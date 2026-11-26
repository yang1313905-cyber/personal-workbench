"""LLM 蒸馏：调用任意 OpenAI 兼容接口（OpenAI / DeepSeek / Moonshot / Ollama / vLLM）。

零 SDK 依赖，直接走 HTTP，兼容所有 provider；支持无密钥的本地模型
（base_url 指向 Ollama 时可不填 api_key）。

可靠性：LLM 调用带指数退避重试；全部失败则降级为本地兜底简报
（标题 + 摘要 + 链接），保证"推送永不静默失败"。
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

import requests

from ...core.retry import retry
from .cleaner import ENGLISH_STOPWORDS, is_same_event, overlap_ratio
from .prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_analysis_prompt,
    build_synthesis_prompt,
    build_user_prompt,
    candidate_ids,
)
from .render import parse as parse_digest

log = logging.getLogger("workbench.news.distill")
_BATCH_SIZE = 1
_MAX_WORKERS = 3
_MAX_RECOVERIES = 4
_SELECTION_TIMEOUT = 60.0
_ANALYSIS_TIMEOUT = 45.0
_SYNTHESIS_TIMEOUT = 60.0


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


def _requirements(nd: dict, highlight_count: int) -> str:
    parts = [f"今日重点目标为 {highlight_count} 条，优先覆盖兴趣匹配素材"]
    if nd.get("interest_keywords"):
        parts.append("兴趣关键词：" + "、".join(nd["interest_keywords"]))
    if nd.get("language"):
        parts.append(f"语言：{nd['language']}")
    if nd.get("word_count"):
        parts.append(f"字数：{nd['word_count']} 字")
    if nd.get("focus"):
        parts.append(f"重点关注：{nd['focus']}")
    return "；".join(parts)


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


def _response_list(text: str, key: str) -> list:
    """Find the expected JSON object even when surrounded by fences or prose."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
        except (ValueError, RecursionError):
            continue
        value = obj.get(key)
        if isinstance(value, list):
            return value
    return []


def _select_highlights(proposed: List[str], candidates: dict[str, dict],
                       limit: int, threshold: float) -> List[str]:
    titles = {key: item.get("title") or "" for key, item in candidates.items()}
    sources = {key: item.get("source_name") or item.get("source_id") or ""
               for key, item in candidates.items()}

    def duplicates(key, others):
        return any(is_same_event(titles[key], titles[other], threshold) for other in others)

    selected = []
    for key in dict.fromkeys([*proposed, *candidates]):
        if len(selected) == limit:
            break
        if not duplicates(key, selected):
            selected.append(key)

    minimum = min(3, len(selected), len(set(sources.values()) - {""}))
    if minimum < 2:
        return selected
    cap = max(1, len(selected) * 3 // 5)

    def penalty(counts):
        missing = minimum - sum(bool(source) and count > 0 for source, count in counts.items())
        excess = sum(max(0, count - cap) for count in counts.values())
        return max(0, missing), excess

    while True:
        counts = Counter(sources[key] for key in selected)
        current = penalty(counts)
        if current == (0, 0):
            return selected

        incoming = [key for key in candidates if key not in selected and sources[key]]
        incoming.sort(key=lambda key: counts[sources[key]])
        outgoing = sorted(reversed(selected), key=lambda key: counts[sources[key]], reverse=True)
        replacement = None
        for key in incoming:
            for other in outgoing:
                if sources[key] == sources[other]:
                    continue
                adjusted = counts.copy()
                adjusted[sources[other]] -= 1
                adjusted[sources[key]] += 1
                remaining = (pick for pick in selected if pick != other)
                if penalty(adjusted) < current and not duplicates(key, remaining):
                    replacement = other, key
                    break
            if replacement:
                break
        if not replacement:
            return selected
        other, key = replacement
        selected[selected.index(other)] = key


def _normalized_title(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold() if char.isalnum())


def _title_match(echo: str, title: str, other_titles: List[str]) -> bool:
    if not echo or not title:
        return False
    score = SequenceMatcher(None, echo, title, autojunk=False).ratio()
    substring = min(len(echo), len(title)) >= 12 and (echo in title or title in echo)
    if score < 0.55 and not substring:
        return False
    return all(SequenceMatcher(None, echo, other, autojunk=False).ratio() < score for other in other_titles)


def _evidence_tokens(text: str, known_entities: frozenset[str] = frozenset()) -> set[str]:
    text = unicodedata.normalize("NFKC", text)
    words = {
        word.casefold() for word in re.findall(r"[A-Za-z0-9]+", text)
        if (len(word) >= 4 or word.isdigit() or word.casefold() in known_entities
            or (len(word) >= 2 and word.isupper()))
        and word.casefold() not in ENGLISH_STOPWORDS
    }
    for sequence in re.findall(r"[\u4e00-\u9fff]{4,}", text):
        words.update(sequence[i:i + 4] for i in range(len(sequence) - 3))
    return words


def verify_batch_alignment(entries: list, batch: dict[str, dict]) -> dict[str, str]:
    """Accept only unambiguous IDs, matching title echoes and consistent evidence."""
    titles = {key: _normalized_title(item.get("title") or "") for key, item in batch.items()}
    evidence = {
        key: _evidence_tokens(f"{item.get('title') or ''} {item.get('summary') or ''}")
        for key, item in batch.items()
    }
    frequencies = Counter(token for tokens in evidence.values() for token in tokens)
    exclusive = {token for token, count in frequencies.items() if count == 1}
    known_entities = frozenset(token for token in frequencies if len(token) < 4)

    records = [entry for entry in entries if isinstance(entry, dict) and isinstance(entry.get("id"), str)]
    returned_ids = Counter(entry["id"] for entry in records)
    verified = {}
    for entry in records:
        key = entry["id"]
        if key not in batch or returned_ids[key] != 1:
            continue
        echo, analysis = entry.get("title_echo"), entry.get("analysis")
        if not isinstance(echo, str) or not isinstance(analysis, str) or not analysis.strip():
            continue
        if not _title_match(_normalized_title(echo), titles[key],
                            [title for other, title in titles.items() if other != key]):
            continue

        tokens = _evidence_tokens(analysis, known_entities)
        own = evidence[key]
        if (tokens & (exclusive - own) and not tokens & (exclusive & own)
                and overlap_ratio(tokens, own) < 0.50):
            continue

        # Keep all model text inside the one Markdown line owned by this item.
        verified[key] = " ".join(analysis.split())
    return verified


def _call(llm_cfg: dict, system: str, user: str, *, stage: str,
          attempts: int = 1) -> Tuple[str, Optional[str]]:
    try:
        return retry(lambda: llm_chat(llm_cfg, system, user),
                     attempts=attempts, delay=3.0, what=stage), None
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) or type(exc).__name__
        log.warning("%s失败：%s", stage, reason)
        return "", reason


_SIGNAL_HEADER_ONLY_RE = re.compile(r"^\*{0,2}\s*(?:信号|风险|观察点|后续观察|趋势|信号与风险)\s*\*{0,2}\s*[:：]?\s*$")


def _clean_signals(signals: List[str]) -> List[str]:
    return [s for s in signals if s.strip() and not _SIGNAL_HEADER_ONLY_RE.match(s.strip())]


def _source_summary(item: dict) -> str:
    return " ".join((item.get("summary") or "").split())[:200] or "（无摘要）"


def _stage_cfg(llm_cfg: dict, *, max_timeout: float, max_tokens: int) -> dict:
    cfg = dict(llm_cfg)
    cfg["timeout"] = min(float(cfg.get("timeout", max_timeout)), max_timeout)
    cfg["max_tokens"] = min(int(cfg.get("max_tokens", max_tokens)), max_tokens)
    return cfg


def compose(items: List[dict], date_str: str, cfg: dict) -> Tuple[str, bool, Optional[str]]:
    """选题、单条隔离分析校验，再按原始素材索引组装简报。

    每条重点新闻独立发起一次单条分析调用，模型在分析某一条时物理上不可见
    其他新闻，从结构上杜绝跨条串稿（即使全文纯中文意译也不会错位）。
    """
    nd = cfg.get("news_digest", {})
    if not items:
        return fallback_digest([]), False, None
    highlight_count = min(max(0, int(nd.get("highlight_count", 15))), len(items))
    if not highlight_count:
        return fallback_digest(items, highlight_count=0), False, None

    llm_cfg = cfg.get("llm", {})
    sel_cfg = _stage_cfg(llm_cfg, max_timeout=_SELECTION_TIMEOUT, max_tokens=600)
    item_cfg = _stage_cfg(llm_cfg, max_timeout=_ANALYSIS_TIMEOUT, max_tokens=350)
    syn_cfg = _stage_cfg(llm_cfg, max_timeout=_SYNTHESIS_TIMEOUT, max_tokens=800)

    ids = candidate_ids(items)
    candidates = dict(zip(ids, items))
    indices = {key: i for i, key in enumerate(ids, 1)}
    user = build_user_prompt(date_str, items, _requirements(nd, highlight_count), ids=ids)
    reply, selection_error = _call(sel_cfg, SYSTEM_PROMPT, user, stage="LLM 选题", attempts=3)
    proposed = [key for key in _response_list(reply, "selected_ids")
                if isinstance(key, str) and key in candidates]
    selected = _select_highlights(proposed, candidates, highlight_count,
                                  float(nd.get("overlap_threshold", 0.55)))

    def analyze_one(key: str) -> dict[str, str]:
        batch = {key: candidates[key]}
        response, _ = _call(item_cfg, ANALYSIS_SYSTEM_PROMPT, build_analysis_prompt(batch),
                            stage="LLM 重点分析")
        entries = _response_list(response, "items")
        return verify_batch_alignment(entries, batch)

    analyses: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        for verified in executor.map(analyze_one, selected):
            analyses.update(verified)
        missing = [key for key in selected if key not in analyses][:_MAX_RECOVERIES]
        if missing:
            for verified in executor.map(analyze_one, missing):
                analyses.update(verified)

    reason = selection_error or "LLM 未返回通过校验的重点分析"
    if not analyses and not proposed:
        return fallback_digest(items, reason, highlight_count), False, reason

    trend, signals = "", []
    if analyses:
        ordered = {key: analyses[key] for key in selected if key in analyses}
        summary, _ = _call(syn_cfg, SYNTHESIS_SYSTEM_PROMPT, build_synthesis_prompt(date_str, candidates, ordered),
                           stage="LLM 趋势归纳")
        parsed = parse_digest(summary)
        trend, signals = parsed["trend"], _clean_signals(parsed["signals"])[:5]

    log.info("LLM 重点分析通过校验 %d/%d 条", len(analyses), len(selected))
    lines = ["## 今日重点"]
    # 仅写入通过 LLM 校验的条目；缺失条目交由 render.build 补齐并自动标注「来源摘要」
    for key in selected:
        if key in analyses:
            lines.append(f"[{indices[key]}] {analyses[key]}")
    lines.extend(["", "## 趋势观察", trend, "", "## 信号与风险"])
    lines.extend(f"- {signal}" for signal in signals)
    return "\n".join(lines), bool(analyses), None if analyses else reason


def fallback_digest(items: List[dict], reason: Optional[str] = None, highlight_count: int = 15) -> str:
    """LLM 不可用时的本地兜底简报。

    这里同样输出新契约格式（``[编号] 分析``），这样 render.py 能照常补全真实标题
    与原文链接，邮件排版与正常情况一致，只是缺少 LLM 的深度分析
    （兜底模式会在简报页脚标注，并带上失败原因）。
    """
    lines = ["## 今日重点"]
    if not items:
        lines.append("今日无重要新闻（抓取结果为空或全部被过滤）。")
    else:
        for i in range(1, min(len(items), highlight_count) + 1):
            lines.append(f"[{i}] {_source_summary(items[i - 1])}")
    return "\n".join(lines)
