"""后台生成任务：Web 页面点击"立即生成"后异步执行。

- 线程在 Streamlit 进程内运行（daemon），不阻塞页面
- 与 CLI / 定时任务共用同一把跨进程锁，保证同时只有一个生成任务
- 任务状态存于进程内 _JOBS + status.json（便于 /status 可观测）
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Dict, Optional

import workbench.modules  # noqa: F401  触发模块自动发现（双保险，见 webui/__init__.py）
from workbench.core import registry
from workbench.core.lock import FileLock, digest_lock_path

from . import context as wctx

_JOBS: Dict[str, dict] = {}
_LOCK = threading.Lock()


def _now() -> float:
    return time.time()


def any_running() -> bool:
    with _LOCK:
        return any(j.get("status") == "running" for j in _JOBS.values())


def start_digest(no_push: bool = False, force: bool = False) -> Optional[str]:
    """启动后台生成任务。锁被占用（CLI/定时正在跑）时返回 None。

    force=True 时跳过历史去重（强制重新生成，同一天可再次生成完整简报）。
    """
    ctx = wctx.make_context()
    lock = FileLock(digest_lock_path(ctx.config["paths"]["state"]))
    if not lock.acquire():
        return None

    job_id = uuid.uuid4().hex[:8]
    with _LOCK:
        _JOBS[job_id] = {"status": "running", "started": _now(),
                         "no_push": no_push, "force": force}
    ctx.status.update(job={"id": job_id, "status": "running",
                           "no_push": no_push, "force": force})

    def _run():
        try:
            if no_push:
                nd = ctx.config.setdefault("news_digest", {})
                nd.setdefault("push", {})["enabled"] = False
            if force:
                ctx.extras["force_digest"] = True
            result = registry.run_module("news_digest", ctx)
            with _LOCK:
                _JOBS[job_id] = {"status": "done", "started": _JOBS[job_id]["started"],
                                 "finished": _now(), "result": result}
            ctx.status.update(job={"id": job_id, "status": "done", "result": result})
        except Exception as e:  # noqa: BLE001
            with _LOCK:
                _JOBS[job_id] = {"status": "error", "started": _JOBS[job_id]["started"],
                                 "finished": _now(), "error": str(e)}
            ctx.status.record_error("webui.job", str(e))
            ctx.status.update(job={"id": job_id, "status": "error", "error": str(e)})
        finally:
            lock.release()

    threading.Thread(target=_run, daemon=True, name=f"digest-{job_id}").start()
    return job_id


def job_state(job_id: str) -> Optional[dict]:
    with _LOCK:
        j = _JOBS.get(job_id)
        if not j:
            return None
        out = dict(j)
    if out.get("status") == "running":
        out["elapsed"] = _now() - out.get("started", _now())
    return out


def running_jobs() -> list:
    with _LOCK:
        return [{"id": k, "elapsed": _now() - v.get("started", _now())}
                for k, v in _JOBS.items() if v.get("status") == "running"]
