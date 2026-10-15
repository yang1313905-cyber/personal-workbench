"""Web 运行时环境识别与 Secrets 桥接。

两件事：
1. ``bridge_secrets_to_env()``：把 Streamlit Cloud 的 ``[env]`` Secrets 注入环境变量，
   这样配置文件里的 ``${SMTP_PASSWORD}`` 之类插值在云端也能生效，且**不需要把 .env 放进仓库**。
2. ``is_hosted()``：判断是否运行在云端托管环境。登录网关据此决定「没有配置凭据时是否拒绝服务」。
"""
from __future__ import annotations

import os
from pathlib import Path

_TRUTHY = {"1", "true", "yes", "on"}

# Streamlit Community Cloud 会注入/生成这些特征
_CLOUD_ENV_KEYS = ("STREAMLIT_SHARING_MODE", "IS_STREAMLIT_CLOUD", "STREAMLIT_CLOUD")


def is_hosted() -> bool:
    """是否运行在云端托管环境（而不是本机）。

    判断信号（任一命中即视为云端）：
    - 显式设置 ``APP_HOSTED=1``（部署到 Render/Fly 等其它平台时请设置）
    - Streamlit Community Cloud 的特征变量
    - 存在 ``/mount/src``（Streamlit Cloud 挂载仓库的位置）
    """
    if os.environ.get("APP_HOSTED", "").strip().lower() in _TRUTHY:
        return True
    if any(os.environ.get(k) for k in _CLOUD_ENV_KEYS):
        return True
    try:
        if Path("/mount/src").exists():
            return True
    except OSError:
        pass
    return False


def _iter_secret_env():
    """从 st.secrets 的 [env] 小节取出键值对；取不到就返回空。"""
    try:
        import streamlit as st  # 延迟导入：CLI / worker 不会用到本模块
        section = st.secrets.get("env")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001  没有 secrets 文件 / 非 Streamlit 运行时
        return []
    if not section:
        return []
    try:
        return [(str(k), str(v)) for k, v in dict(section).items() if v is not None]
    except Exception:  # noqa: BLE001
        return []


def bridge_secrets_to_env() -> int:
    """把 Secrets 里的 [env] 注入 os.environ（不覆盖已存在的真实环境变量）。

    返回注入的键数量。必须在读取配置之前调用（app.py 最前面）。
    """
    injected = 0
    for key, value in _iter_secret_env():
        if not key:
            continue
        if os.environ.get(key):
            continue
        os.environ[key] = value
        injected += 1
    return injected


def masked(value: str, keep: int = 4) -> str:
    """密钥打码显示：只保留末 keep 位。"""
    v = str(value or "")
    if not v:
        return ""
    if len(v) <= keep:
        return "*" * len(v)
    return "*" * (len(v) - keep) + v[-keep:]
