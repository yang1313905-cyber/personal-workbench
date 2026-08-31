"""Web UI 后端逻辑单测（不依赖 Streamlit 运行时）+ AppTest 冒烟。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from workbench.webui import config_editor as ce
from workbench.webui import data as wdata

ROOT = Path(__file__).resolve().parents[1]


# ---------------- 配置编辑器（ruamel 保注释） ----------------

def test_yaml_editor_roundtrip_preserves_comments(tmp_path):
    src = ROOT / "config" / "config.yaml"
    target = tmp_path / "config.yaml"
    shutil.copy2(src, target)
    ed = ce.YamlEditor(target)
    ed.set("llm.model", "test-model")
    ed.set("schedule.time", "09:30")
    ed.save()

    text = target.read_text(encoding="utf-8")
    # 注释仍在
    assert "# ----------------" in text
    assert "LLM" in text
    # 值已更新
    import yaml
    data = yaml.safe_load(text)
    assert data["llm"]["model"] == "test-model"
    assert data["schedule"]["time"] == "09:30"
    # 备份已生成
    assert (target.parent / "config.yaml.bak").exists()


def test_yaml_editor_feeds_edit(tmp_path):
    src = ROOT / "config" / "feeds.yaml"
    target = tmp_path / "feeds.yaml"
    shutil.copy2(src, target)
    ed = ce.YamlEditor(target)
    sources = ed.sources()
    sources[0]["enabled"] = False
    ed.save()
    import yaml
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["sources"][0]["enabled"] is False


def test_env_roundtrip(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# 注释\nA=1\n\nB=hello world\n", encoding="utf-8")
    entries = ce.load_env(env)
    assert ("kv", "A", "1") in entries
    ce.set_env("A", "2", env)
    ce.set_env("C", "new", env)
    assert ce.env_value("A", env) == "2"
    assert ce.env_value("C", env) == "new"
    text = env.read_text(encoding="utf-8")
    assert "# 注释" in text          # 注释保留
    assert "B=hello world" in text   # 顺序保留


def test_effective_config_redacts_secrets():
    eff = ce.effective_config()
    llm = eff.get("llm", {})
    if "api_key" in llm:
        # 空密钥保持空（未配置）；非空则必须打码
        assert llm["api_key"] in ("", "***")
    assert isinstance(eff.get("feeds"), list)


# ---------------- 数据访问 ----------------

def _fake_cfg(tmp_path):
    out = tmp_path / "output"
    out.mkdir(parents=True)
    (out / "digest-2026-08-26.md").write_text("## 今日重点\nOpenAI 发布新模型\n", encoding="utf-8")
    (out / "digest-2026-08-25.md").write_text("## 今日重点\n苹果发布新手机\n", encoding="utf-8")
    return {
        "news_digest": {"output_dir": str(out)},
        "paths": {"state": str(tmp_path / "state.db"), "status": str(tmp_path / "status.json")},
        "logging": {"file": str(tmp_path / "workbench.log")},
    }


def test_data_list_search(tmp_path):
    cfg = _fake_cfg(tmp_path)
    digests = wdata.list_digests(cfg=cfg)
    assert [d["date"] for d in digests] == ["2026-08-26", "2026-08-25"]
    assert wdata.read_digest("2026-08-25", cfg).startswith("## 今日重点")
    assert wdata.read_digest("1999-01-01", cfg) is None
    assert wdata.digest_matches("2026-08-26", "OpenAI", cfg)
    assert not wdata.digest_matches("2026-08-26", "不存在词", cfg)
    assert "OpenAI" in wdata.search_snippet("2026-08-26", "OpenAI", cfg)


# ---------------- 跨进程锁 ----------------

def test_file_lock(tmp_path):
    from workbench.core.lock import FileLock
    lock_path = tmp_path / ".digest.lock"
    with FileLock(lock_path) as l1:
        assert l1.acquired
        with FileLock(lock_path) as l2:
            assert not l2.acquired   # 第二个拿不到
        assert l1.acquired           # 释放 l2 不影响 l1
    # 全部释放后可再拿
    with FileLock(lock_path) as l3:
        assert l3.acquired


def test_file_lock_stale(tmp_path):
    import json, os, time
    from workbench.core.lock import FileLock
    lock_path = tmp_path / ".digest.lock"
    lock_path.write_text(json.dumps({"pid": 99999999, "started": time.time()}), encoding="utf-8")
    with FileLock(lock_path, stale_seconds=3600) as lock:
        assert lock.acquired  # 属主进程不存在 → 判定陈旧 → 自动回收


# ---------------- AppTest 冒烟（真实渲染默认页） ----------------

@pytest.mark.filterwarnings("ignore")
def test_app_boots():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception


def test_webui_triggers_module_discovery():
    """回归：Web 端导入后必须注册 news_digest，否则后台生成报"未知模块"。"""
    import workbench.webui  # noqa: F401  触发注册
    from workbench.core import registry
    assert registry.get_module("news_digest") is not None, "news_digest 未注册！"


# ---------------- LLM 调用路径（mock OpenAI 兼容服务器） ----------------

def test_llm_chat_path_works():
    """用本地 mock 服务器验证 llm_chat 完整调用链（不依赖真实 key）。"""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from workbench.modules.news_digest.distill import llm_chat

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            assert body["model"] == "mock-model"
            assert body["messages"][0]["role"] == "system"
            resp = {"choices": [{"message": {"content": "## 今日重点\n- mock 简报内容"}}]}
            data = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # 静默
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        out = llm_chat({"base_url": f"http://127.0.0.1:{port}/v1", "model": "mock-model"},
                       "system-msg", "user-msg")
        assert out == "## 今日重点\n- mock 简报内容"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_llm_fallback_digest():
    """LLM 不可用时本地兜底应产出清晰简报，并带失败原因。"""
    from workbench.modules.news_digest.distill import fallback_digest
    text = fallback_digest([{"title": "测试新闻", "source_name": "Mock",
                            "summary": "内容", "link": "http://x"}],
                           reason="401 Unauthorized")
    assert "测试新闻" in text
    assert "http://x" in text
    assert "本地兜底" in text
    assert "401 Unauthorized" in text  # 原因必须可见
    # 无原因时也不报错
    assert fallback_digest([])  # 空列表兜底


def test_sources_in_text_detects_multi_source():
    """多源校验：能识别正文引用了哪些来源（含短名匹配）。"""
    from workbench.modules.news_digest.distill import _sources_in_text
    items = [
        {"source_name": "华尔街见闻"},
        {"source_name": "The Verge"},
        {"source_name": "Reuters (via Google News)"},
        {"source_name": "TechCrunch"},
    ]
    text = "## 今日重点\n- 标题（华尔街见闻）\n- 标题（The Verge）\n- 标题（Reuters）"
    used = _sources_in_text(text, items)
    assert "华尔街见闻" in used
    assert "The Verge" in used
    assert "Reuters (via Google News)" in used  # 通过短名 "Reuters" 匹配到
    assert "TechCrunch" not in used


def test_dedupe_without_store(tmp_path):
    """store=None（强制重新生成）时不做历史去重。"""
    from workbench.modules.news_digest import cleaner
    items = [{"hash": "a", "title": "OpenAI 发布新模型", "weight": 1.0},
             {"hash": "b", "title": "苹果发布新手机", "weight": 0.9}]
    kept = cleaner.dedupe(items, store=None, threshold=0.55)
    assert len(kept) == 2  # 即使是"已见过"的 hash 也保留


def test_dotenv_override_refreshes(tmp_path, monkeypatch):
    """回归：.env 必须覆盖进程内已存在的环境变量（否则长驻服务换 key 后 401）。"""
    import os
    from dotenv import load_dotenv
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_OVERRIDE_KEY=new_value\n", encoding="utf-8")
    os.environ["TEST_OVERRIDE_KEY"] = "old_value"
    try:
        load_dotenv(env_file, override=True)
        assert os.environ["TEST_OVERRIDE_KEY"] == "new_value"
    finally:
        os.environ.pop("TEST_OVERRIDE_KEY", None)
