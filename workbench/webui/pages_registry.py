"""st.Page 注册表：Web 站点页面清单 + 角色可见性。

新增页面三步：
    1. workbench/webui/pages/ 下新建模块，实现 render() 函数
    2. 在 ``_PAGE_SPECS`` 里加一行
    3. （可选）sidebar 默认即展示

为什么页面对象要「运行时构建 + 仅在脚本运行上下文内缓存」
--------------------------------------------------------
``st.Page()`` 必须在 Streamlit 的脚本运行上下文里创建：在裸模式（例如被
单元测试 import、或命令行里调用）创建的 Page 对象缺少内部属性，
再交给 ``st.navigation`` 就会抛 ``AttributeError: '_page'``。
因此这里把「页面定义」与「st.Page 对象」拆开：
- ``page_keys_for(role)`` 是纯逻辑，不需要 Streamlit，可直接单测；
- ``build_pages()`` 只在运行上下文里缓存对象，裸模式一律现造现用、不污染缓存。
"""
from __future__ import annotations

from typing import Dict, List

import streamlit as st

from .pages import about, config_center, dashboard, detail, distill_center
from .pages import history, logs, push_center, sources

# key, render, title, icon, url_path, default
_PAGE_SPECS = [
    ("dashboard", dashboard.render, "首页仪表盘", "📊", "dashboard", True),
    ("distill", distill_center.render, "蒸馏中心", "🧠", "distill", False),
    ("push", push_center.render, "推送中心", "📡", "push", False),
    ("sources", sources.render, "新闻源管理", "📰", "sources", False),
    ("detail", detail.render, "简报详情", "📄", "detail", False),
    ("history", history.render, "历史简报", "🗂️", "history", False),
    ("config", config_center.render, "配置中心", "⚙️", "config", False),
    ("logs", logs.render, "运行日志", "📜", "logs", False),
    ("about", about.render, "关于", "ℹ️", "about", False),
]

PAGE_KEYS: List[str] = [spec[0] for spec in _PAGE_SPECS]

# 仅管理员可见：
# - config：可读写 .env / 改密钥；logs：可能含推送错误细节
# - distill / push：会真正调用 LLM、发送测试消息（有成本与副作用）
ADMIN_ONLY = {"config", "logs", "distill", "push"}

_CACHE: Dict[str, st.Page] = {}


def _in_script_run() -> bool:
    """当前是否处于 Streamlit 脚本运行上下文。"""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:  # noqa: BLE001
        return False


def build_pages() -> Dict[str, st.Page]:
    """构建全部 st.Page；只在运行上下文内缓存。"""
    global _CACHE
    if _CACHE:
        return _CACHE
    pages = {
        key: st.Page(render, title=title, icon=icon, url_path=url_path, default=default)
        for key, render, title, icon, url_path, default in _PAGE_SPECS
    }
    if _in_script_run():
        _CACHE = pages
    return pages


def page_for(key: str) -> st.Page:
    """按 key 取 Page 对象（供 nav.go 程序化跳转使用）。"""
    return build_pages()[key]


def page_keys_for(role: str) -> List[str]:
    """按角色返回可见页面 key（纯逻辑，无需 Streamlit）。"""
    if role == "admin":
        return list(PAGE_KEYS)
    return [k for k in PAGE_KEYS if k not in ADMIN_ONLY]


def pages_for(role: str) -> List[st.Page]:
    """按角色返回可见页面对象列表（保持注册顺序）。"""
    pages = build_pages()
    return [pages[k] for k in page_keys_for(role)]

def is_admin(role: str) -> bool:
    return role == "admin"
