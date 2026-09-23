"""清洗与去重：HTML 剥离、关键词过滤、标题相似度去重（站内 + 历史）。

去重策略：
- 历史去重：同一链接/标题的 hash 已见过则丢弃（避免天天重复报道旧闻）
- 站内去重：标题 token 的 Jaccard 相似度 ≥ threshold 视为同一事件，
  保留权重更高的来源
中文分词不做重型处理，用相邻字符 bigram 近似，对标题级去重足够。
"""
from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser
from typing import List

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[a-z0-9]+")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(text: str) -> str:
    """用 stdlib HTMLParser 剥离标签，避免正则误伤。"""
    if not text:
        return ""
    parser = _TextExtractor()
    parser.feed(text)
    return " ".join(" ".join(parser.parts).split())


def clean_text(text: str) -> str:
    return html.unescape(strip_html(text)).strip()


def tokens(text: str) -> set:
    """中文相邻 bigram + 英文单词/数字，返回 token 集合。"""
    t = text.lower()
    result = set(LATIN_RE.findall(t))
    cjk = CJK_RE.findall(t)
    result.update("".join(pair) for pair in zip(cjk, cjk[1:]))
    return result


def overlap_ratio(a: set, b: set) -> float:
    """Jaccard 相似度。"""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def keyword_ok(text: str, include: List[str], exclude: List[str]) -> bool:
    """关键词过滤：命中 exclude 则丢弃；include 非空时必须命中其一。"""
    t = text.lower()
    if exclude and any(k.lower() in t for k in exclude):
        return False
    if include and not any(k.lower() in t for k in include):
        return False
    return True


def item_hash(source_id: str, link: str, title: str) -> str:
    return hashlib.sha1(f"{source_id}|{link or ''}|{title}".encode("utf-8")).hexdigest()


def balance_sources(items: List[dict], max_per_source: int) -> List[dict]:
    """多源配额制：每个来源最多保留 max_per_source 条。

    入参 items 应已按（权重, 时间）降序排列，这样每个来源保留的是
    自己最优质的前 N 条，同时保证候选池覆盖所有来源，避免单一网站霸榜。
    max_per_source <= 0 表示不限量。
    """
    if max_per_source <= 0:
        return items
    counts: dict = {}
    result: List[dict] = []
    for it in items:
        sid = it.get("source_id", "")
        if counts.get(sid, 0) < max_per_source:
            result.append(it)
            counts[sid] = counts.get(sid, 0) + 1
    return result


def dedupe(items: List[dict], store=None, keep_days: int = 3, threshold: float = 0.55) -> List[dict]:
    """历史去重 + 站内去重。高权重来源优先保留。

    store 为 None 时跳过历史去重（用于"强制重新生成"）。
    """
    kept: List[dict] = []
    pool: List[tuple] = []  # (title_tokens, item)
    ordered = sorted(items, key=lambda it: float(it.get("weight", 0.0)), reverse=True)
    for it in ordered:
        if store is not None and store.is_seen(it["hash"]):
            continue
        t = tokens(it.get("title", ""))
        if any(overlap_ratio(t, other) >= threshold for other, _ in pool):
            continue
        pool.append((t, it))
        kept.append(it)
    return kept
