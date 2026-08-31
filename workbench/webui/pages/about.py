"""关于页：模块列表、运行路径、部署说明。"""
from __future__ import annotations

import streamlit as st

from workbench import __version__
from workbench.core import registry

from .. import config_editor as ce
from .. import context as wctx


def render() -> None:
    st.title("ℹ️ 关于")

    st.subheader("🧩 已注册模块")
    for m in registry.all_modules():
        st.markdown(f"- **{m.id}** — {m.name}（配置段：`{m.config_section}`）")
    st.caption("新增模块：在 workbench/modules/ 下新建包并调用 register() 即可自动接入。")

    st.subheader("📁 运行信息")
    cfg = wctx.get_cfg()
    st.json({
        "版本": __version__,
        "数据目录": cfg.get("app", {}).get("data_dir"),
        "状态文件": cfg["paths"]["status"],
        "简报输出": cfg["news_digest"].get("output_dir"),
        "配置文件": str(ce.CONFIG_PATH),
        "数据源文件": str(ce.FEEDS_PATH),
        "环境变量文件": str(ce.ENV_PATH),
    })

    st.subheader("☁️ 云端部署提示")
    st.markdown(
        """
- **Streamlit Community Cloud / Render / Railway 免费版的文件系统是临时的**：配置中心
  的写盘修改在实例重启后丢失。云端请优先使用平台 Secrets（环境变量），它们优先级最高。
- 每日定时推送请继续用 **GitHub Actions**（`.github/workflows/digest.yml`，电脑无需开机），
  Web 端负责查看 / 搜索 / 手动触发。
- 数据持久化：免费云上 `data/` 为临时目录；如需长期保留历史简报，可开启付费磁盘
  （Railway Volume / Render Disk / Fly Volume），或把输出目录指向外部存储。
"""
    )
