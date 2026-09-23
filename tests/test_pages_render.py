"""页面渲染冒烟测试：逐个 AppTest 渲染所有页面，确认无异常。"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

PAGES_TO_TEST = [
    "dashboard", "distill", "push", "sources", "detail", "history", "config", "logs", "about",
]

# 页面 key → 模块名
_MODULE = {
    "dashboard": "dashboard",
    "distill": "distill_center",
    "push": "push_center",
    "sources": "sources",
    "detail": "detail",
    "history": "history",
    "config": "config_center",
    "logs": "logs",
    "about": "about",
}


@pytest.fixture(scope="module")
def page_app(tmp_path_factory):
    """生成一个小应用：根据 ?p= 参数渲染指定页面的 render()。"""
    lines = ["import streamlit as st"]
    for mod in sorted(set(_MODULE.values())):
        lines.append(f"from workbench.webui.pages import {mod}")
    lines.append('which = st.query_params.get("p", "dashboard")')
    lines.append("renderers = {")
    for key, mod in _MODULE.items():
        lines.append(f'    "{key}": {mod}.render,')
    lines.append("}")
    lines.append("renderers[which]()")
    app_file = tmp_path_factory.mktemp("app") / "page_app.py"
    app_file.write_text("\n".join(lines), encoding="utf-8")
    return app_file


@pytest.mark.filterwarnings("ignore")
@pytest.mark.parametrize("page", PAGES_TO_TEST)
def test_page_renders(page, page_app):
    at = AppTest.from_file(str(page_app), default_timeout=60)
    at.query_params["p"] = page
    at.run()
    assert not at.exception, at.exception
