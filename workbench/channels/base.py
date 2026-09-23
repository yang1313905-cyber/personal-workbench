"""渠道抽象基类：所有推送渠道实现 send(title, content)。

新增渠道三步：
    1. 继承 Channel，实现 id / name / validate / send
    2. 在 channels/__init__.py 的 CHANNELS 字典中登记
    3. config.yaml 的 channels 段添加配置项
"""
from __future__ import annotations


class Channel:
    id = "base"
    name = "Base Channel"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def validate(self) -> None:
        """检查必需配置，缺失抛 ValueError（该渠道会被跳过并记录）。"""

    def send(self, title: str, content: str) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} id={self.id}>"
