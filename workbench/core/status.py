"""运行状态存储：JSON 单文件，供 `workbench status` 与本地状态页读取。

写失败（例如只读文件系统上的云端部署）只记警告、不抛异常——
Web 界面不应因为写不了状态文件而整页报错。
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("workbench.status")


class StatusStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:  # 只读挂载：仍然允许读取已有状态文件
            log.warning("状态目录不可创建（%s）：%s", self.path.parent, e)
        self._lock = threading.Lock()

    def read(self) -> dict:
        try:
            return json.loads(self.path.read_text("utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        except OSError as e:
            log.warning("状态文件写入失败（%s），已忽略：%s", self.path, e)

    def update(self, **fields: Any) -> None:
        with self._lock:
            data = self.read()
            data.update(fields)
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write(data)

    def record_error(self, where: str, message: str) -> None:
        """记录最近一条错误（最多保留 20 条）。"""
        with self._lock:
            data = self.read()
            errors = data.get("errors") or []
            errors.append({"time": datetime.now().isoformat(timespec="seconds"), "where": where, "message": str(message)[:500]})
            data["errors"] = errors[-20:]
            data["last_error"] = errors[-1]
            self._write(data)
