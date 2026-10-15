"""登录网关测试：哈希、角色、以及最关键的「未授权看不到业务页面 / 云端缺凭据拒绝服务」。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workbench.webui import auth  # noqa: E402

APP = ROOT / "app.py"
PASSWORD = "Qhlyzxm1208."

# 注意：不要在测试模块顶层 import pages_registry。
# st.Page 必须在 Streamlit 的脚本运行上下文里创建；在裸模式下导入会缓存
# "半初始化"的 Page 对象，导致后续 AppTest 运行 app.py 时 st.navigation 报错。


# ---------------------------------------------------------------- 哈希

def test_hash_and_verify_roundtrip():
    h = auth.hash_password(PASSWORD)
    assert h.startswith("pbkdf2_sha256$")
    assert auth.verify_password(PASSWORD, h)
    assert not auth.verify_password(PASSWORD + "x", h)
    assert not auth.verify_password("", h)


def test_hash_is_salted_and_never_plaintext():
    h1, h2 = auth.hash_password(PASSWORD), auth.hash_password(PASSWORD)
    assert h1 != h2                      # 随机盐：同一密码哈希不同
    assert PASSWORD not in h1            # 绝不落明文


def test_verify_rejects_malformed_hash():
    for bad in ("", "plain", "md5$1$aa$bb", "pbkdf2_sha256$notanint$aa$bb"):
        assert not auth.verify_password(PASSWORD, bad)


# ---------------------------------------------------------------- 角色

def test_viewer_cannot_see_admin_pages():
    from workbench.webui.pages_registry import ADMIN_ONLY, PAGE_KEYS, page_keys_for

    assert page_keys_for("admin") == PAGE_KEYS
    viewer = page_keys_for("viewer")
    assert len(viewer) == len(PAGE_KEYS) - len(ADMIN_ONLY)
    assert ADMIN_ONLY == {"config", "logs", "distill", "push"}
    assert not (set(viewer) & ADMIN_ONLY)          # viewer 拿不到管理页


# ---------------------------------------------------------------- 失败限流

def test_brute_force_lockout(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "_FAILURE_FILE", tmp_path / "failures.json")
    monkeypatch.setattr(auth, "FAIL_DELAY", 0)
    assert auth.lock_remaining() == 0
    for _ in range(auth.MAX_FAILURES):
        auth.record_failure()
    assert auth.lock_remaining() > 0          # 达到阈值后锁定
    auth.clear_failures()
    assert auth.lock_remaining() == 0         # 登录成功后解除


# ---------------------------------------------------------------- 网关行为

def _all_text(at: AppTest) -> str:
    parts = []
    for attr in ("markdown", "error", "warning", "title", "header", "subheader", "info"):
        for el in getattr(at, attr, []) or []:
            parts.append(str(getattr(el, "value", "")))
    return " ".join(parts)


def test_cloud_without_credentials_refuses_service(monkeypatch):
    """云端 + 没有配置凭据 => 必须拒绝服务，且不能渲染任何业务页面。"""
    monkeypatch.setenv("APP_HOSTED", "1")
    monkeypatch.delenv("AUTH_PASSWORD_HASH", raising=False)

    at = AppTest.from_file(str(APP), default_timeout=90)
    at.run()

    assert not at.exception, at.exception
    assert "拒绝提供服务" in _all_text(at)
    assert "仪表盘" not in _all_text(at)          # 业务页面没有泄露出来


def test_cloud_with_credentials_requires_login(monkeypatch):
    """配置了凭据 => 未登录只能看到登录表单，看不到业务页面。"""
    monkeypatch.setenv("APP_HOSTED", "1")
    monkeypatch.setenv("AUTH_USERNAME", "Hannibal")
    monkeypatch.setenv("AUTH_PASSWORD_HASH", auth.hash_password(PASSWORD))
    monkeypatch.setattr(auth, "_FAILURE_FILE", Path("/tmp/_never_written.json"))

    at = AppTest.from_file(str(APP), default_timeout=90)
    at.run()

    assert not at.exception, at.exception
    labels = [i.label for i in at.text_input]
    assert "账号" in labels and "密码" in labels   # 登录表单存在
    assert "仪表盘" not in _all_text(at)           # 业务页面不可见


def test_local_without_credentials_allows_access(monkeypatch):
    """本机（非云端）未配置凭据时放行，但不应出现登录表单。"""
    monkeypatch.delenv("APP_HOSTED", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.setattr(auth, "is_hosted", lambda: False)

    at = AppTest.from_file(str(APP), default_timeout=90)
    at.run()

    assert not at.exception, at.exception
    assert "账号" not in [i.label for i in at.text_input]


def test_authenticated_session_reaches_business_pages(monkeypatch):
    """已登录会话（管理员）能进入业务页面。"""
    monkeypatch.setenv("APP_HOSTED", "1")
    monkeypatch.setenv("AUTH_USERNAME", "Hannibal")
    monkeypatch.setenv("AUTH_PASSWORD_HASH", auth.hash_password(PASSWORD))

    at = AppTest.from_file(str(APP), default_timeout=90)
    at.session_state["auth_user"] = {
        "username": "Hannibal", "display": "Hannibal", "role": "admin",
        "login_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    at.run()

    assert not at.exception, at.exception
    assert "账号" not in [i.label for i in at.text_input]   # 不再要求登录
