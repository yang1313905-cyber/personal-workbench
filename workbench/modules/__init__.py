"""模块自动发现：导入 workbench.modules 即扫描并加载所有子包。

新增模块：在 workbench/modules/ 下新建包，包内调用 register()，
无需修改本文件或任何核心代码。
"""
from __future__ import annotations

import importlib
import logging
import pkgutil

log = logging.getLogger("workbench.modules")


def discover() -> None:
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{__name__}.{mod.name}")
            log.debug("已加载模块包: %s", mod.name)
        except Exception:  # noqa: BLE001
            log.exception("模块 %s 加载失败，跳过", mod.name)


discover()
