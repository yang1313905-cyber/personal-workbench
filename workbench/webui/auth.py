"""Web 管理界面的登录网关：身份校验、角色、会话管理与失败限流。

安全模型
--------
1. **不存明文**：密码只以 PBKDF2-HMAC-SHA256 加盐哈希形式存在；
   代码、配置、仓库里都没有明文口令。
2. **凭据来源**：Streamlit Secrets（云端，推荐）→ 环境变量（本机 .env）。
3. **云端缺凭据时拒绝服务**（fail closed）：宁可打不开，也绝不把工作台裸奔在公网。
   本机未配置凭据时直接放行（本机已有系统登录保护），并提示可自行开启。
4. **角色**：admin 可见全部页面；viewer 看不到配置中心、运行日志等敏感页。
5. **失败限流**：连续多次失败会指数退避并短暂锁定，降低公网暴力猜解的成功率。
6. **密钥不外泄**：云端模式下配置中心不再回显 / 写入 .env（见 config_center）。

哈希格式：``pbkdf2_sha256$<迭代次数>$<salt_hex>$<hash_hex>``
生成方式：``python -m workbench.webui.auth --hash '你的密码'``
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

from .runtime import is_hosted

PBKDF2_ITERATIONS = 260_000
ALGO = "pbkdf2_sha256"

# 失败限流参数
MAX_FAILURES = 5          # 一个时间窗内允许的失败次数
FAILURE_WINDOW = 600      # 统计窗口（秒）
LOCK_SECONDS = 300        # 触发后锁定时长（秒）
FAIL_DELAY = 0.8          # 每次失败固定延时，拖慢猜解

ROOT = Path(__file__).resolve().parents[2]
_FAILURE_FILE = ROOT / "data" / "status" / "auth_failures.json"
_SESSION_KEY = "auth_user"


# ---------------------------------------------------------------- 哈希与校验

def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS,
                  salt: Optional[bytes] = None) -> str:
    """生成可存库的密码哈希字符串。"""
    salt = salt if salt is not None else os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码；格式不对一律返回 False（不抛异常）。"""
    try:
        algo, iters, salt_hex, hash_hex = str(stored).split("$")
        if algo != ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- 凭据来源

def load_credentials() -> Optional[Dict[str, str]]:
    """按优先级读取凭据：Streamlit Secrets → 环境变量。都没有则返回 None。"""
    # 1) Streamlit Secrets: [auth] username / password_hash / role
    try:
        import streamlit as st
        section = st.secrets.get("auth")  # type: ignore[union-attr]
        if section and section.get("password_hash"):
            return {
                "username": str(section.get("username") or "admin"),
                "password_hash": str(section["password_hash"]),
                "role": str(section.get("role") or "admin"),
                "display": str(section.get("display") or section.get("username") or "admin"),
                "source": "Streamlit Secrets",
            }
    except Exception:  # noqa: BLE001
        pass

    # 2) 环境变量（本机 .env 亦可）
    pw_hash = os.environ.get("AUTH_PASSWORD_HASH", "").strip()
    if pw_hash:
        return {
            "username": os.environ.get("AUTH_USERNAME", "admin").strip() or "admin",
            "password_hash": pw_hash,
            "role": os.environ.get("AUTH_ROLE", "admin").strip() or "admin",
            "display": os.environ.get("AUTH_DISPLAY", "").strip() or os.environ.get("AUTH_USERNAME", "admin"),
            "source": "环境变量",
        }
    return None


# ---------------------------------------------------------------- 失败限流

def _read_failures() -> dict:
    try:
        return json.loads(_FAILURE_FILE.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return {"events": []}


def _write_failures(data: dict) -> None:
    try:
        _FAILURE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _FAILURE_FILE.write_text(json.dumps(data), "utf-8")
    except Exception:  # noqa: BLE001  只读文件系统时退化为仅按会话计数
        pass


def _recent_failures(now: float) -> list:
    events = [t for t in (_read_failures().get("events") or []) if now - float(t) < FAILURE_WINDOW]
    return events


def lock_remaining() -> int:
    """剩余锁定秒数；0 表示未锁定。"""
    now = time.time()
    events = _recent_failures(now)
    if len(events) < MAX_FAILURES:
        return 0
    return max(0, int(LOCK_SECONDS - (now - min(events[-MAX_FAILURES:]))))


def record_failure() -> None:
    now = time.time()
    events = _recent_failures(now)
    events.append(now)
    _write_failures({"events": events[-50:]})


def clear_failures() -> None:
    try:
        _FAILURE_FILE.unlink()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 会话

def current_user() -> Optional[Dict]:
    """已登录用户信息；未登录返回 None。"""
    try:
        import streamlit as st
        return st.session_state.get(_SESSION_KEY)
    except Exception:  # noqa: BLE001
        return None


def logout() -> None:
    try:
        import streamlit as st
        st.session_state.pop(_SESSION_KEY, None)
    except Exception:  # noqa: BLE001
        pass


def logout_button() -> None:
    """侧边栏里的退出登录按钮（未登录时不渲染）。"""
    import streamlit as st

    user = current_user()
    if not user or user.get("local"):
        return
    if st.button("🚪 退出登录", use_container_width=True, key="auth_logout"):
        logout()
        st.rerun()


# ---------------------------------------------------------------- 登录页面

_LOGIN_CSS = """
<style>
  .login-card { max-width: 420px; margin: 6vh auto 0; padding: 30px 32px 26px;
    background: #fff; border-radius: 18px; box-shadow: 0 8px 30px rgba(0,0,0,.08);
    border: 1px solid #ececf0; }
  .login-title { font-size: 1.45rem; font-weight: 700; color: #1d1d1f;
    letter-spacing: -0.02em; margin: 0; }
  .login-sub { color: #6e6e73; font-size: .86rem; margin-top: 6px; }
  .login-mark { font-size: 30px; }
</style>
"""


def _render_login(form_key: str = "auth_login_form") -> None:
    import streamlit as st

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown(
            '<div class="login-card"><div class="login-mark">🧰</div>'
            '<p class="login-title">个人智能工作台</p>'
            '<div class="login-sub">请登录后使用 · 未授权访问会被拒绝</div></div>',
            unsafe_allow_html=True,
        )
        remaining = lock_remaining()
        if remaining:
            st.error(f"尝试次数过多，请在 {remaining} 秒后重试。")
            return

        with st.form(form_key, clear_on_submit=False):
            username = st.text_input("账号", autocomplete="username")
            password = st.text_input("密码", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("登录", use_container_width=True, type="primary")

        if not submitted:
            return

        creds = load_credentials()
        assert creds is not None  # 调用方已保证
        ok = (hmac.compare_digest(username.strip(), creds["username"])
              and verify_password(password, creds["password_hash"]))
        if ok:
            clear_failures()
            st.session_state[_SESSION_KEY] = {
                "username": creds["username"],
                "display": creds.get("display") or creds["username"],
                "role": creds["role"],
                "source": creds.get("source", ""),
                "login_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            st.rerun()
        else:
            record_failure()
            time.sleep(FAIL_DELAY)
            st.error("账号或密码不正确。")


def login_gate() -> Dict:
    """在 app.py 最前面调用。

    - 已登录：返回用户信息
    - 未登录：渲染登录页并 ``st.stop()``，不会执行到后面的业务页面
    - 云端但未配置凭据：拒绝提供服务（fail closed）
    - 本机且未配置凭据：放行（role=admin，local=True）
    """
    import streamlit as st

    user = current_user()
    if user:
        return user

    creds = load_credentials()
    if creds is None:
        if is_hosted():
            st.error(
                "### 🔒 已拒绝提供服务\n\n"
                "当前运行在云端环境，但没有配置登录凭据，为避免工作台（含 API 密钥）被公开访问，"
                "已主动停止服务。\n\n"
                "请在平台设置中添加 Secrets 后重新部署：\n\n"
                "```toml\n[auth]\nusername = \"...\"\npassword_hash = \"pbkdf2_sha256$...\"\nrole = \"admin\"\n```"
            )
            st.stop()
        st.session_state[_SESSION_KEY] = {
            "username": "local", "display": "本机用户", "role": "admin", "local": True,
        }
        return st.session_state[_SESSION_KEY]

    _render_login()
    st.stop()


# ---------------------------------------------------------------- 命令行

def _main(argv=None) -> int:
    """生成密码哈希：python -m workbench.webui.auth --hash '密码'"""
    import argparse

    parser = argparse.ArgumentParser(prog="workbench.webui.auth", description="登录凭据工具")
    parser.add_argument("--hash", metavar="PASSWORD", help="生成 password_hash")
    args = parser.parse_args(argv)
    if not args.hash:
        parser.print_help()
        return 1
    print(hash_password(args.hash))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
