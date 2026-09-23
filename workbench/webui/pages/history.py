"""历史简报页：全文搜索 + 分页浏览。"""
from __future__ import annotations

import streamlit as st

from .. import data as wdata
from ..nav import go

PAGE_SIZE = 20


def render() -> None:
    st.title("🗂️ 历史简报")

    keyword = st.text_input("🔍 搜索关键词（匹配简报正文）", key="history_q")

    all_digests = wdata.list_digests()
    if keyword.strip():
        kw = keyword.strip()
        results = []
        for d in all_digests:
            if wdata.digest_matches(d["date"], kw):
                d["snippet"] = wdata.search_snippet(d["date"], kw)
                results.append(d)
    else:
        results = all_digests

    st.caption(f"共 **{len(results)}** 篇" + (f"（匹配「{keyword.strip()}」）" if keyword.strip() else ""))

    if not results:
        st.info("没有找到匹配的简报")
        return

    # 分页
    page = st.session_state.get("hist_page", 1)
    total_pages = max(1, -(-len(results) // PAGE_SIZE))
    if page > total_pages:
        page = total_pages
        st.session_state["hist_page"] = page

    for d in results[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]:
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{d['date']}**　{d['size_kb']}KB · {d['mtime']}")
                if d.get("snippet"):
                    st.caption(f"🔍 …{d['snippet']}")
            if col2.button("查看", key=f"hist_{d['date']}", use_container_width=True):
                go("detail", date=d["date"])

    if total_pages > 1:
        col_prev, col_info, col_next = st.columns([1, 2, 1])
        if col_prev.button("◀ 上一页", disabled=(page <= 1), use_container_width=True):
            st.session_state["hist_page"] = page - 1
            st.rerun()
        col_info.markdown(f"<div style='text-align:center'>第 {page} / {total_pages} 页</div>",
                          unsafe_allow_html=True)
        if col_next.button("下一页 ▶", disabled=(page >= total_pages), use_container_width=True):
            st.session_state["hist_page"] = page + 1
            st.rerun()
