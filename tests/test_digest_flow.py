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
            "max_age_hours": 0,  # Fixed historical fixtures are intentionally retained.
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


def test_daily_email_contains_45_distinct_stories_when_model_returns_few(monkeypatch, tmp_path):
    import re

    from workbench.channels import smtp_mail
    from workbench.core.config import load_yaml
    from workbench.modules.news_digest import module

    items = [dict(_ITEMS[0], hash=f"h{i}", title=f"Story-{i}", link=f"https://example.com/{i}",
                  source_id=f"s{i % 6}", published="") for i in range(66)]
    monkeypatch.setattr(module.fetcher, "fetch_all", lambda *a: (items, []))
    model_text = "## 今日重点\n[1] 第一条分析\n[1] 重复分析\n[99] 无效编号\n[3] 第三条分析"
    monkeypatch.setattr(module.distill, "compose", lambda *a: (model_text, True, None))

    messages = []

    class InMemorySMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def login(self, *a):
            pass

        def send_message(self, message):
            messages.append(message)

    monkeypatch.setattr(smtp_mail.smtplib, "SMTP_SSL", InMemorySMTP)
    cfg = _cfg(tmp_path)
    cfg["news_digest"] = load_yaml(ROOT / "config" / "config.yaml")["news_digest"]
    cfg["news_digest"]["output_dir"] = str(tmp_path)
    cfg["channels"] = {"smtp": {"enabled": True, "host": "example.test", "use_ssl": True,
                                 "user": "sender@example.test", "password": "placeholder",
                                 "to": "reader@example.test"}}
    state = _State()
    result = module.run(_Ctx(cfg, state, _Status()))

    assert result["push"] == {"smtp": True}
    assert result["items_shown"] == len(state.seen) == 45
    html = messages[0].get_body(preferencelist=("html",)).get_content()
    links = re.findall(r'href="(https://example[.]com/\d+)"', html)
    assert len(links) == len(set(links)) == 45
    assert html.count("来源摘要") == 13
    assert "本期 45 条（重点 15 条，快讯 30 条）" in html


# ---------------------------------------------------------------- 重试上限
# 保护 2026-10-19 的教训：邮箱授权码失效后外部调度每 5 分钟重试，一天 74 次。

def _load_daily_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "daily_digest_script", ROOT / "scripts" / "daily_digest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeStatus:
    def __init__(self, **kw):
        self.d = dict(kw)

    def read(self):
        return dict(self.d)

    def update(self, **kw):
        self.d.update(kw)


def test_attempt_counter_increments_and_caps():
    mod = _load_daily_module()
    st = _FakeStatus()
    assert mod._attempts_today(st) == 0
    for i in range(1, mod.MAX_ATTEMPTS_PER_DAY + 2):
        assert mod._note_attempt(st) == i
    assert mod._attempts_today(st) > mod.MAX_ATTEMPTS_PER_DAY   # 会触发停止重试


def test_attempt_counter_resets_on_new_day():
    mod = _load_daily_module()
    st = _FakeStatus(attempt_date="1999-01-01", attempt_count=99)
    assert mod._attempts_today(st) == 0          # 跨日期自动归零
    assert mod._note_attempt(st) == 1


def test_daily_script_force_sets_force_digest_flag(monkeypatch, tmp_path):
    mod = _load_daily_module()
    captured = {}

    class _DummyLock:
        def __init__(self, *_a):
            pass

        def acquire(self):
            return True

        def release(self):
            pass

    class _DummyState(_State):
        def close(self):
            pass

        def last_digest_date(self):
            return None

    class _DummyCtx(_Ctx):
        def __init__(self, cfg, state, status):
            super().__init__(cfg, state, status)
            self.extras = {}

        def get(self, key, default=None):
            return self.extras.get(key, default)

    ctx = _DummyCtx(_cfg(tmp_path), _DummyState(), _FakeStatus())
    monkeypatch.setattr(mod, "make_context", lambda: ctx)
    monkeypatch.setattr(mod, "FileLock", _DummyLock)

    def _run_module(name, c):
        captured["force_digest"] = c.get("force_digest")
        return {"push": {"smtp": True}, "output_file": str(tmp_path / "out.md")}

    monkeypatch.setattr(mod.registry, "run_module", _run_module)
    assert mod.main(["--force"]) == 0
    assert captured["force_digest"] is True


def test_fetch_error_urls_are_redacted_in_status(monkeypatch, tmp_path):
    from workbench.modules.news_digest import module
    secret_err = {"source": "priv", "error": "Failed https://feed.example.com/rss?token=secret123"}
    monkeypatch.setattr(module.fetcher, "fetch_all", lambda *a, **k: ([dict(_ITEMS[0])], [secret_err]))
    monkeypatch.setattr(module.distill, "compose", lambda *a, **k: ("## 今日重点\n[1] 分析。", True, None))
    monkeypatch.setattr(module, "broadcast", lambda *a, **k: {"smtp": True})
    status = _Status()
    recorded = []
    orig_update = status.update

    def capture(**kw):
        recorded.append(kw)
        orig_update(**kw)

    status.update = capture
    module.run(_Ctx(_cfg(tmp_path), _State(), status))
    fetch_errs = next(kw["fetch_errors"] for kw in recorded if "fetch_errors" in kw)
    assert "secret123" not in str(fetch_errs)
    assert "[redacted-url]" in fetch_errs[0]["error"]


def test_only_displayed_items_marked_seen(monkeypatch, tmp_path):
    from workbench.modules.news_digest import module
    items = [dict(_ITEMS[0], hash=f'h{i}', title=f'unique{i}', link=f'https://example.com/{i}') for i in range(6)]
    monkeypatch.setattr(module.fetcher, 'fetch_all', lambda *a: (items, []))
    monkeypatch.setattr(module.distill, 'compose', lambda *a: ('## 今日重点\n[1] 一段分析', True, None))
    monkeypatch.setattr(module, 'broadcast', lambda *a, **k: {'smtp': True})
    cfg = _cfg(tmp_path)
    cfg['news_digest'].update(highlight_count=1, appendix_limit=1, max_items=4)
    state = _State()
    module.run(_Ctx(cfg, state, _Status()))
    assert len(state.seen) == 2


def test_refresh_never_sends_or_marks_seen(monkeypatch, tmp_path):
    import json
    from workbench.modules.news_digest import module
    monkeypatch.setattr(module.fetcher, 'fetch_all', lambda *a: ([dict(_ITEMS[0])], []))
    def forbidden(*a, **k):
        raise AssertionError('Refresh must not distill or send')
    monkeypatch.setattr(module.distill, 'compose', forbidden)
    monkeypatch.setattr(module, 'broadcast', forbidden)
    state = _State()
    ctx = _Ctx(_cfg(tmp_path), state, _Status())
    ctx.get = lambda key, default=None: key == 'refresh_only'
    result = module.run(ctx)
    assert result['available'] == 1
    assert not state.seen and not state.digests
    assert len(json.loads((tmp_path / 'news-latest.json').read_text())['items']) == 1
