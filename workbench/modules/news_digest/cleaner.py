"""清洗与去重：HTML 剥离、关键词过滤、标题相似度去重（站内 + 历史）。

去重策略：
- 历史去重：同一链接/标题的 hash 已见过则丢弃（避免天天重复报道旧闻）
- 事件去重：比较原标题及归一化的内容词，保留权重更高的来源
中文分词不做重型处理，用相邻字符 bigram 近似，对标题级去重足够。
"""
from __future__ import annotations

import hashlib
import html
import re
from functools import lru_cache
from html.parser import HTMLParser
from typing import List

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[a-z0-9]+")
ENGLISH_STOPWORDS = frozenset("""
    a about above after again against all am an and any are as at be because been
    before being below between both but by can could did do does doing down during
    each few for from further had has have having he her here hers herself him
    himself his how i if in into is it its itself just may me might more most my
    myself no nor not now of off on once only or other ought our ours ourselves out
    over own per same she should so some such than that the their theirs them
    themselves then there these they this those through to too under until up upon
    use very was we were what when where which while who whom why will with would
    you your yours yourself yourselves new report reports said says say company
""".split())


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


_GENERIC_EVENT_WORDS = frozenset("""
    raise raises raised funding round billion million trillion announce announces
    announced launch launches launched plan plans deal deals talk talks update
    updates version latest first year years week weeks month months today market
    markets price prices stock stocks share shares global world tech user users
    feature features service services system systems model models industry ceo
    chief founder startup startups firm firms
""".split())
_CASED_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _stem_token(word: str) -> str:
    return word[:-1] if word.isascii() and len(word) > 4 and word.endswith("s") else word


@lru_cache(maxsize=4096)
def _event_tokens(title: str) -> tuple[set, set, set, str]:
    original = tokens(title)
    content = {
        _stem_token(word)
        for word in original
        if len(word) >= 2 and word not in ENGLISH_STOPWORDS and word not in _GENERIC_EVENT_WORDS
    }
    entities: set[str] = set()
    lead_entity = ""
    raw_words = _CASED_TOKEN_RE.findall(title or "")
    for idx, word in enumerate(raw_words):
        low = word.lower()
        if len(low) < 2 or low in ENGLISH_STOPWORDS or low in _GENERIC_EVENT_WORDS:
            continue
        has_upper = any(c.isupper() for c in word)
        has_digit = any(c.isdigit() for c in word)
        has_alpha = any(c.isalpha() for c in word)
        if has_upper or (has_digit and has_alpha):
            stemmed = _stem_token(low)
            entities.add(stemmed)
            if idx == 0:
                lead_entity = stemmed
    return original, content, entities, lead_entity


def is_same_event(title_a: str, title_b: str, threshold: float = 0.55) -> bool:
    """Use title similarity, with an entity-guarded second pass for reworded coverage."""
    raw_a, content_a, entities_a, lead_a = _event_tokens(title_a)
    raw_b, content_b, entities_b, lead_b = _event_tokens(title_b)
    # 两条新闻首词分别指向互不出现的不同主体（如 OpenAI vs Anthropic），不合并为同一事件
    if (lead_a and lead_b and lead_a != lead_b
            and lead_a not in entities_b and lead_b not in entities_a):
        return False
    if overlap_ratio(raw_a, raw_b) >= threshold:
        return True
    if not content_a or not content_b:
        return False
    # 两条新闻各自明确指向不同的主体/品牌且无共同实体时，绝不合并为同一事件
    if entities_a and entities_b and not (entities_a & entities_b):
        return False
    common = len(content_a & content_b)
    return common >= 3 and common / min(len(content_a), len(content_b)) >= 0.42


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
    ordered = sorted(items, key=lambda it: float(it.get("weight", 0.0)), reverse=True)
    for it in ordered:
        if store is not None and store.is_seen(it["hash"]):
            continue
        title = it.get("title") or ""
        if any(is_same_event(title, other.get("title") or "", threshold) for other in kept):
            continue
        kept.append(it)
    return kept
