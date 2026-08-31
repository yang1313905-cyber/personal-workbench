"""运行日志页：按级别过滤 + 自动刷新。"""
from __future__ import annotations

import streamlit as st

from .. import data as wdata
from .. import context as wctx

LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"]


def render() -> None:
    st.title("📜 运行日志")

    max_lines = int(wctx.get_cfg().get("webui", {}).get("max_log_lines", 500))
    level = st.selectbox("级别过滤", LEVELS, index=2)
    auto = st.toggle("自动刷新（每 5 秒）", value=False)

    col1, col2 = st.columns([1, 5])
    col2.caption(f"日志文件：`{wdata.log_path()}`（滚动 5MB × 3）")

    if auto:

        @st.fragment(run_every=5.0)
        def _auto_logs() -> None:
            st.code(wdata.tail_log(n=max_lines, level=level))

        _auto_logs()
    else:
        st.code(wdata.tail_log(n=max_lines, level=level))

    if st.button("🔄 刷新"):
        st.rerun()
