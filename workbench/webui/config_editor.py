"""配置中心读写后端。

- config.yaml / feeds.yaml：ruamel.yaml 保注释、保格式原地修改（写前校验 + 自动备份）
- .env：保留注释与顺序的键值编辑
- 提供"有效配置"（含环境变量插值后的最终值，密钥打码）

说明：在云平台（Streamlit Cloud 免费版等）文件系统是临时的，
配置中心的写盘改动在实例重启后会丢失；云端应优先使用环境变量/Secrets
（本项目配置加载顺序：config.yaml < feeds.yaml < ${ENV}，env 永远优先）。
"""
from __future__ import annotations

import io
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

import yaml as pyyaml
from ruamel.yaml import YAML

from workbench.core.config import ROOT

CONFIG_PATH = ROOT / "config" / "config.yaml"
FEEDS_PATH = ROOT / "config" / "feeds.yaml"
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE_PATH = ROOT / ".env.example"

# 每个渠道依赖的环境变量清单（配置中心 / 推送中心共用）
CHANNEL_ENV_KEYS = {
    "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
    "wecom": ["WECOM_WEBHOOK"],
    "feishu": ["FEISHU_WEBHOOK"],
    "dingtalk": ["DINGTALK_WEBHOOK"],
    "smtp": ["SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO"],
    "webhook": ["SENDKEY", "PUSHPLUS_TOKEN", "WXPUSHER_APP_TOKEN", "WXPUSHER_UID", "BARK_KEY"],
}

_editors: dict = {}


# ---------------- YAML（保注释） ----------------

class YamlEditor:
    """ruamel round-trip 编辑器：load 与 save 必须用同一个实例（注释状态绑定）。"""

    def __init__(self, path: Path):
        self.path = path
        self.yaml = YAML()
        self.yaml.preserve_quotes = True   # 保留 "800-1500" 这类引号
        self.yaml.width = 4096             # 避免长行被自动折行
        self.data = self.yaml.load(path) if path.exists() else {}

    # ---- 读取 ----
    def get(self, dotted: str, default=None):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def sources(self) -> list:
        return self.data.get("sources", [])

    # ---- 修改 ----
    def set(self, dotted: str, value) -> None:
        node = self.data
        parts = dotted.split(".")
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node or not isinstance(node[part], dict):
                raise KeyError(f"配置路径不存在: {dotted}")
            node = node[part]
        node[parts[-1]] = value

    def append_source(self, item: dict) -> None:
        srcs = self.data.setdefault("sources", [])
        srcs.append(item)

    def remove_source(self, index: int) -> None:
        del self.data["sources"][index]

    # ---- 保存（写前校验 + 备份） ----
    def save(self) -> str:
        buf = io.StringIO()
        self.yaml.dump(self.data, buf)
        text = buf.getvalue()
        pyyaml.safe_load(text)  # 校验合法，非法则抛异常且不落盘
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            shutil.copy2(p, str(p) + ".bak")
        p.write_text(text, encoding="utf-8")
        _editors.pop(str(p), None)  # 缓存失效，下次重新加载
        return text


def editor(path: Path) -> YamlEditor:
    key = str(path)
    if key not in _editors:
        _editors[key] = YamlEditor(path)
    return _editors[key]


def config_editor() -> YamlEditor:
    return editor(CONFIG_PATH)


def feeds_editor() -> YamlEditor:
    return editor(FEEDS_PATH)


# ---------------- .env ----------------

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def load_env(path: Path = ENV_PATH) -> List[Tuple[str, str, str]]:
    """解析 .env，保留注释与空行。返回 [(kind, key, value)]，kind ∈ comment|blank|kv。"""
    if not path.exists():
        return []
    entries: List[Tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            entries.append(("blank", "", ""))
        elif stripped.startswith("#"):
            entries.append(("comment", "", line))
        else:
            m = _ENV_LINE.match(line)
            if m:
                entries.append(("kv", m.group(1), m.group(2)))
            else:
                entries.append(("comment", "", line))  # 异常行按注释保留
    return entries


def save_env(entries: List[Tuple[str, str, str]], path: Path = ENV_PATH) -> None:
    lines = []
    for kind, key, value in entries:
        if kind == "kv":
            lines.append(f"{key}={value}")
        elif kind == "comment":
            lines.append(value)
        else:
            lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    if path.exists():
        shutil.copy2(path, str(path) + ".bak")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def env_value(key: str, path: Path = ENV_PATH) -> str:
    for kind, k, v in load_env(path):
        if kind == "kv" and k == key:
            return v
    return ""


def set_env(key: str, value: str, path: Path = ENV_PATH) -> None:
    entries = load_env(path)
    found = False
    for i, (kind, k, _v) in enumerate(entries):
        if kind == "kv" and k == key:
            if value:
                entries[i] = ("kv", key, value)
            else:  # 空值 = 删除该键
                del entries[i]
            found = True
            break
    if not found and value:
        entries.append(("kv", key, value))
    save_env(entries, path)


def init_env_from_example(path: Path = ENV_PATH) -> int:
    """从 .env.example 初始化 .env（值清空，只保留键）。返回键数量。"""
    entries: List[Tuple[str, str, str]] = []
    count = 0
    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            entries.append(("blank", "", ""))
        elif stripped.startswith("#"):
            entries.append(("comment", "", line))
        else:
            m = _ENV_LINE.match(line)
            if m:
                entries.append(("kv", m.group(1), ""))
                count += 1
            else:
                entries.append(("comment", "", line))
    save_env(entries, path)
    return count


# ---------------- 有效配置（只读，密钥打码） ----------------

_SECRET_HINT = ("token", "password", "api_key", "secret", "sendkey", "bark", "uid", "key")


def _redact(obj, path: str = ""):
    if isinstance(obj, dict):
        return {k: _redact(v, f"{path}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v, path) for v in obj]
    if isinstance(obj, str) and any(h in path.lower() for h in _SECRET_HINT):
        return "***" if obj else ""
    return obj


def effective_config() -> dict:
    """环境变量插值后的最终配置（密钥打码，供只读查看）。"""
    from workbench.core.config import load_config
    cfg = load_config()
    feeds = cfg.pop("feeds", [])
    out = _redact(cfg)
    out["feeds"] = [
        {"id": s.get("id"), "name": s.get("name"), "lang": s.get("lang"),
         "enabled": s.get("enabled", True)}
        for s in feeds
    ]
    return out
