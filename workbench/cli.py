"""workbench 命令行入口。

用法：
    workbench digest                立即生成并推送今日简报
    workbench digest --no-push      只生成简报，不推送（--dry-run 同义）
    workbench digest --channel X    仅通过指定渠道推送
    workbench worker                常驻调度进程（每天定时执行）
    workbench status [--json]       查看运行状态
    workbench serve                 启动本地状态页（默认 http://127.0.0.1:8123）
    workbench test-channel <id>     发送测试消息到指定渠道
    workbench modules               列出已注册模块
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import workbench.modules  # noqa: F401  触发模块自动发现
from . import __version__
from .channels import CHANNELS, build_channel
from .core import registry
from .core.config import get as cfg_get
from .core.config import load_config
from .core.context import Context
from .core.logging import setup_logging
from .core.state import StateStore
from .core.status import StatusStore

log = logging.getLogger("workbench.cli")


# ---------------- 上下文 ----------------

def make_context() -> Context:
    cfg = load_config()
    logger = setup_logging(cfg)
    state = StateStore(cfg["paths"]["state"])
    status = StatusStore(cfg["paths"]["status"])
    return Context(config=cfg, state=state, status=status, log=logger)


# ---------------- 子命令 ----------------

def cmd_digest(args: argparse.Namespace, ctx: Context) -> int:
    nd = ctx.config.setdefault("news_digest", {})
    push = nd.setdefault("push", {"enabled": True, "channels": []})
    if args.no_push:
        push["enabled"] = False
        ctx.log.info("--no-push：只生成简报，不推送")
    if args.channel:
        push["channels"] = [args.channel]

    # 跨进程防重锁：Web / CLI / 定时任务同时触发时只允许一个真正执行
    from .core.lock import FileLock, digest_lock_path

    with FileLock(digest_lock_path(ctx.config["paths"]["state"])) as lock:
        if not lock.acquired:
            ctx.log.error("已有简报生成任务在运行（锁 %s 被占用），本次跳过", lock.path)
            print("⚠️ 已有任务在运行，请稍后再试")
            return 3
        result = registry.run_module("news_digest", ctx)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok = result.get("push") and any(result["push"].values())
    return 0 if (ok or args.no_push) else 2


def cmd_worker(args: argparse.Namespace, ctx: Context) -> int:
    from .core.scheduler import run_worker
    run_worker(ctx)
    return 0


def cmd_status(args: argparse.Namespace, ctx: Context) -> int:
    data = ctx.status.read()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    if not data:
        print("尚无运行记录（先执行一次 workbench digest）")
        return 0
    print("=== 工作台运行状态 ===")
    for key in ("updated_at", "last_run", "digest_date", "items_fetched",
                "items_kept", "used_llm", "output_file", "push"):
        if key in data:
            print(f"{key}: {json.dumps(data[key], ensure_ascii=False)}")
    if data.get("errors"):
        print("\n最近错误：")
        for e in data["errors"][-5:]:
            print(f"  [{e.get('time')}] {e.get('where')}: {e.get('message')}")
    return 0


def cmd_serve(args: argparse.Namespace, ctx: Context) -> int:
    status_path = Path(ctx.config["paths"]["status"])
    host = str(cfg_get(ctx.config, "status_server.host", "127.0.0.1"))
    port = int(cfg_get(ctx.config, "status_server.port", 8123))

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            try:
                body = status_path.read_text("utf-8")
            except Exception:
                body = "{}"
            if self.path in ("/", "/status.json"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):  # 静默访问日志
            pass

    ctx.log.info("状态页已启动: http://%s:%s/status.json", host, port)
    try:
        ThreadingHTTPServer((host, port), _Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_test_channel(args: argparse.Namespace, ctx: Context) -> int:
    try:
        ch = build_channel(ctx.config, args.channel_id)
        ch.send("✅ 测试消息", "这是来自个人工作台的测试推送。\n如果收到本条消息，说明渠道配置正确。")
        print(f"渠道 {args.channel_id} 测试成功")
        return 0
    except Exception as e:  # noqa: BLE001
        ctx.log.error("渠道 %s 测试失败: %s", args.channel_id, e)
        return 1


def cmd_modules(args: argparse.Namespace, ctx: Context) -> int:
    for m in registry.all_modules():
        print(f"{m.id:16s} {m.name}")
    return 0


# ---------------- 入口 ----------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workbench",
        description=f"个人智能工作台 v{__version__} —— 模块化 Agent，首个模块为每日新闻简报",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_digest = sub.add_parser("digest", help="立即生成并推送今日简报")
    p_digest.add_argument("--no-push", "--dry-run", action="store_true", dest="no_push",
                          help="只生成简报，不推送")
    p_digest.add_argument("--channel", help="仅通过指定渠道推送（如 telegram）")

    sub.add_parser("worker", help="常驻调度进程（每天定时执行）")

    p_status = sub.add_parser("status", help="查看运行状态")
    p_status.add_argument("--json", action="store_true", help="JSON 输出")

    sub.add_parser("serve", help="启动本地状态页（默认 127.0.0.1:8123）")

    p_test = sub.add_parser("test-channel", help="发送测试消息到指定渠道")
    p_test.add_argument("channel_id", choices=sorted(CHANNELS), help="渠道 id")

    sub.add_parser("modules", help="列出已注册模块")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ctx = make_context()
    handlers = {
        "digest": cmd_digest,
        "worker": cmd_worker,
        "status": cmd_status,
        "serve": cmd_serve,
        "test-channel": cmd_test_channel,
        "modules": cmd_modules,
    }
    try:
        return handlers[args.cmd](args, ctx) or 0
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001
        ctx.log.exception("命令 %s 执行失败", args.cmd)
        return 1
    finally:
        ctx.state.close()


if __name__ == "__main__":
    sys.exit(main())
