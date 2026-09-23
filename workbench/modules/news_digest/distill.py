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
from .render import parse as parse_digest

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


def _highlight_sources(parsed: dict, items: List[dict]) -> set:
    """统计「今日重点」实际引用了哪些来源。

    注意：新契约下模型只输出素材编号，不写来源名，因此必须按编号回填后的
    真实来源来统计，而不是在正文里搜来源字符串。
    """
    used = set()
    for h in parsed.get("highlights", []):
        i = int(h.get("index") or 0)
        if 1 <= i <= len(items):
            name = items[i - 1].get("source_name", "")
            if name:
                used.add(name)
    return used


def _valid_highlights(parsed: dict, items: List[dict]) -> list:
    return [h for h in parsed.get("highlights", [])
            if 1 <= int(h.get("index") or 0) <= len(items)]


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
        parsed = parse_digest(text)

        # ---- 格式校验：必须能解析出有效素材编号，否则拿不到标题与链接 ----
        if items and not _valid_highlights(parsed, items):
            log.warning("LLM 输出中没有可解析的素材编号，触发一次格式纠正重写")
            fix_user = (
                user
                + "\n\n【重要纠正】你上一版没有按要求用素材编号引用新闻，"
                "系统因此无法为每条新闻补全标题与原文链接。"
                "请严格按 `[编号] 分析内容` 的格式重新输出完整简报："
                "每一条重点都以方括号编号开头，编号必须是素材中真实存在的编号；"
                "不要写标题、来源和链接，这些都由系统自动补全。"
            )
            text = retry(
                lambda: llm_chat(llm_cfg, SYSTEM_PROMPT, fix_user),
                attempts=1,
                delay=0,
                what="LLM 格式纠正",
            )
            parsed = parse_digest(text)
            log.info("格式纠正后正文 %d 字符，解析到 %d 条有效重点",
                     len(text), len(_valid_highlights(parsed, items)))

        # ---- 多源校验 + 一次性重写 ----
        available = {it.get("source_name", "") for it in items if it.get("source_name")}
        if len(available) >= 2:
            used = _highlight_sources(parsed, items)
            if len(used) < 2:
                names = "、".join(sorted(available))
                log.warning("简报来源单一（%s），触发一次多源重写", sorted(used) or "无")
                retry_user = (
                    user
                    + f"\n\n【重要纠正】你上一版的今日重点只覆盖了来源「{'、'.join(sorted(used)) or '无'}」，"
                    f"不合格。本次素材包含多个来源：{names}。"
                    "请重新输出完整简报，今日重点必须覆盖至少 3 个不同来源，"
                    "国际来源（TechCrunch / The Verge / Reuters）与中文来源（华尔街见闻等）都要有。"
                    "仍然只输出 `[编号] 分析内容`，不要写标题、来源和链接。"
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
    """LLM 不可用时的本地兜底简报。

    这里同样输出新契约格式（``[编号] 分析``），这样 render.py 能照常补全真实标题
    与原文链接，邮件排版与正常情况一致，只是缺少 LLM 的深度分析
    （兜底模式会在简报页脚标注，并带上失败原因）。
    """
    lines = ["## 今日重点"]
    if not items:
        lines.append("今日无重要新闻（抓取结果为空或全部被过滤）。")
    else:
        for i in range(1, min(len(items), 5) + 1):
            summary = (items[i - 1].get("summary") or "").strip()
            lines.append(f"[{i}] {summary[:200] or '（无摘要）'}")
    return "\n".join(lines)
