"""进程内资源单例：Streamlit 每次交互都会重跑脚本，必须缓存重量级资源。

- st.cache_resource 保证同一进程内只创建一次（跨 rerun、跨会话）
- 配置中心保存配置后调用 invalidate() 强制重建
- 注意：后台生成任务(jobs.py)在独立线程里自行创建 Context，不共享这里的实例
"""
from __future__ import annotations

import streamlit as st

from workbench.core.config import load_config
from workbench.core.context import Context
from workbench.core.logging import setup_logging
from workbench.core.state import StateStore
from workbench.core.status import StatusStore


@st.cache_resource(show_spinner=False)
def _resources() -> tuple:
    cfg = load_config()
    state = StateStore(cfg["paths"]["state"])
    status = StatusStore(cfg["paths"]["status"])
    log = setup_logging(cfg)
    return cfg, state, status, log


def get_cfg() -> dict:
    return _resources()[0]


def get_state() -> StateStore:
    return _resources()[1]


def get_status() -> StatusStore:
    return _resources()[2]


def get_log() -> object:
    return _resources()[3]


def invalidate() -> None:
    """配置被修改后调用，强制下一次读取重新加载。"""
    st.cache_resource.clear()


def make_context() -> Context:
    """供后台任务使用：每次独立创建（配置取最新值）。"""
    cfg = load_config()
    logger = setup_logging(cfg)
    state = StateStore(cfg["paths"]["state"])
    status = StatusStore(cfg["paths"]["status"])
    return Context(config=cfg, state=state, status=status, log=logger)
