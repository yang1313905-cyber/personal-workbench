"""LLM 蒸馏：调用任意 OpenAI 兼容接口（OpenAI / DeepSeek / Moonshot / Ollama / vLLM）。

零 SDK 依赖，直接走 HTTP，兼容所有 provider；支持无密钥的本地模型
（base_url 指向 Ollama 时可不填 api_key）。

可靠性：LLM 调用带指数退避重试；全部失败则降级为本地兜底简报
（标题 + 摘要 + 链接），保证"推送永不静默失败"。
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import requests

from ...core.retry import retry
from .prompts import SYSTEM_PROMPT, build_user_prompt

log = logging.getLogger("workbench.news.distill")


def llm_chat(llm_cfg: dict, system: str, user: str) -> str:
    """一次 chat/completions 调用，返回助手文本。"""
    api_key = llm_cfg.get("api_key")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    base = str(llm_cfg["base_url"]).rstrip("/")
    payload = {
        "model": llm_cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": float(llm_cfg.get("temperature", 0.4)),
        "max_tokens": int(llm_cfg.get("max_tokens", 2500)),
        "stream": False,
    }
    resp = requests.post(
        base + "/chat/completions",
        json=payload,
        headers=headers,
        timeout=float(llm_cfg.get("timeout", 120)),
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"LLM 返回格式异常: {str(data)[:500]}") from e


def _requirements(nd: dict) -> str:
    parts = []
    if nd.get("language"):
        parts.append(f"语言：{nd['language']}")
    if nd.get("word_count"):
        parts.append(f"字数：{nd['word_count']} 字")
    if nd.get("focus"):
        parts.append(f"重点关注：{nd['focus']}")
    return "；".join(parts) or "默认要求"


def _sources_in_text(text: str, items: List[dict]) -> set:
    """统计简报正文实际引用了哪些来源（按素材中的来源名匹配）。"""
    used = set()
    for it in items:
        name = it.get("source_name", "")
        short = name.split(" (")[0].split("（")[0]  # "Reuters (via Google News)" → "Reuters"
        if name and (name in text or (short and len(short) > 1 and short in text)):
            used.add(name)
    return used


def compose(items: List[dict], date_str: str, cfg: dict) -> Tuple[str, bool, Optional[str]]:
    """生成简报正文。返回 (正文, 是否由 LLM 生成, LLM 错误原因或 None)。

    多源强制：生成后统计正文引用的来源数，若素材含 ≥2 个来源而正文只用了 1 个，
    带纠正指令重写一次（最多一次，避免死循环）。
    """
    nd = cfg.get("news_digest", {})
    user = build_user_prompt(date_str, items, _requirements(nd))
    llm_cfg = cfg.get("llm", {})
    try:
        text = retry(
            lambda: llm_chat(llm_cfg, SYSTEM_PROMPT, user),
            attempts=3,
            delay=3.0,
            what="LLM 蒸馏",
        )
        log.info("LLM 蒸馏完成，正文 %d 字符", len(text))

        # ---- 多源校验 + 一次性重写 ----
        available = {it.get("source_name", "") for it in items if it.get("source_name")}
        if len(available) >= 2:
            used = _sources_in_text(text, items)
            if len(used) < 2:
                names = "、".join(sorted(available))
                log.warning("简报来源单一（%s），触发一次多源重写", sorted(used) or "无")
                retry_user = (
                    user
                    + f"\n\n【重要纠正】你上一版的今日重点只引用了来源「{'、'.join(sorted(used)) or '无'}」，"
                    f"不合格。本次素材包含多个来源：{names}。"
                    "请重新输出完整简报，今日重点必须覆盖至少 3 个不同来源，"
                    "国际来源（TechCrunch / The Verge / Reuters）与中文来源（华尔街见闻等）都要有。"
                )
                text = retry(
                    lambda: llm_chat(llm_cfg, SYSTEM_PROMPT, retry_user),
                    attempts=1,
                    delay=0,
                    what="LLM 多源重写",
                )
                log.info("多源重写完成，正文 %d 字符", len(text))
        return text, True, None
    except Exception as e:  # noqa: BLE001
        log.exception("LLM 蒸馏失败，降级为本地兜底简报")
        reason = str(e)
        return fallback_digest(items, reason), False, reason


def fallback_digest(items: List[dict], reason: Optional[str] = None) -> str:
    """LLM 不可用时的本地兜底简报：清晰排版 + 明确标注失败原因。"""
    lines = ["## 今日重点（本地兜底模式 · LLM 未参与）"]
    if not items:
        lines.append("今日无重要新闻（抓取结果为空或全部被过滤）。")
    for i, it in enumerate(items[:5], 1):
        lines.append(f"{i}. **{it.get('title', '')}**（{it.get('source_name', '')}）")
        summary = (it.get("summary") or "").strip()
        if summary:
            lines.append(f"   - 摘要：{summary[:200]}")
        if it.get("link"):
            lines.append(f"   - 原文：{it['link']}")
    lines.append("")
    lines.append("> ⚠️ 本简报由**本地兜底逻辑**生成：LLM 蒸馏失败，内容为原始素材的简单整理，不含深度分析。")
    if reason:
        lines.append(f"> 失败原因：`{reason[:300]}`")
    lines.append("> 修复：检查「配置中心 → LLM 参数」的 Base URL / 模型 / API Key，"
                 "改好后在首页勾选「强制重新生成」。")
    return "\n".join(lines)
