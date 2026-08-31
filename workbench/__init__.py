"""个人智能工作台（Personal Workbench）。

模块化 Agent 框架：
- core:    配置、日志、重试、状态存储、模块注册表、调度器
- modules: 业务功能模块（首个模块：news_digest 新闻简报）
- channels:推送渠道（Telegram / 企业微信 / 飞书 / 钉钉 / 邮件 / 通用 Webhook）

设计原则：
1. 每个功能是一个独立模块（Module），通过注册表接入核心，互不依赖。
2. 所有关键参数走 config.yaml + 环境变量插值，代码零硬编码。
3. 抓取、蒸馏、推送三段式流水线，任何一段失败都有兜底。
"""

__version__ = "0.1.0"
