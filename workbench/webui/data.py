"""数据访问层：简报文件、运行状态、日志读取。

全部为只读操作，函数可传入 cfg 便于单元测试隔离。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from workbench.core.config import load_config
from workbench.core.status import StatusStore

_DIGEST_RE = re.compile(r"^digest-(\d{4}-\d{2}-\d{2})\.md$")


def _cfg(cfg: Optional[dict] = None) -> dict:
    return cfg if cfg is not None else load_config()


def output_dir(cfg: Optional[dict] = None) -> Path:
    return Path(_cfg(cfg)["news_digest"]["output_dir"])


def status_path(cfg: Optional[dict] = None) -> Path:
    return Path(_cfg(cfg)["paths"]["status"])


def state_path(cfg: Optional[dict] = None) -> Path:
    return Path(_cfg(cfg)["paths"]["state"])


def log_path(cfg: Optional[dict] = None) -> Path:
    return Path(_cfg(cfg).get("logging", {}).get("file", "data/logs/workbench.log"))


# ---------------- 简报 ----------------

def list_digests(limit: Optional[int] = None, cfg: Optional[dict] = None) -> List[dict]:
    """按日期倒序返回简报元信息。"""
    out_dir = output_dir(cfg)
    if not out_dir.exists():
        return []
    files = sorted(out_dir.glob("digest-*.md"), reverse=True)
    result = []
    for f in files:
        m = _DIGEST_RE.match(f.name)
        if not m:
            continue
        st = f.stat()
        result.append({
            "date": m.group(1),
            "path": str(f),
            "size_kb": max(1, st.st_size // 1024),
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%m-%d %H:%M"),
        })
        if limit and len(result) >= limit:
            break
    return result


def list_digest_dates(cfg: Optional[dict] = None) -> List[str]:
    return [d["date"] for d in list_digests(cfg=cfg)]


def read_digest(date: str, cfg: Optional[dict] = None) -> Optional[str]:
    f = output_dir(cfg) / f"digest-{date}.md"
    if not f.exists():
        return None
    return f.read_text(encoding="utf-8")


def digest_matches(date: str, keyword: str, cfg: Optional[dict] = None) -> bool:
    content = read_digest(date, cfg)
    return bool(content) and keyword.lower() in content.lower()


def search_snippet(date: str, keyword: str, cfg: Optional[dict] = None) -> Optional[str]:
    """返回第一条命中行（截断）。"""
    content = read_digest(date, cfg)
    if not content or not keyword:
        return None
    for line in content.splitlines():
        if keyword.lower() in line.lower():
            line = line.strip()
            return line[:80] + ("…" if len(line) > 80 else "")
    return None


def digest_record(date: str, cfg: Optional[dict] = None) -> Optional[dict]:
    """从状态库读取某天的推送记录。"""
    from workbench.core.state import StateStore
    store = StateStore(state_path(cfg))
    try:
        with store.conn:
            row = store.conn.execute(
                "SELECT date, channels, created_at FROM digests WHERE date = ?", (date,)
            ).fetchone()
    finally:
        store.close()
    if not row:
        return None
    return {"date": row[0], "channels": (row[1] or "").split(",") if row[1] else [], "created_at": row[2]}


# ---------------- 状态 / 日志 ----------------

def read_status(cfg: Optional[dict] = None) -> dict:
    return StatusStore(status_path(cfg)).read()


def tail_log(n: int = 500, level: Optional[str] = None, cfg: Optional[dict] = None) -> str:
    """读取日志尾部；level 可选过滤（ERROR/WARNING/INFO/DEBUG）。"""
    path = log_path(cfg)
    if not path.exists():
        return "（暂无日志文件）"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if level and level != "ALL":
        tag = level.upper()
        lines = [ln for ln in lines if f" [{tag}] " in ln or f" {tag} " in ln]
    return "\n".join(lines[-n:])
