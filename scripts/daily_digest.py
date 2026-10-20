#!/usr/bin/env python3
"""每日简报定时入口（供 launchd / cron 调用）。

为什么需要这个包装脚本，而不直接跑 `workbench digest`：

- 幂等：当天日报已成功送达邮件渠道时直接跳过，避免「开机补发」与
  「08:00 定时」两次触发导致重复邮件。
- 可重试：只有当天真正推送成功才算完成；若 08:00 那次因断网/锁冲突/
  电脑休眠失败，09:00 的重试或下次开机补发会重新执行。
- 防并发：与 Web 界面 / CLI 共用 data/.digest.lock，同一时刻只有一个任务在跑。

用法：
    .venv/bin/python scripts/daily_digest.py            # 当天未成功发送则发送
    .venv/bin/python scripts/daily_digest.py --force    # 忽略记录，强制重新生成并发送
    .venv/bin/python scripts/daily_digest.py --check    # 只报告状态，不发邮件

退出码：0 = 已发送或无需发送；4 = 简报生成了但推送失败；1 = 异常。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import workbench.modules  # noqa: F401,E402  触发模块自动发现
from workbench.cli import make_context  # noqa: E402
from workbench.core import registry  # noqa: E402
from workbench.core.lock import FileLock, digest_lock_path  # noqa: E402

PUSH_CHANNEL = "smtp"  # 判定「今天是否已送达」的渠道


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def already_delivered(ctx) -> bool:
    """当天简报是否已成功推送到邮件渠道。"""
    status = ctx.status.read()
    if status.get("digest_date") != today():
        return False
    return bool((status.get("push") or {}).get(PUSH_CHANNEL))


# ---------------------------------------------------------------- 重试上限
# 背景：2026-10-19 邮箱授权码被 QQ 拒绝后，外部调度器每 5 分钟重试一次，
# 一天打了 74 次——既浪费，又会触发 QQ 的「登录频率受限」把问题拖得更久。
# 现在每天最多真正尝试 MAX_ATTEMPTS_PER_DAY 次，超过后主动返回 0（视为本次完成），
# 让外部调度器停止重试；人工补发用 --force 不受此限制。
MAX_ATTEMPTS_PER_DAY = 6


def _attempts_today(status) -> int:
    data = status.read()
    if data.get("attempt_date") != today():
        return 0
    return int(data.get("attempt_count") or 0)


def _note_attempt(status) -> int:
    n = _attempts_today(status) + 1
    status.update(attempt_date=today(), attempt_count=n)
    return n


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="每日简报定时入口")
    parser.add_argument("--force", action="store_true", help="忽略当天记录，强制重新生成并推送")
    parser.add_argument("--check", action="store_true", help="只检查当天是否已发送，不执行抓取")
    args = parser.parse_args(argv)

    ctx = make_context()
    log = ctx.log
    try:
        if args.check:
            done = already_delivered(ctx)
            print(json.dumps({
                "date": today(),
                "delivered": done,
                "last_digest_date": ctx.state.last_digest_date(),
                "attempts_today": _attempts_today(ctx.status),
                "status": {k: ctx.status.read().get(k) for k in ("digest_date", "push", "output_file")},
            }, ensure_ascii=False, indent=2))
            return 0

        if not args.force and already_delivered(ctx):
            log.info("[daily] %s 的简报已成功送达，跳过本次触发（幂等）", today())
            print(f"skip: {today()} 的简报已发送，无需重复执行")
            return 0

        if not args.force:
            attempts = _note_attempt(ctx.status)
            if attempts > MAX_ATTEMPTS_PER_DAY:
                log.error(
                    "[daily] 今日已尝试 %d 次，达到上限 %d，停止重试。"
                    "请检查推送配置（例如邮箱授权码是否失效），修好后用 --force 手动补发。",
                    attempts - 1, MAX_ATTEMPTS_PER_DAY,
                )
                print(f"abort: 今日重试已达上限 {MAX_ATTEMPTS_PER_DAY} 次，停止重试（退出码 0，避免外部调度继续打）")
                return 0

        lock = FileLock(digest_lock_path(ctx.config["paths"]["state"]))
        if not lock.acquire():
            log.warning("[daily] 已有简报任务在运行，跳过本次触发")
            print("skip: 已有简报任务在运行")
            return 0
        try:
            result = registry.run_module("news_digest", ctx)
        finally:
            lock.release()

        push = result.get("push") or {}
        ok = bool(push) and any(push.values())
        log.info("[daily] 执行完成 delivered=%s 输出=%s", ok, result.get("output_file"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if ok else 4
    except Exception:  # noqa: BLE001
        log.exception("[daily] 执行异常")
        return 1
    finally:
        ctx.state.close()


if __name__ == "__main__":
    sys.exit(main())
