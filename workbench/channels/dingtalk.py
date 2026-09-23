"""钉钉自定义机器人渠道（免费、需在群内添加机器人）。

配置（config.yaml）：
    channels.dingtalk:
        enabled: true
        webhook: ${DINGTALK_WEBHOOK}

Webhook 获取：钉钉群 → 群设置 → 智能群助手 → 添加机器人（自定义）。
若机器人开启了"加签"或"自定义关键词"安全设置，需要相应配置（本项目未内置加签，
建议选择"自定义关键词"并把关键词设为"今日"或直接关闭安全设置）。
"""
from __future__ import annotations

import logging

import requests

from .base import Channel

log = logging.getLogger("workbench.channel.dingtalk")

MAX_LEN = 19000


class DingTalkChannel(Channel):
    id = "dingtalk"
    name = "钉钉机器人"

    def validate(self) -> None:
        if not self.cfg.get("webhook"):
            raise ValueError("缺少 webhook（钉钉群机器人地址）")

    def send(self, title: str, content: str) -> None:
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title[:50], "text": content[:MAX_LEN]},
        }
        resp = requests.post(self.cfg["webhook"], json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"钉钉错误: {data}")
        log.info("钉钉推送成功")
