"""首页仪表盘：今日简报 + 最近简报列表 + 一键生成 + 运行状态。"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from .. import data as wdata
from .. import jobs
from ..nav import go


def render() -> None:
    today = dt.date.today().isoformat()

    # Apple 风格 Hero 横幅
    st.markdown(
        f"""
        <div class="wb-hero">
          <div class="wb-hero-title">🧰 个人智能工作台</div>
          <div class="wb-hero-sub">News Digest · 多源新闻抓取 → LLM 蒸馏 → 定时推送</div>
          <span class="wb-badge">今日 {today}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    status = wdata.read_status()
    today_digest = wdata.read_digest(today)

    # ---------------- 状态指标 ----------------
    push = status.get("push") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("今日抓取", status.get("items_fetched", "—"))
    c2.metric("保留条数", status.get("items_kept", "—"))
    used_llm = status.get("used_llm")
    c3.metric("LLM 生成", "✅" if used_llm is True else ("🔧 兜底" if used_llm is False else "—"))
    c4.metric("推送成功", f"{sum(1 for v in push.values() if v)}/{len(push)}"
              if push else ("—" if status.get("digest_date") != today else "0/0"))

    # ---------------- 手动生成 ----------------
    st.subheader("🚀 手动生成")
    with st.container(border=True):
        col_a, col_b = st.columns([1, 3])
        with col_a:
            no_push = st.checkbox("仅生成不推送", value=False,
                                  help="等价于 CLI 的 --no-push")
            force = st.checkbox("强制重新生成", value=False,
                                help="跳过历史去重，同一天可再次生成完整简报（默认一天一份）")
            if st.button("⚡ 立即生成今日简报", type="primary", use_container_width=True):
                if jobs.any_running():
                    st.warning("已有生成任务正在运行，请稍候…")
                else:
                    job_id = jobs.start_digest(no_push=no_push, force=force)
                    if job_id:
                        st.session_state["job_id"] = job_id
                        st.toast("🚀 生成任务已启动")
                        st.rerun()
                    else:
                        st.error("已有任务在运行（可能来自 CLI 或定时任务），请稍后再试")
        with col_b:
            st.caption("点击后**后台异步生成**（抓取 → 去重 → LLM 蒸馏 → 推送），"
                       "与 CLI / 定时任务共用同一套流水线与防重锁。"
                       "生成耗时通常 1-3 分钟，可在下方实时查看进度。")

    # ---------------- 生成进度 ----------------
    @st.fragment(run_every=2.0)
    def _progress() -> None:
        job_id = st.session_state.get("job_id")
        if not job_id:
            return
        state = jobs.job_state(job_id)
        if not state:
            return
        if state["status"] == "running":
            st.info(f"⏳ 正在生成… 已耗时 **{state['elapsed']:.0f}s**（页面每 2 秒自动刷新）")
        elif state["status"] == "done":
            st.success("✅ 生成完成")
            with st.expander("生成结果详情", expanded=False):
                st.json(state["result"])
            if st.button("🔄 刷新页面查看最新简报"):
                st.rerun()
        elif state["status"] == "error":
            st.error(f"❌ 生成失败：{state['error']}")
            if st.button("🔄 清除任务状态"):
                st.session_state.pop("job_id", None)
                st.rerun()

    _progress()

    # ---------------- 今日简报 ----------------
    st.subheader("📰 今日简报")
    if today_digest:
        lines = today_digest.splitlines()
        preview = "\n".join(lines[:40])
        st.markdown(preview)
        col_l, col_r = st.columns(2)
        if col_l.button("📄 查看完整简报", type="primary", use_container_width=True):
            go("detail", date=today)
        col_r.download_button("⬇️ 下载 Markdown", today_digest,
                              file_name=f"digest-{today}.md", use_container_width=True)
        if len(lines) > 40:
            st.caption(f"（已预览前 40 行，全文共 {len(lines)} 行）")
    else:
        st.info("今日简报尚未生成，点击上方「立即生成」按钮开始。")

    # ---------------- 最近简报 ----------------
    st.subheader("🕘 最近简报")
    recent = wdata.list_digests(limit=5)
    if not recent:
        st.caption("暂无历史简报")
    for d in recent:
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            col1.markdown(f"**{d['date']}**　{d['size_kb']}KB · {d['mtime']}")
            if col2.button("查看", key=f"recent_{d['date']}", use_container_width=True):
                go("detail", date=d["date"])

    # ---------------- 运行状态 / 错误 ----------------
    with st.expander("🩺 运行状态与最近错误"):
        st.json(status, expanded=False)
        st.caption(f"状态文件：{wdata.status_path()}")
