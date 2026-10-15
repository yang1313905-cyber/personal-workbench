"""个人智能工作台 · Web 管理界面（Streamlit 入口）。

本地运行：  streamlit run app.py          （默认 http://localhost:8501）
云端部署：  Streamlit Community Cloud（见 AUTOMATION.md / README）

安全：入口先经过登录网关（workbench/webui/auth.py）。
- 云端缺少凭据时**拒绝服务**，避免工作台与密钥被公开访问；
- 本机未配置凭据时直接放行（沿用系统登录保护）；
- 角色决定可见页面（viewer 看不到配置中心与运行日志）。

业务核心（抓取/蒸馏/推送/调度）完全复用 workbench 现有模块，零改动。
"""
from __future__ import annotations

import streamlit as st

# 必须放在第一个 st 调用
st.set_page_config(
    page_title="个人智能工作台",
    page_icon="🧰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 把云端 Secrets 的 [env] 注入环境变量（必须早于任何配置读取）
from workbench.webui.runtime import bridge_secrets_to_env  # noqa: E402

bridge_secrets_to_env()

from workbench.webui.auth import login_gate, logout_button  # noqa: E402
from workbench.webui.pages_registry import pages_for  # noqa: E402
from workbench.webui.theme import APPLE_CSS  # noqa: E402

# Apple 风格主题
st.markdown(APPLE_CSS, unsafe_allow_html=True)

# ---------------- 登录网关（未登录会渲染登录页并 st.stop） ----------------
user = login_gate()

# ---------------- 侧边栏 隐藏 / 重现 ----------------
if "sidebar_hidden" not in st.session_state:
    st.session_state.sidebar_hidden = False

if st.session_state.sidebar_hidden:
    # 隐藏侧边栏：主区域全宽，左上角提供"重现"按钮
    st.markdown(
        '<style>[data-testid="stSidebar"]{display:none !important;}</style>',
        unsafe_allow_html=True,
    )
    col_btn, _ = st.columns([1, 8])
    if col_btn.button("☰ 侧边栏", help="重新显示侧边栏", use_container_width=True):
        st.session_state.sidebar_hidden = False
        st.rerun()
else:
    # 侧边栏顶部品牌区 + 隐藏按钮
    with st.sidebar:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;padding:4px 6px 10px;">'
            '<span style="font-size:24px;">🧰</span>'
            '<span style="font-weight:700;font-size:1.08rem;color:#1d1d1f;'
            'letter-spacing:-0.01em;">个人智能工作台</span></div>',
            unsafe_allow_html=True,
        )
        if st.button("🙈 隐藏侧边栏", use_container_width=True,
                     help="隐藏后主区域全宽显示，点击左上角「☰」可恢复"):
            st.session_state.sidebar_hidden = True
            st.rerun()

        st.caption(
            f"👤 {user.get('display') or user.get('username')} · "
            f"{'管理员' if user.get('role') == 'admin' else '只读'}"
            + ("（本机免登录）" if user.get("local") else "")
        )
        logout_button()

nav = st.navigation(pages_for(user.get("role", "viewer")), position="sidebar", expanded=True)
nav.run()
