"""SMTP 邮件渠道（免费，使用邮箱授权码，不依赖任何第三方服务）。

配置（config.yaml）：
    channels.smtp:
        enabled: true
        host: smtp.qq.com
        port: 465
        user: ${SMTP_USER}          # 邮箱账号
        password: ${SMTP_PASSWORD}  # 授权码（非登录密码）
        from: ${SMTP_FROM}
        to: ${SMTP_TO}              # 收件人，可多个用逗号分隔

授权码获取：QQ 邮箱 → 设置 → 账户 → 开启 SMTP 服务 → 生成授权码。
Gmail 需在 Google 账号启用"应用专用密码"。
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from html import escape as html_escape

from .base import Channel

log = logging.getLogger("workbench.channel.smtp")


class SMTPChannel(Channel):
    id = "smtp"
    name = "邮件 (SMTP)"

    def validate(self) -> None:
        for key in ("host", "user", "password", "to"):
            if not self.cfg.get(key):
                raise ValueError(f"缺少 smtp.{key}")

    def send(self, title: str, content: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = title
        # 显示名（如「个人智能工作台 <xxx@qq.com>」），提升收件体验与投递率
        from email.utils import formataddr
        sender = self.cfg.get("from") or self.cfg["user"]
        msg["From"] = formataddr((self.cfg.get("from_name", "个人智能工作台"), sender))
        msg["To"] = self.cfg["to"]
        msg.set_content(content)
        # 附带一份保留换行的简单 HTML 版本，手机邮件客户端显示更好
        body_html = (
            "<html><body><pre style='font-family:-apple-system,sans-serif;"
            f"white-space:pre-wrap;font-size:14px'>{html_escape(content)}</pre></body></html>"
        )
        msg.add_alternative(body_html, subtype="html")

        host = self.cfg["host"]
        port = int(self.cfg.get("port", 465))
        use_ssl = bool(self.cfg.get("use_ssl", True))

        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                server.login(self.cfg["user"], self.cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls()
                server.login(self.cfg["user"], self.cfg["password"])
                server.send_message(msg)
        log.info("邮件推送成功 -> %s", self.cfg["to"])
