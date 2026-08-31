"""模块运行上下文：核心层向模块层注入的依赖集合。

未来新增模块时，如果还需要新能力（如数据库、缓存），
在 Context 上扩展字段即可，模块通过 ctx.xxx 使用，无需改其他模块。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .state import StateStore
from .status import StatusStore


@dataclass
class Context:
    config: dict
    state: StateStore
    status: StatusStore
    log: logging.Logger
    extras: dict = field(default_factory=dict)  # 模块私有扩展点

    def get(self, key: str, default: Any = None) -> Any:
        return self.extras.get(key, default)
