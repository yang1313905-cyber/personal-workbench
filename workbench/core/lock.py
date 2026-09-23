"""跨进程互斥锁：防止 CLI / worker / Web 同时生成简报（重复抓取、重复推送）。

实现：O_CREAT|O_EXCL 原子创建锁文件，内容含 pid 与时间戳。
- 锁文件存在且属主进程已死 → 视为陈旧，自动回收
- 锁文件存在超过 stale_seconds → 视为陈旧，自动回收（防进程僵死）
- 与平台无关（POSIX / Windows 均可），无第三方依赖
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在但无权限，视为存活
    except OSError:
        return False


class FileLock:
    """用法：
        with FileLock(path) as lock:
            if not lock.acquired: ... # 拿不到锁
            ...
    """

    def __init__(self, path: str | Path, stale_seconds: int = 3600):
        self.path = Path(path)
        self.stale_seconds = stale_seconds
        self.acquired = False

    def acquire(self) -> bool:
        if self.acquired:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):  # 回收陈旧锁后重试一次
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "started": time.time()}).encode("utf-8"))
                os.close(fd)
                self.acquired = True
                return True
            except FileExistsError:
                if not self._is_stale():
                    return False
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
        return False

    def _is_stale(self) -> bool:
        try:
            data = json.loads(self.path.read_text("utf-8"))
            pid = data.get("pid")
            if pid and not _pid_alive(int(pid)):
                return True
            age = time.time() - float(data.get("started", 0))
            return age > self.stale_seconds
        except Exception:  # noqa: BLE001  无法解析视为陈旧
            return True

    def release(self) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self.acquired = False

    # ---- 上下文管理器 ----
    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def digest_lock_path(state_db_path: str | Path) -> Path:
    """与状态库同目录的 .digest.lock。"""
    return Path(state_db_path).parent / ".digest.lock"
