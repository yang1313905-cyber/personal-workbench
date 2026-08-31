"""Web 管理界面（Streamlit）。

目录结构：
- context.py       资源单例（配置/状态库/状态文件，进程内缓存）
- data.py          简报/状态/日志数据访问
- jobs.py          后台生成任务（线程 + 跨进程锁）
- config_editor.py 配置中心读写（ruamel 保注释写 YAML，.env 读写）
- nav.py           页面导航助手
- pages_registry.py st.Page 注册表
- pages/           各页面 render 函数

只依赖 workbench.core 与 workbench.modules，核心逻辑零改动。
"""
from __future__ import annotations

# 关键：触发模块自动发现（news_digest 等）。
# CLI 在 workbench.cli 顶部导入 modules；Web 端必须在这里导入，
# 否则后台生成任务会报"未知模块: news_digest（可用: ）"。
import workbench.modules  # noqa: F401  触发模块注册
