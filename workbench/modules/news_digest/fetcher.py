"""新闻抓取：数据源适配层。

当前内置 kind=rss（标准 RSS/Atom），覆盖绝大多数主流媒体。
要接入"无 RSS 的 API 源"或自定义逻辑（如 X 抓取），在 fetch_source 中
按 kind 分发即可，扩展点清晰，不影响其他部分。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import feedparser
import requests

from ...core.retry import retry
from .cleaner import clean_text, item_hash

log = logging.getLogger("workbench.news.fetch")

DEFAULT_UA = "Mozilla/5.0 (compatible; PersonalWorkbench/0.1; +https://example.com)"


def _to_iso(published_parsed) -> str:
    if not published_parsed:
        return ""
    try:
        return datetime(*published_parsed[:6], tzinfo=timezone.utc).isoformat()
    except Exception:
        return ""


def fetch_rss(src: dict, http_cfg: dict) -> List[dict]:
    url = src["url"]
    headers = {**http_cfg.get("headers", {}), "User-Agent": DEFAULT_UA}
    resp = requests.get(
        url,
        headers=headers,
        timeout=float(http_cfg.get("timeout", 20)),
        proxies=http_cfg.get("proxies") or None,
    )
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"RSS 解析失败: {feed.bozo_exception}")

    items: List[dict] = []
    for entry in feed.entries[: int(src.get("limit", 30))]:
        title = clean_text(entry.get("title") or "")
        if not title:
            continue
        link = entry.get("link") or ""
        summary = clean_text(entry.get("summary") or entry.get("description") or "")
        items.append(
            {
                "source_id": src["id"],
                "source_name": src.get("name", src["id"]),
                "lang": src.get("lang", "en"),
                "category": src.get("category", ""),
                "weight": float(src.get("weight", 1.0)),
                "title": title,
                "summary": summary,
                "link": link,
                "published": _to_iso(entry.get("published_parsed")),
                "hash": item_hash(src["id"], link, title),
            }
        )
    return items


def fetch_wallstreetcn(src: dict, http_cfg: dict) -> List[dict]:
    """华尔街见闻 JSON 信息流接口（https://api-one.wallstcn.com）。

    该接口返回 JSON 而非 RSS，这里把它适配成统一 item 结构。
    这也是"扩展点"的示例：任何 JSON API 源都能照此接入。
    """
    headers = {**http_cfg.get("headers", {}), "User-Agent": DEFAULT_UA}
    resp = requests.get(
        src["url"],
        headers=headers,
        timeout=float(http_cfg.get("timeout", 20)),
        proxies=http_cfg.get("proxies") or None,
    )
    resp.raise_for_status()
    data = resp.json()
    raw_items = (data.get("data") or {}).get("items") or []

    items: List[dict] = []
    for raw in raw_items[: int(src.get("limit", 20))]:
        res = raw.get("resource") or {}
        title = clean_text(res.get("title") or "")
        if not title:
            continue
        link = res.get("uri") or ""
        if link and not link.startswith("http"):
            link = "https://wallstreetcn.com" + link
        summary = clean_text(res.get("content_short") or res.get("subtitle") or "")
        ts = res.get("display_time")
        published = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat() if ts else ""
        items.append(
            {
                "source_id": src["id"],
                "source_name": src.get("name", src["id"]),
                "lang": src.get("lang", "zh"),
                "category": src.get("category", ""),
                "weight": float(src.get("weight", 1.0)),
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "hash": item_hash(src["id"], link, title),
            }
        )
    return items


def fetch_source(src: dict, http_cfg: dict) -> List[dict]:
    kind = src.get("kind", "rss")
    if kind == "rss":
        return fetch_rss(src, http_cfg)
    if kind == "wallstreetcn":
        return fetch_wallstreetcn(src, http_cfg)
    # ---- 扩展点：接入新类型数据源 ----
    # if kind == "api":   return fetch_my_api(src, http_cfg)
    # if kind == "x":     return fetch_x(src, http_cfg)
    raise ValueError(f"未知数据源类型 kind={kind}（请在 fetcher.fetch_source 中扩展）")


def fetch_all(sources: List[dict], http_cfg: dict) -> tuple[List[dict], List[dict]]:
    """抓取全部启用来源。单源失败只记录，不影响其他源。

    返回 (items, errors)，errors 为 [{source, error}]。
    """
    all_items: List[dict] = []
    errors: List[dict] = []
    for src in sources:
        if not src.get("enabled", True):
            continue
        # 单源可覆盖全局重试次数（如已知不稳定的源可设 retries: 0 快速失败）
        attempts = max(1, int(src.get("retries", http_cfg.get("retries", 2))) + 1)
        try:
            items = retry(
                lambda: fetch_source(src, http_cfg),
                attempts=attempts,
                delay=2.0,
                what=f"抓取 {src.get('name', src['id'])}",
            )
            all_items.extend(items)
            log.info("来源 %s：%d 条", src.get("name", src["id"]), len(items))
        except Exception as e:  # noqa: BLE001
            errors.append({"source": src.get("id"), "error": str(e)})
            log.warning("来源 %s 抓取失败: %s", src.get("id"), e)
    return all_items, errors
