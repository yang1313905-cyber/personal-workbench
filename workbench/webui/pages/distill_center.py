"""蒸馏中心：新闻蒸馏母平台。

多源抓取 → 清洗去重 → LLM 蒸馏 → 简报推送 的全流程控制台：
数据源总览、LLM 引擎状态与连通性测试、流水线运行状态、快捷生成。
"""
from __future__ import annotations

import streamlit as st

from .. import context as wctx
from .. import data as wdata
from .. import jobs


def test_llm(cfg: dict):
    """真实连通性测试：发起一次最小 chat 调用（约 10 token），能暴露 key/余额/模型问题。

    关键：直接读 .env 里的最新 key 覆盖缓存配置，避免长驻进程的环境变量缓存
    导致测试到旧 key（401 问题）。
    """
    from .. import config_editor as ce
    from workbench.modules.news_digest.distill import llm_chat
    llm = dict(cfg.get("llm", {}))
    fresh_key = ce.env_value("LLM_API_KEY")
    if fresh_key:
        llm["api_key"] = fresh_key
    if not llm.get("base_url") or not llm.get("model"):
        return False, "未配置 base_url / model"
    try:
        out = llm_chat({**llm, "max_tokens": 10, "temperature": 0.0},
                       "You are a test.", "请只回复两个字：正常")
        return True, f"调用成功，模型返回：{out[:40]!r}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _pipeline_steps(status: dict) -> list:
    fetched = status.get("items_fetched")
    kept = status.get("items_kept")
    used_llm = status.get("used_llm")
    output = status.get("output_file")
    push = status.get("push")

    steps = [
        ("① 多源抓取", f"{fetched} 条" if fetched is not None else "未运行",
         "wb-step-done" if fetched else "wb-step-muted"),
        ("② 清洗去重", f"{kept} 条保留" if kept is not None else "—",
         "wb-step-done" if kept else "wb-step-muted"),
        ("③ LLM 蒸馏", "✅ 模型生成" if used_llm is True else ("🔧 本地兜底" if used_llm is False else "—"),
         "wb-step-done" if used_llm is True else "wb-step-warn"),
        ("④ 简报输出", "已存档" if output else "—",
         "wb-step-done" if output else "wb-step-muted"),
        ("⑤ 推送分发", f"{sum(1 for v in push.values() if v)}/{len(push)} 成功"
         if push else "—", "wb-step-done" if push and any(push.values()) else "wb-step-muted"),
    ]
    return steps


def render() -> None:
    st.title("🧠 新闻蒸馏中心")
    st.caption("新闻蒸馏母平台：数据源 → 清洗去重 → LLM 蒸馏 → 推送 全流程可视化控制台。")

    cfg = wctx.get_cfg()
    status = wdata.read_status()

    # ---------------- 快捷操作 ----------------
    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("🚀 立即生成简报", type="primary", use_container_width=True):
            if jobs.any_running():
                st.warning("已有生成任务在运行")
            else:
                jid = jobs.start_digest(no_push=False)
                if jid:
                    st.toast("生成任务已启动，进度见「首页仪表盘」")
                    st.session_state["job_id"] = jid
                    st.rerun()
                else:
                    st.error("已有任务在运行（CLI/定时/Web）")
    with col_b:
        st.caption("后台异步执行，耗时通常 1-3 分钟；完成后自动推送并归档到 data/output/")

    # ---------------- 流水线状态 ----------------
    st.subheader("⚙️ 蒸馏流水线（最近一次运行）")
    steps = _pipeline_steps(status)
    cols = st.columns(len(steps))
    for col, (name, value, cls) in zip(cols, steps):
        with col:
            st.markdown(
                f'<div class="wb-step-card" style="background:#fff;border-radius:16px;'
                f'border:1px solid rgba(0,0,0,0.06);padding:0.9rem 0.6rem;text-align:center;'
                f'box-shadow:0 2px 10px rgba(0,0,0,0.04);">'
                f'<div style="font-size:0.82rem;color:#86868b;margin-bottom:0.35rem;">{name}</div>'
                f'<div class="{cls}" style="font-size:0.95rem;">{value}</div></div>',
                unsafe_allow_html=True,
            )
    if not status.get("digest_date"):
        st.caption("尚无运行记录 —— 点击上方「立即生成」开始第一次蒸馏。")

    # LLM 失败原因直接展示（清晰可排查）
    llm_error = status.get("llm_error")
    if llm_error:
        st.error(f"⚠️ **LLM 蒸馏失败**：`{llm_error[:300]}`\n\n"
                 "请检查「配置中心 → LLM 参数」的 Base URL / 模型 / API Key，"
                 "改好后回首页勾选「强制重新生成」。")

    # ---------------- LLM 引擎 ----------------
    st.subheader("🤖 LLM 蒸馏引擎")
    llm = cfg.get("llm", {})
    col1, col2, col3, col4 = st.columns([1.6, 2.2, 1.2, 1])
    col1.metric("模型", llm.get("model", "—"))
    col2.metric("Base URL", str(llm.get("base_url", "—")).replace("https://", "").replace("http://", ""))
    col3.metric("Temperature", llm.get("temperature", "—"))
    if col4.button("🔌 测试连接", use_container_width=True):
        ok, detail = test_llm(cfg)
        if ok:
            st.success(f"✅ LLM 连接正常 — {detail}")
        else:
            st.error(f"❌ LLM 连接失败：{detail}")

    # ---------------- 数据源总览 ----------------
    st.subheader("🌐 数据源总览")
    sources = cfg.get("feeds", [])
    failed = {e.get("source") for e in (status.get("fetch_errors") or [])}
    rows = []
    for s in sources:
        sid = s.get("id")
        if not s.get("enabled", True):
            state_icon = "⛔ 停用"
        elif sid in failed:
            state_icon = "❌ 失败"
        else:
            state_icon = "✅ 正常"
        rows.append({"状态": state_icon, "ID": sid, "名称": s.get("name"),
                     "语言": s.get("lang"), "权重": s.get("weight"), "类型": s.get("kind")})
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption("❌ = 最近一次运行抓取失败（详见「运行日志」）；源管理请到「配置中心 → 新闻源」。")
    else:
        st.caption("未配置任何数据源 —— 到「配置中心 → 新闻源」添加。")

    # ---------------- 最近运行详情 ----------------
    with st.expander("🗒️ 最近一次运行详情"):
        st.json(status, expanded=False)
