"""简报详情页：完整查看某一天简报，URL 带 ?date= 参数（可手机分享）。"""
from __future__ import annotations

import streamlit as st

from .. import data as wdata


def render() -> None:
    st.title("📄 简报详情")

    dates = wdata.list_digest_dates()
    if not dates:
        st.info("暂无历史简报。请先到首页生成今日简报。")
        return

    # 优先取 URL 参数（分享链接），否则取最近一期
    sel = st.query_params.get("date") or dates[0]
    if sel not in dates:
        sel = dates[0]

    sel = st.selectbox("📅 选择日期", dates, index=dates.index(sel), key="detail_date")
    if sel != st.query_params.get("date"):
        st.query_params["date"] = sel  # 同步到 URL，方便分享

    content = wdata.read_digest(sel)
    if not content:
        st.warning("该日简报文件不存在")
        return

    # 推送记录
    rec = wdata.digest_record(sel)
    if rec:
        channels = "、".join(rec["channels"]) if rec["channels"] else "（无推送记录）"
        st.caption(f"推送渠道：{channels}　·　生成于 {rec['created_at']}（UTC）")

    st.markdown(content)
    st.download_button("⬇️ 下载 Markdown", content,
                       file_name=f"digest-{sel}.md", use_container_width=True)
