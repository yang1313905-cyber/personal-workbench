"""配置加载：YAML + ${ENV} 插值 + 路径归一化。

优先级：默认值 < config.yaml / feeds.yaml < 环境变量（通过 ${VAR} 插值）。

约定：
- config.yaml 中任何字符串都可以写成 ${ENV_NAME} 或 ${ENV_NAME:-默认值}，
  加载时自动替换为环境变量，密钥不落盘。
- 相对路径统一以项目根目录为基准解析，任何目录下执行都安全。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

# 项目根目录（本文件位于 workbench/core/config.py，向上三级即根）
ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG_PATH = "config/config.yaml"
DEFAULT_FEEDS_PATH = "config/feeds.yaml"

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _interpolate(value: Any) -> Any:
    """递归地把字符串中的 ${VAR} / ${VAR:-default} 替换为环境变量。"""
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    if isinstance(value, str):
        def repl(m: "re.Match") -> str:
            name, default = m.group(1), m.group(2)
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            raise ValueError(
                f"配置引用了未设置的环境变量 {name}；"
                f"请 export {name}=... 或在 .env 中配置，"
                f"或在 YAML 中写 {name}:-默认值"
            )
        return _ENV_RE.sub(repl, value)
    return value


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层必须是键值映射")
    return _interpolate(data)


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _default_config_path() -> Path:
    return _first_existing(ROOT / DEFAULT_CONFIG_PATH, Path(DEFAULT_CONFIG_PATH))


def _default_feeds_path() -> Path:
    return _first_existing(ROOT / DEFAULT_FEEDS_PATH, Path(DEFAULT_FEEDS_PATH))


def resolve_paths(cfg: dict) -> None:
    """把相对路径归一化为绝对路径，并填充 cfg['paths']。"""
    root = ROOT

    def abspath(p: Any) -> str:
        p = Path(str(p))
        return str(p if p.is_absolute() else root / p)

    app = cfg.setdefault("app", {})
    data_dir = abspath(app.get("data_dir", "data"))
    app["data_dir"] = data_dir

    cfg["paths"] = {
        "state": str(Path(data_dir) / "state.db"),
        "status": str(Path(data_dir) / "status" / "status.json"),
        "logs": str(Path(data_dir) / "logs"),
        "output": str(Path(data_dir) / "output"),
    }

    logging_cfg = cfg.setdefault("logging", {})
    logging_cfg.setdefault("file", str(Path(data_dir) / "logs" / "workbench.log"))

    nd = cfg.setdefault("news_digest", {})
    nd.setdefault("output_dir", cfg["paths"]["output"])
    nd.setdefault("push", {"enabled": True, "channels": []})

    ss = cfg.setdefault("status_server", {})
    ss.setdefault("enabled", True)
    ss.setdefault("host", "127.0.0.1")
    ss.setdefault("port", 8123)


def load_config(config_path: str | None = None, feeds_path: str | None = None) -> dict:
    """加载合并后的完整配置：.env + config.yaml + feeds.yaml + 路径归一化。"""
    _load_dotenv()
    cfg = load_yaml(_default_config_path() if config_path is None else Path(config_path))
    feeds = load_yaml(_default_feeds_path() if feeds_path is None else Path(feeds_path))
    cfg["feeds"] = feeds.get("sources", [])
    resolve_paths(cfg)
    return cfg


def _load_dotenv() -> None:
    """优先从项目根目录的 .env 加载环境变量（存在才加载）。"""
    try:
        from dotenv import load_dotenv
        # override=True：.env 存在时以文件内容为准。
        # 关键修复：Web 服务是长驻进程，默认 load_dotenv 不会覆盖已存在的环境变量，
        # 导致用户在配置中心更新 .env 后，进程内存里仍是旧 key（如 401 错误）。
        # 云端部署无 .env 文件（gitignore），Secrets 仍作为环境变量正常生效。
        load_dotenv(ROOT / ".env", override=True)
    except ImportError:
        pass  # 未安装 python-dotenv 时静默跳过，用户可自行 export


def get(cfg: dict, dotted: str, default: Any = None) -> Any:
    """按 'a.b.c' 取配置，缺失返回 default。"""
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
