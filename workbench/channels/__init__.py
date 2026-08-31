"""渠道注册表：把 config.yaml 的 channels 段实例化为可用渠道列表。

新增渠道：在对应文件实现 Channel 子类后，加进 CHANNELS 字典即可。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from .base import Channel
from .dingtalk import DingTalkChannel
from .feishu import FeishuChannel
from .smtp_mail import SMTPChannel
from .telegram import TelegramChannel
from .webhook import WebhookChannel
from .wecom import WeComChannel

CHANNELS: Dict[str, Type[Channel]] = {
    TelegramChannel.id: TelegramChannel,
    WeComChannel.id: WeComChannel,
    FeishuChannel.id: FeishuChannel,
    DingTalkChannel.id: DingTalkChannel,
    SMTPChannel.id: SMTPChannel,
    WebhookChannel.id: WebhookChannel,
}

log = logging.getLogger("workbench.channels")


def build_channels(cfg: dict, only: Optional[List[str]] = None) -> List[Channel]:
    """按配置实例化所有启用渠道；only 非空时只保留指定渠道。"""
    result: List[Channel] = []
    for cid, cc in (cfg.get("channels") or {}).items():
        if only is not None and cid not in only:
            continue
        if not cc.get("enabled"):
            continue
        cls = CHANNELS.get(cid)
        if cls is None:
            log.warning("未知推送渠道: %s（已实现: %s）", cid, ", ".join(sorted(CHANNELS)))
            continue
        try:
            ch = cls(cc)
            ch.validate()
        except ValueError as e:
            log.error("渠道 %s 配置无效，已跳过: %s", cid, e)
            continue
        result.append(ch)
    return result


def build_channel(cfg: dict, channel_id: str) -> Channel:
    """实例化单个渠道（供 `workbench test-channel` 使用）。"""
    cc = (cfg.get("channels") or {}).get(channel_id)
    if not cc:
        raise ValueError(f"config.yaml 中不存在渠道 {channel_id}")
    if not cc.get("enabled"):
        raise ValueError(f"渠道 {channel_id} 未启用（enabled: false）")
    cls = CHANNELS.get(channel_id)
    if cls is None:
        raise ValueError(f"未知渠道类型 {channel_id}")
    ch = cls(cc)
    ch.validate()
    return ch


def broadcast(
    title: str,
    content: str,
    cfg: dict,
    log: logging.Logger,
    only: Optional[List[str]] = None,
) -> Dict[str, bool]:
    """向所有启用渠道推送；单渠道失败不影响其他渠道。返回 {channel_id: 是否成功}。"""
    results: Dict[str, bool] = {}
    channels = build_channels(cfg, only=only)
    if not channels:
        log.warning("没有可用的推送渠道，简报已保存到本地文件")
        return results
    for ch in channels:
        try:
            ch.send(title, content)
            results[ch.id] = True
            log.info("推送成功: %s", ch.id)
        except Exception as e:  # noqa: BLE001
            results[ch.id] = False
            log.exception("推送失败: %s (%s)", ch.id, e)
    return results
