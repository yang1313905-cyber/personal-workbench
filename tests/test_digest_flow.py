"""简报主流程的落库行为测试。

重点保护一个容易踩的隐患：推送失败后重试时，素材不能被当成"已见"而被去重掉，
否则重试只会发出一封"今日无重要新闻"的空简报。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _State:
    def __init__(self) -> None:
        self.seen: list = []
        self.digests: list = []

    def is_seen(self, h: str) -> bool:
        return False

    def mark_seen_many(self, items: list) -> None:
        self.seen.extend(items)

    def mark_digest(self, date: str, content: str, channels=None) -> None:
        self.digests.append((date, content, channels))

    def prune(self, days: int) -> int:
        return 0


class _Status:
    def __init__(self) -> None:
        self.last: dict = {}

    def update(self, **kw) -> None:
        self.last = kw

    def record_error(self, *a, **k) -> None:
        pass


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Ctx:
    def __init__(self, cfg, state, status) -> None:
        self.config, self.state, self.status, self.log = cfg, state, status, _Log()

    def get(self, key, default=None):
        return default


def _cfg(tmp_path: Path) -> dict:
    return {
        "feeds": [],
        "http": {},
        "llm": {},
        "paths": {"output": str(tmp_path), "state": str(tmp_path / "state.db")},
        "news_digest": {
            "output_dir": str(tmp_path),
            "push": {"enabled": True, "channels": []},
            "dedupe_keep_days": 3,
            "max_items": 30,
            "max_per_source": 8,
            "include_keywords": [],
            "exclude_keywords": [],
        },
    }


_ITEMS = [{
    "hash": "h1", "title": "标题一", "summary": "摘要一", "link": "https://example.com/1",
    "source_name": "Mock", "source_id": "mock", "weight": 1.0,
    "published": "2026-09-24T00:00:00+00:00", "lang": "zh", "category": "tech",
}]


@pytest.mark.parametrize("push_ok,expect_seen", [(True, True), (False, False)])
def test_items_marked_seen_only_when_delivered(monkeypatch, tmp_path, push_ok, expect_seen):
    from workbench.modules.news_digest import module

    monkeypatch.setattr(module.fetcher, "fetch_all", lambda *a, **k: ([dict(_ITEMS[0])], []))
    monkeypatch.setattr(module.distill, "compose",
                        lambda *a, **k: ("## 今日重点\n[1] 这是一段分析内容。", True, None))
    monkeypatch.setattr(module, "broadcast", lambda *a, **k: {"smtp": push_ok})

    state = _State()
    result = module.run(_Ctx(_cfg(tmp_path), state, _Status()))

    assert result["push"] == {"smtp": push_ok}
    assert bool(state.seen) is expect_seen
    # 无论成败都要留下简报记录（本地存档与状态页依赖它）
    assert state.digests and state.digests[0][2] == ["smtp"]


def test_digest_contains_clickable_real_link(monkeypatch, tmp_path):
    """主流程产出的正文必须带真实原文链接（邮箱里可点）。"""
    from workbench.modules.news_digest import module

    monkeypatch.setattr(module.fetcher, "fetch_all", lambda *a, **k: ([dict(_ITEMS[0])], []))
    monkeypatch.setattr(module.distill, "compose",
                        lambda *a, **k: ("## 今日重点\n[1] 这是一段分析内容。", True, None))
    monkeypatch.setattr(module, "broadcast", lambda *a, **k: {"smtp": True})

    state = _State()
    module.run(_Ctx(_cfg(tmp_path), state, _Status()))

    body = state.digests[0][1]
    assert "### 1. [标题一](https://example.com/1)" in body
