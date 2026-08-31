"""Telegram Bot 渠道（最稳定、最推荐的国际渠道）。

配置（config.yaml）：
    channels.telegram:
        enabled: true
        bot_token: ${TELEGRAM_BOT_TOKEN}
        chat_id:   ${TELEGRAM_CHAT_ID}
"""
from __future__ import annotations

import logging

import requests

from .base import Channel

log = logging.getLogger("workbench.channel.telegram")

API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 4000  # Telegram 单条上限 4096，留余量


def _chunks(text: str, size: int = MAX_LEN):
    """按段落切分，保证单条不超过 size。"""
    if len(text) <= size:
        yield text
        return
    buf, cur = [], 0
    for para in text.split("\n\n"):
        if cur + len(para) + 2 > size and buf:
            yield "\n\n".join(buf)
            buf, cur = [], 0
        buf.append(para)
        cur += len(para) + 2
    if buf:
        yield "\n\n".join(buf)


class TelegramChannel(Channel):
    id = "telegram"
    name = "Telegram Bot"

    def validate(self) -> None:
        if not self.cfg.get("bot_token"):
            raise ValueError("缺少 bot_token（配置 ${TELEGRAM_BOT_TOKEN}）")
        if not self.cfg.get("chat_id"):
            raise ValueError("缺少 chat_id（向 @userinfobot 发送 /start 获取）")

    def send(self, title: str, content: str) -> None:
        token = self.cfg["bot_token"]
        chat_id = self.cfg["chat_id"]
        text = f"{title}\n\n{content}"
        for chunk in _chunks(text):
            resp = requests.post(
                API.format(token=token),
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API 错误: {data}")
        log.info("Telegram 推送成功（%d 字符）", len(text))
