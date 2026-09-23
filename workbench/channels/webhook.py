"""通用 Webhook 渠道：一个渠道覆盖 Server酱 / PushPlus / WxPusher / Bark 等。

这些第三方服务本质都是"向一个 URL 提交 title + content"，差异只在
URL 结构、请求方法与字段名。全部用配置描述，零代码。

配置（config.yaml channels.webhook.services 下可配任意多个服务）：

  serverchan:                       # 微信推送（Server酱3，免费 5 条/天）
    enabled: true
    url: "https://sctapi.ftqq.com/${SENDKEY}.send"   # ${} 由环境变量注入
    method: POST
    data: {title: "{title}", desp: "{content}"}       # 表单字段

  pushplus:                         # 微信推送（PushPlus，免费 200 条/天）
    url: "https://www.pushplus.plus/send"
    json: {token: "${PUSHPLUS_TOKEN}", title: "{title}", content: "{content}"}

  wxpusher:                         # 微信推送（WxPusher，免费，需关注公众号）
    url: "http://wxpusher.zjiecode.com/api/send/message"
    json: {appToken: "${WXPUSHER_APP_TOKEN}", content: "{content}",
           summary: "{title}", uids: ["${WXPUSHER_UID}"]}

  bark:                             # iOS 推送（Bark 免费）
    path: true
    url: "https://api.day.app/${BARK_KEY}/{title}/{content}"

字段说明：
- url 中的 {title}/{content} 会被替换（path: true 时 URL 编码）
- params → 查询参数（GET）；data → 表单（POST）；json → JSON 体（POST）
"""
from __future__ import annotations

import logging
from urllib.parse import quote

import requests

from .base import Channel

log = logging.getLogger("workbench.channel.webhook")


class WebhookChannel(Channel):
    id = "webhook"
    name = "通用 Webhook（Server酱/PushPlus/WxPusher/Bark）"

    def send(self, title: str, content: str) -> None:
        sent_any = False
        services = self.cfg.get("services") or {}
        for name, svc in services.items():
            if not svc.get("enabled", True):
                continue
            self._send_one(name, svc, title, content)
            sent_any = True
        if not sent_any:
            raise ValueError("webhook 渠道未配置任何启用的服务")

    def _send_one(self, name: str, svc: dict, title: str, content: str) -> None:
        method = str(svc.get("method", "POST")).upper()
        if svc.get("path"):
            url = svc["url"].format(title=quote(title), content=quote(content))
            resp = requests.request(method, url, timeout=30)
        elif method == "GET":
            params = {
                k: v.format(title=title, content=content)
                for k, v in (svc.get("params") or {}).items()
            }
            resp = requests.request(method, svc["url"], params=params, timeout=30)
        elif "json" in svc:
            payload = {
                k: (v.format(title=title, content=content) if isinstance(v, str) else v)
                for k, v in (svc.get("json") or {}).items()
            }
            resp = requests.request(method, svc["url"], json=payload, timeout=30)
        else:  # 默认 POST 表单
            data = {
                k: v.format(title=title, content=content)
                for k, v in (svc.get("data") or {}).items()
            }
            resp = requests.request(method, svc["url"], data=data, timeout=30)
        resp.raise_for_status()
        log.info("webhook 服务 %s 发送成功（HTTP %s）", name, resp.status_code)
