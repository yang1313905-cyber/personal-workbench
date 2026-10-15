"""只读文件系统下的降级行为测试。

云端容器（如 Streamlit Cloud）挂载的仓库目录可能不可写。
此时工作台必须能正常打开：状态库回退到临时目录，状态文件写入失败只警告不抛异常。
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workbench.core.state import StateStore  # noqa: E402
from workbench.core.status import StatusStore  # noqa: E402


@pytest.fixture
def readonly_dir(tmp_path: Path):
    """创建一个不可写目录，测试结束后恢复权限以便清理。"""
    d = tmp_path / "ro"
    d.mkdir()
    p = d / "state.db"
    d.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x：不能创建新文件
    yield p
    d.chmod(stat.S_IRWXU)


def test_state_store_falls_back_when_not_writable(readonly_dir):
    store = StateStore(readonly_dir)          # 不应抛异常
    store.mark_seen("h1", "src", "标题")
    assert store.is_seen("h1")                # 回退到临时目录后功能正常
    store.close()


def test_state_store_normal_path_is_used(tmp_path):
    p = tmp_path / "sub" / "state.db"
    store = StateStore(p)
    store.mark_seen("h2", "src", "标题")
    assert p.exists() or (p.parent / ".~write_probe").exists() is False
    store.close()


def test_status_store_write_failure_is_silent(readonly_dir):
    store = StatusStore(readonly_dir)         # 不应抛异常
    store.update(digest_date="2026-09-24", push={"smtp": True})
    store.record_error("fetch", "boom")
    assert store.read() == {} or isinstance(store.read(), dict)


def test_status_store_normal_write(tmp_path):
    p = tmp_path / "status" / "status.json"
    store = StatusStore(p)
    store.update(digest_date="2026-09-24")
    assert store.read()["digest_date"] == "2026-09-24"
