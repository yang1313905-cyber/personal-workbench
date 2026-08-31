"""运行状态存储：JSON 单文件，供 `workbench status` 与本地状态页读取。"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class StatusStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def read(self) -> dict:
        try:
            return json.loads(self.path.read_text("utf-8"))
        except Exception:
            return {}

    def update(self, **fields: Any) -> None:
        with self._lock:
            data = self.read()
            data.update(fields)
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )

    def record_error(self, where: str, message: str) -> None:
        """记录最近一条错误（最多保留 20 条）。"""
        with self._lock:
            data = self.read()
            errors = data.get("errors") or []
            errors.append({"time": datetime.now().isoformat(timespec="seconds"), "where": where, "message": str(message)[:500]})
            data["errors"] = errors[-20:]
            data["last_error"] = errors[-1]
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )
