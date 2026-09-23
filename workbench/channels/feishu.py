"""飞书自定义机器人渠道（免费、需在群内添加机器人）。

配置（config.yaml）：
    channels.feishu:
        enabled: true
        webhook: ${FEISHU_WEBHOOK}

Webhook 获取：飞书群 → 设置 → 群机器人 → 添加自定义机器人 → 复制 Webhook。
"""
from __future__ import annotations

import logging

import requests

from .base import Channel

log = logging.getLogger("workbench.channel.feishu")

MAX_LEN = 30000


class FeishuChannel(Channel):
    id = "feishu"
    name = "飞书机器人"

    def validate(self) -> None:
        if not self.cfg.get("webhook"):
            raise ValueError("缺少 webhook（飞书群机器人地址）")

    def send(self, title: str, content: str) -> None:
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title[:100]}},
                "elements": [{"tag": "markdown", "content": content[:MAX_LEN]}],
            },
        }
        resp = requests.post(self.cfg["webhook"], json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0:
            raise RuntimeError(f"飞书错误: {data}")
        log.info("飞书推送成功")
