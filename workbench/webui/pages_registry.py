"""st.Page 注册表：Web 站点页面清单。

新增页面三步：
    1. workbench/webui/pages/ 下新建模块，实现 render() 函数
    2. 在此 import 并注册 st.Page
    3. （可选）sidebar 默认即展示
"""
from __future__ import annotations

import streamlit as st

from .pages import about, config_center, dashboard, detail, distill_center
from .pages import history, logs, push_center, sources

PAGES = {
    "dashboard": st.Page(dashboard.render, title="首页仪表盘", icon="📊",
                         url_path="dashboard", default=True),
    "distill": st.Page(distill_center.render, title="蒸馏中心", icon="🧠",
                       url_path="distill"),
    "push": st.Page(push_center.render, title="推送中心", icon="📡",
                    url_path="push"),
    "sources": st.Page(sources.render, title="新闻源管理", icon="📰",
                       url_path="sources"),
    "detail": st.Page(detail.render, title="简报详情", icon="📄", url_path="detail"),
    "history": st.Page(history.render, title="历史简报", icon="🗂️", url_path="history"),
    "config": st.Page(config_center.render, title="配置中心", icon="⚙️", url_path="config"),
    "logs": st.Page(logs.render, title="运行日志", icon="📜", url_path="logs"),
    "about": st.Page(about.render, title="关于", icon="ℹ️", url_path="about"),
}
