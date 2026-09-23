"""去重与清洗的单元测试（纯逻辑，不依赖网络）。"""
from workbench.modules.news_digest import cleaner


class _FakeStore:
    def __init__(self, seen=()):
        self.seen = set(seen)

    def is_seen(self, h):
        return h in self.seen


def test_clean_text():
    assert cleaner.clean_text("<p>Hello &amp; <b>World</b></p>") == "Hello & World"
    assert cleaner.clean_text("  a   b\n\t c ") == "a b c"


def test_overlap_similar_titles():
    a = "OpenAI 发布新一代大模型 GPT-5"
    b = "OpenAI 正式发布 GPT-5 新一代大模型"
    assert cleaner.overlap_ratio(cleaner.tokens(a), cleaner.tokens(b)) > 0.55


def test_overlap_different_titles():
    a = "OpenAI 发布新一代大模型"
    b = "苹果发布新款折叠屏手机"
    assert cleaner.overlap_ratio(cleaner.tokens(a), cleaner.tokens(b)) < 0.3


def test_keyword_filter():
    assert cleaner.keyword_ok("AI 芯片巨头发布新品", ["AI"], [])
    assert not cleaner.keyword_ok("电商大促", ["AI"], [])
    assert not cleaner.keyword_ok("双11 大促来袭", [], ["双11"])


def test_dedupe_keeps_high_weight():
    items = [
        {"hash": "a", "title": "OpenAI 发布 GPT-5", "weight": 1.0},
        {"hash": "b", "title": "OpenAI 发布 GPT-5 新模型", "weight": 0.5},
        {"hash": "c", "title": "苹果发布新手机", "weight": 0.9},
    ]
    kept = cleaner.dedupe(items, _FakeStore(), threshold=0.55)
    assert [it["hash"] for it in kept] == ["a", "c"]


def test_dedupe_skips_seen_history():
    items = [
        {"hash": "x", "title": "旧闻重复", "weight": 1.0},
        {"hash": "y", "title": "全新新闻", "weight": 0.9},
    ]
    kept = cleaner.dedupe(items, _FakeStore(seen={"x"}), threshold=0.55)
    assert [it["hash"] for it in kept] == ["y"]


def test_balance_sources_caps_per_source():
    """多源配额制：每个来源最多保留 max_per_source 条，保证多源覆盖。"""
    from collections import Counter

    items = []
    for src in ("a", "b", "c"):
        for n in range(10):
            items.append({"source_id": src, "title": f"{src}-{n}", "weight": 1.0})
    balanced = cleaner.balance_sources(items, max_per_source=8)
    assert len(balanced) == 24  # 3 源 × 8 条
    counts = Counter(it["source_id"] for it in balanced)
    assert counts == {"a": 8, "b": 8, "c": 8}
    # 不限量时原样返回
    assert cleaner.balance_sources(items, max_per_source=0) == items
