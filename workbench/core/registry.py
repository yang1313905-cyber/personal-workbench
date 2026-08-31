"""模块注册表：核心与业务模块的边界。

每个功能模块是一个 Module：
    Module(id="news_digest", name="新闻简报", run=run_fn)

模块通过 `register(module)` 自我注册，核心通过 `run_module(id, ctx)` 调度。
新模块只需三步接入：
    1. 在 workbench/modules/<name>/ 下新建包
    2. 实现 run(ctx) -> dict
    3. 包内调用 register(Module(...))
自动发现机制（workbench/modules/__init__.py）会在启动时导入所有子包，
无需修改任何核心代码。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .context import Context

log = logging.getLogger("workbench.registry")


@dataclass
class Module:
    id: str
    name: str
    run: Callable[[Context], dict]
    config_section: Optional[str] = None

    def __post_init__(self) -> None:
        self.config_section = self.config_section or self.id


_MODULES: Dict[str, Module] = {}


def register(module: Module) -> None:
    if module.id in _MODULES:
        log.warning("模块 %s 重复注册，覆盖旧实现", module.id)
    _MODULES[module.id] = module
    log.info("已注册模块: %s (%s)", module.id, module.name)


def get_module(module_id: str) -> Optional[Module]:
    return _MODULES.get(module_id)


def all_modules() -> List[Module]:
    return list(_MODULES.values())


def run_module(module_id: str, ctx: Context) -> dict:
    m = get_module(module_id)
    if m is None:
        raise KeyError(f"未知模块: {module_id}（可用: {', '.join(sorted(_MODULES))}）")
    log.info("执行模块 %s", module_id)
    return m.run(ctx)
