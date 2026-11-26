"""新闻简报模块（News Digest Module）：工作台第一个业务模块。

流水线：抓取 → 关键词过滤 → 去重 → 排序取 Top-N → LLM 蒸馏 → 渲染（回填真实链接）
        → 存档 → 推送。
每一步都独立、可替换、可单独调试。模块只依赖 core 提供的 Context。
"""
from __future__ import annotations

import logging
import json
import re
from zoneinfo import ZoneInfo
from datetime import datetime
from pathlib import Path
from typing import Optional

from ...channels import broadcast
from ...core.registry import Module, register
from ...core.status import StatusStore
from . import cleaner, distill, fetcher, render, recommend

log = logging.getLogger("workbench.news")
_URL_RE = re.compile(r"https?://[^\s'\"<>)]+")


def _redact_error(msg: str) -> str:
    return _URL_RE.sub("[redacted-url]", str(msg or ""))[:200]


def run(ctx) -> dict:
    cfg = ctx.config
    nd = cfg.get("news_digest", {})
    date_str = datetime.now(ZoneInfo(cfg.get("app", {}).get("timezone", "Asia/Shanghai"))).strftime("%Y-%m-%d")
    http_cfg = cfg.get("http", {})
    status: StatusStore = ctx.status

    # 1. 抓取（单源失败不中断整体）
    items, errors = fetcher.fetch_all(cfg.get("feeds", []), http_cfg)
    fetched_total = len(items)
    safe_status_errors = [
        {"source": e.get("source") or "未知来源", "error": _redact_error(e.get("error", ""))}
        for e in errors[:10]
    ]
    status.update(last_run=datetime.now().isoformat(timespec="seconds"),
                  items_fetched=fetched_total, fetch_errors=safe_status_errors)
    ctx.log.info("抓取完成：共 %d 条，%d 个来源失败", fetched_total, len(errors))

    # 2. 关键词过滤
    include, exclude = nd.get("include_keywords", []), nd.get("exclude_keywords", [])
    if include or exclude:
        before = len(items)
        items = [it for it in items
                 if cleaner.keyword_ok(it["title"] + " " + it["summary"], include, exclude)]
        ctx.log.info("关键词过滤：%d -> %d", before, len(items))

    # Keep a complete browsable pool, independent of digest delivery history.
    items = recommend.rank(items, nd)
    items = cleaner.dedupe(items, threshold=float(nd.get("overlap_threshold", 0.55)))
    items = recommend.rank(items, nd)
    out_dir = Path(nd.get("output_dir", cfg["paths"]["output"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    pool_file = out_dir / "news-latest.json"
    temporary = pool_file.with_suffix(".tmp")
    safe_errors = [{"source": e.get("source") or "未知来源"} for e in errors]
    temporary.write_text(json.dumps({
        "updated_at": datetime.now().astimezone().isoformat(),
        "items": items, "errors": safe_errors, "fetched": fetched_total,
    }, ensure_ascii=False), encoding="utf-8")
    temporary.replace(pool_file)
    status.update(items_available=len(items))
    if ctx.get("refresh_only"):
        return {"available": len(items), "fetched": fetched_total, "errors": errors}

    ctx.state.prune(int(nd.get("dedupe_keep_days", 3)))
    candidates = items if ctx.get("force_digest") else [it for it in items if not ctx.state.is_seen(it["hash"])]
    top = recommend.select(candidates, int(nd.get("max_items", 65)),
                           int(nd.get("max_per_source", 12)),
                           float(nd.get("discovery_ratio", 0.2)))

    # 5. LLM 蒸馏（失败自动降级本地兜底；原因记录到状态，页面可直接展示）
    raw_text, used_llm, llm_error = distill.compose(top, date_str, cfg)

    # 6. 渲染：按素材编号回填真实标题/来源/时间/原文链接，生成带层级的简报正文
    built = render.build(
        render.parse(raw_text), top, date_str,
        used_llm=used_llm, llm_error=llm_error,
        fetched_total=fetched_total, kept_total=len(items),
        highlight_count=int(nd.get("highlight_count", 15)),
        appendix_limit=int(nd.get("appendix_limit", 30)),
    )
    text = built["markdown"]
    subject = built["subject"]
    items_shown = len(built["shown_indices"])
    ctx.log.info("简报渲染完成：共 %d 条（重点 %d 条），正文 %d 字符",
                 items_shown, built["matched"], len(text))

    # 7. 存档（即使推送失败，本地始终有完整记录）
    out_dir = Path(nd.get("output_dir", cfg["paths"]["output"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"digest-{date_str}.md"
    out_file.write_text(text, encoding="utf-8")

    # 8. 推送（多渠道并行，单渠道失败不影响其他）
    push_results: dict = {}
    push_cfg = nd.get("push", {})
    if push_cfg.get("enabled", True):
        only: Optional[list] = push_cfg.get("channels") or None
        push_results = broadcast(subject, text, cfg, ctx.log, only=only)

    # 9. 落库。
    #    关键：只有「确实送达」才把素材标记为已见。
    #    原先无论推送成败都标记，导致推送失败后重试时素材已被去重掉，
    #    简报会变成"今日无重要新闻"——现在重试仍能拿到同一批素材。
    delivered = (not push_results) or any(push_results.values())
    if delivered:
        ctx.state.mark_seen_many([top[i - 1] for i in built["shown_indices"]])
    else:
        ctx.log.warning("本次推送全部失败，素材不标记为已见，重试时可重新使用")
    ctx.state.mark_digest(date_str, text, sorted(push_results) if push_results else [])
    ctx.state.prune(int(nd.get("dedupe_keep_days", 3)))

    # 10. 状态更新（可观测性）
    status.update(
        module="news_digest",
        digest_date=date_str,
        items_kept=len(items),
        items_shown=items_shown,
        used_llm=used_llm,
        llm_error=llm_error,
        output_file=str(out_file),
        push=push_results,
    )
    if errors:
        status.record_error("fetch", f"{len(errors)} 个来源抓取失败: "
                                    + "; ".join(e["source"] for e in errors[:5]))
    if llm_error:
        status.record_error("llm", llm_error[:500])

    summary = {
        "module": "news_digest",
        "date": date_str,
        "fetched": fetched_total,
        "kept": len(items),
        "items_shown": items_shown,
        "used_llm": used_llm,
        "llm_error": llm_error,
        "output_file": str(out_file),
        "push": push_results,
    }
    return summary


# 注册模块（模块自描述，核心零改动）
register(Module(id="news_digest", name="新闻简报", run=run, config_section="news_digest"))
