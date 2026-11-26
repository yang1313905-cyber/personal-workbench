"""Web 端简报阅读器：复用邮件同款编辑晨报排版，提升网页阅读体验。"""
from __future__ import annotations

import streamlit as st

from workbench.channels.markdown_email import md_to_html


def render_digest_html(markdown_text: str) -> None:
    """将简报 Markdown 渲染为卡片化阅读视图（XSS 安全，复用内联转义渲染器）。"""
    body_html = md_to_html(markdown_text or "")
    st.markdown(
        f'<div class="wb-digest-shell">{body_html}</div>',
        unsafe_allow_html=True,
    )
