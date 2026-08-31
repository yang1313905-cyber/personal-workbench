"""内置调度器（APScheduler）：适合本地/服务器常驻进程。

与 cron 二选一：
- 服务器有 cron / systemd：推荐用 cron 触发 `workbench digest`（更稳、可审计）
- 无 cron 环境（如 Docker / 常驻进程）：用本模块 `workbench worker`

可靠性特性：catch_up —— 若错过计划时间（如电脑关机），启动时自动补发。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Tuple

from . import registry
from .config import get as cfg_get
from .context import Context

log = logging.getLogger("workbench.scheduler")


def parse_time(s: str) -> Tuple[int, int]:
    hh, mm = s.split(":")
    return int(hh), int(mm)


def _run_digest_job(ctx: Context) -> None:
    from .lock import FileLock, digest_lock_path

    lock = FileLock(digest_lock_path(ctx.config["paths"]["state"]))
    if not lock.acquire():
        log.warning("定时任务跳过：已有简报生成任务在运行（可能是 Web 手动触发）")
        return
    try:
        result = registry.run_module("news_digest", ctx)
        log.info("定时任务完成: 抓取 %s 条，保留 %s 条，输出 %s",
                 result.get("fetched"), result.get("kept"), result.get("output_file"))
    except Exception:
        log.exception("定时任务失败")
        ctx.status.record_error("scheduler.news_digest", "定时任务异常")
    finally:
        lock.release()


def run_worker(ctx: Context) -> None:
    """常驻调度进程，阻塞运行。"""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched_cfg = ctx.config.get("schedule", {})
    tz = sched_cfg.get("timezone") or cfg_get(ctx.config, "app.timezone", "Asia/Shanghai")
    hh, mm = parse_time(sched_cfg.get("time", "08:00"))

    scheduler = BlockingScheduler(timezone=tz)

    # 错过补发：今日尚未生成简报则立即执行一次
    if sched_cfg.get("catch_up", True):
        today = datetime.now().strftime("%Y-%m-%d")
        if ctx.state.last_digest_date() != today:
            log.info("检测到今日尚未生成简报，启动即补发")
            _run_digest_job(ctx)

    scheduler.add_job(
        _run_digest_job,
        CronTrigger(hour=hh, minute=mm, timezone=tz),
        args=[ctx],
        id="news_digest_daily",
        misfire_grace_time=3600,  # 错过 1 小时内仍会补执行
        coalesce=True,            # 多次错过只执行一次
    )
    log.info("调度器启动：每天 %02d:%02d (%s) 执行 news_digest", hh, mm, tz)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("调度器退出")
