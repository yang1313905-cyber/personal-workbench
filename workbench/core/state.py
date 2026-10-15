"""SQLite 状态存储：去重历史 + 已发送简报记录。

单文件、零外部依赖、并发安全（WAL + 锁）。
只读文件系统（如云端容器挂载的仓库目录）上会自动回退到临时目录，
保证 Web 界面能正常打开而不是直接报错。
"""
from __future__ import annotations

import logging
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("workbench.state")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dir_writable(path: Path) -> bool:
    """目标目录是否可写（用一次真实写入探测，比 os.access 可靠）。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.parent / ".~write_probe"
        probe.write_text("", "utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


class StateStore:
    def __init__(self, path: str | Path):
        path = Path(path)
        if not _dir_writable(path):
            fallback = Path(tempfile.gettempdir()) / "workbench-state" / path.name
            fallback.parent.mkdir(parents=True, exist_ok=True)
            log.warning("状态库 %s 不可写，已回退到临时目录 %s（数据不会持久化）", path, fallback)
            path = fallback
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS seen_items(
                    hash       TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL,
                    source     TEXT,
                    title      TEXT
                );
                CREATE TABLE IF NOT EXISTS digests(
                    date       TEXT PRIMARY KEY,
                    content    TEXT NOT NULL,
                    channels   TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            self.conn.commit()

    # ---------- 去重 ----------
    def is_seen(self, item_hash: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM seen_items WHERE hash = ?", (item_hash,)
            ).fetchone()
        return row is not None

    def mark_seen(self, item_hash: str, source: str = "", title: str = "") -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO seen_items(hash, first_seen, source, title) VALUES (?,?,?,?)",
                (item_hash, _utc_now(), source, title),
            )
            self.conn.commit()

    def mark_seen_many(self, items: list[dict]) -> None:
        with self._lock:
            self.conn.executemany(
                "INSERT OR IGNORE INTO seen_items(hash, first_seen, source, title) VALUES (?,?,?,?)",
                [(it["hash"], _utc_now(), it.get("source_id", ""), it.get("title", "")) for it in items],
            )
            self.conn.commit()

    def prune(self, keep_days: int = 3) -> None:
        """清理超过 keep_days 的历史（默认 3 天，避免重复报道同一旧闻）。"""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, keep_days))).isoformat()
        with self._lock:
            cur = self.conn.execute("DELETE FROM seen_items WHERE first_seen < ?", (cutoff,))
            self.conn.commit()
            return cur.rowcount

    # ---------- 简报记录 ----------
    def digest_sent(self, date: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM digests WHERE date = ?", (date,)
            ).fetchone()
        return row is not None

    def mark_digest(self, date: str, content: str, channels: Optional[List[str]] = None) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO digests(date, content, channels, created_at) VALUES (?,?,?,?)",
                (date, content, ",".join(channels or []), _utc_now()),
            )
            self.conn.commit()

    def last_digest_date(self) -> Optional[str]:
        with self._lock:
            row = self.conn.execute("SELECT MAX(date) FROM digests").fetchone()
        return row[0] if row and row[0] else None

    def close(self) -> None:
        self.conn.close()
