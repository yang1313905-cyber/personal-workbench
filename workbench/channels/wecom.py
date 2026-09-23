"""企业微信群机器人渠道（国内最便捷、免费、无审核）。

配置（config.yaml）：
    channels.wecom:
        enabled: true
        webhook: ${WECOM_WEBHOOK}

Webhook 获取：群 → 右上角 ... → 添加群机器人 → 复制 Webhook 地址。
注意：markdown 内容上限 4096 字节；机器人是"群内"消息，不能私聊推送。
"""
from __future__ import annotations

import logging

import requests

from .base import Channel

log = logging.getLogger("workbench.channel.wecom")

MAX_BYTES = 4000


class WeComChannel(Channel):
    id = "wecom"
    name = "企业微信机器人"

    def validate(self) -> None:
        if not self.cfg.get("webhook"):
            raise ValueError("缺少 webhook（企业微信群机器人地址）")

    def send(self, title: str, content: str) -> None:
        text = f"{title}\n{content}"[:MAX_BYTES]
        resp = requests.post(
            self.cfg["webhook"],
            json={"msgtype": "markdown", "markdown": {"content": text}},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"企业微信错误: {data}")
        log.info("企业微信推送成功")
