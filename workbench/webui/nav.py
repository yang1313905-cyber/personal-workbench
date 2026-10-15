"""页面导航助手：程序化跳转（带 URL 参数，便于手机分享链接）。

注意：页面对象由 pages_registry.build_pages() 在运行上下文内构建；
这里用函数内延迟导入避免循环依赖。
"""
from __future__ import annotations

import streamlit as st


def go(page_key: str, **params) -> None:
    """跳转到指定页面并携带 URL 查询参数，如 go('detail', date='2026-08-26')。"""
    from .pages_registry import page_for  # 延迟导入，避免循环依赖

    for k, v in params.items():
        st.query_params[k] = v
    st.switch_page(page_for(page_key))
