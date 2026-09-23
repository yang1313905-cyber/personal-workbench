"""统一日志：控制台 + 滚动文件，UTF-8 安全。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import get

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"


def setup_logging(cfg: dict) -> logging.Logger:
    logger = logging.getLogger("workbench")
    if logger.handlers:  # 已初始化，避免重复挂 handler
        return logger

    level = getattr(logging, str(get(cfg, "logging.level", "INFO")).upper(), logging.INFO)
    logger.setLevel(level)

    fmt = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    log_file = get(cfg, "logging.file")
    if log_file:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            p,
            maxBytes=int(get(cfg, "logging.max_bytes", 5 * 1024 * 1024)),
            backupCount=int(get(cfg, "logging.backup_count", 3)),
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
