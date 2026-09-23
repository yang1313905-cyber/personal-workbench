"""简报渲染：把 LLM 的「分析文本」与真实素材数据合成最终简报。

核心设计原则
------------
LLM 只负责**挑选哪几条、以及怎么写分析**，它用素材编号（如 ``[7]``）来指代新闻；
标题、来源、时间、原文链接一律由本模块按编号从真实抓取结果回填。

这样做的两个理由：
1. 链接永远指向真实原文 —— 大模型自己写 URL 极易编造出看起来像但不存在的链接；
2. 标题与原文严格一致 —— 不会出现「简报名和点进去的新闻对不上」。

产出物是**带层级的 Markdown**：``##`` 章节 → ``###`` 编号标题（含链接）→ 正文。
邮件渠道（channels/markdown_email.py）会把它渲染成有字体层级的 HTML 邮件。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 解析

_HEADING_RE = re.compile(r"^\s*#{1,4}\s*(.+?)\s*#*\s*$")
# 兼容 LLM 可能写出的多种编号形式：[7] 【7】 #7 7. 7、 7)
_INDEX_RE = re.compile(r"^\s*(?:[-*•]\s*)?(?:\[(\d+)\]|【(\d+)】|#(\d+)|(\d+)\s*[.、)）:：])\s*(.*)$")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+\s*[.、)）])\s+(.*)$")

_CATEGORY_ZH = {
    "tech": "科技", "ai": "AI", "world": "国际", "finance": "财经",
    "business": "商业", "china": "国内", "science": "科学", "security": "安全",
}


def _section_of(title: str) -> str:
    """把 LLM 写的章节标题归一化，容忍措辞差异。"""
    t = title.strip().strip("：: ")
    if "重点" in t or "头条" in t or "要闻" in t:
        return "重点"
    if "趋势" in t or "观察" in t or "综述" in t:
        return "趋势"
    if "信号" in t or "风险" in t or "关注" in t:
        return "信号"
    return "其他"


def parse(text: str) -> Dict:
    """解析 LLM 输出为结构化数据。

    返回 ``{"highlights": [{"index": int, "text": str}], "trend": str,
    "signals": [str], "other": [str]}``。
    容错：不依赖严格的章节顺序，多余内容归入 ``other``。
    """
    highlights: List[dict] = []
    trend_lines: List[str] = []
    signals: List[str] = []
    other: List[str] = []
    section: Optional[str] = None
    current: Optional[dict] = None

    for raw in (text or "").splitlines():
        line = raw.rstrip()
        m = _HEADING_RE.match(line)
        if m:
            section = _section_of(m.group(1))
            current = None
            continue

        if section == "重点":
            idx = _INDEX_RE.match(line)
            if idx and line.strip():
                num = next(g for g in idx.groups()[:4] if g)
                body = (idx.group(5) or "").strip()
                current = {"index": int(num), "lines": [body] if body else []}
                highlights.append(current)
                continue
            if line.strip():
                if current is not None:
                    current["lines"].append(line.strip().lstrip("-*• ").strip())
                else:
                    other.append(line.strip())
            continue

        if section == "趋势":
            trend_lines.append(line)
            continue

        if section == "信号":
            s = line.strip()
            s = _BULLET_RE.sub(r"\1", s) if _BULLET_RE.match(s) else s.lstrip("-*• ").strip()
            if s:
                signals.append(s)
            continue

        if line.strip():
            other.append(line.strip())

    parsed_highlights = []
    for h in highlights:
        body = " ".join(x for x in h["lines"] if x).strip()
        parsed_highlights.append({"index": h["index"], "text": _strip_inline_md(body)})

    return {
        "highlights": parsed_highlights,
        "trend": "\n".join(trend_lines).strip(),
        "signals": signals,
        "other": other,
    }


def _strip_inline_md(s: str) -> str:
    """去掉行内 markdown 标记，只保留纯文本（分析段落不需要行内链接）。"""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", s)
    s = re.sub(r"\[(.+?)\]\((https?://[^\s)]+)\)", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()


# ---------------------------------------------------------------- 工具

def _md_link_text(s: str) -> str:
    """转义 Markdown 链接文本里会破坏语法的字符。"""
    return (s or "").replace("[", "（").replace("]", "）").replace("\n", " ").strip()


def _md_url(u: str) -> str:
    return (u or "").strip().replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def format_time(published: str) -> str:
    """ISO 时间 → 本地时区的 'MM-DD HH:MM'。"""
    if not published:
        return ""
    try:
        dt = datetime.fromisoformat(published)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return ""


def _meta_line(item: dict) -> str:
    parts = [item.get("source_name") or "未知来源"]
    cat = _CATEGORY_ZH.get(str(item.get("category") or "").strip().lower())
    if cat:
        parts.append(cat)
    ts = format_time(item.get("published") or "")
    if ts:
        parts.append(ts)
    return " · ".join(parts)


def resolve(parsed: Dict, items: List[dict]) -> Tuple[List[dict], set]:
    """把编号解析为真实素材。返回 (命中的重点列表, 已用编号集合)。

    编号越界、重复、或分析为空的一律丢弃 —— 宁可少一条，也不给出错误链接。
    """
    picked: List[dict] = []
    used: set = set()
    for h in parsed.get("highlights", []):
        i = int(h.get("index") or 0)
        text = (h.get("text") or "").strip()
        if not (1 <= i <= len(items)) or i in used or not text:
            continue
        used.add(i)
        picked.append({"item": items[i - 1], "analysis": text})
    return picked, used


# ---------------------------------------------------------------- 渲染

def build(parsed: Dict, items: List[dict], date_str: str, *,
          used_llm: bool = True, llm_error: Optional[str] = None,
          fetched_total: int = 0, kept_total: int = 0,
          highlight_count: int = 5, appendix_limit: int = 10,
          generated_at: Optional[str] = None) -> Dict[str, str]:
    """合成最终简报（Markdown）。

    返回 ``{"markdown": str, "subject": str, "headline": str, "matched": int}``：
    - ``markdown``：推送与存档正文（带 ``###`` 编号标题与原文链接）
    - ``subject``：邮件主题（含当天头条，收件箱里就能看到重点）
    - ``headline``：头条标题（用于邮件摘要行/预览）
    """
    picked, used = resolve(parsed, items)

    # 解析不到任何有效编号时（LLM 没按格式输出），降级为按排序取前 N 条，
    # 保证邮件永远是"有标题有链接"的正常样子。
    unmatched_note = False
    if not picked and items:
        unmatched_note = True
        for i, it in enumerate(items[:highlight_count], 1):
            picked.append({"item": it, "analysis": (it.get("summary") or "").strip()[:200] or "（无摘要）"})
            used.add(i)

    lines: List[str] = []
    lines.append("## 今日重点")
    lines.append("")
    if not picked:
        lines.append("今日无重要新闻（抓取结果为空或全部被过滤）。")
        lines.append("")
    for n, entry in enumerate(picked, 1):
        it = entry["item"]
        title = _md_link_text(it.get("title") or "（无标题）")
        url = _md_url(it.get("link") or "")
        if url:
            lines.append(f"### {n}. [{title}]({url})")
        else:
            lines.append(f"### {n}. {title}")
        lines.append(f"*{_meta_line(it)}*")
        lines.append("")
        lines.append(entry["analysis"])
        lines.append("")

    trend = (parsed.get("trend") or "").strip()
    if trend:
        lines.append("## 趋势观察")
        lines.append("")
        lines.append(trend)
        lines.append("")

    signals = [s for s in (parsed.get("signals") or []) if s.strip()]
    if signals:
        lines.append("## 信号与风险")
        lines.append("")
        for s in signals[:8]:
            lines.append(f"- {s}")
        lines.append("")

    # 附录：未入选重点但值得一读的条目，同样带链接，方便随时跳转
    appendix = [it for i, it in enumerate(items, 1) if i not in used][:appendix_limit]
    if appendix:
        lines.append("## 其他值得一读")
        lines.append("")
        for it in appendix:
            title = _md_link_text(it.get("title") or "（无标题）")
            url = _md_url(it.get("link") or "")
            src = it.get("source_name") or ""
            if url:
                lines.append(f"- [{title}]({url}) — {src}")
            else:
                lines.append(f"- {title} — {src}")
        lines.append("")

    stamp = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    foot = (f"个人智能工作台 · {date_str} {stamp.split(' ')[-1]} 生成"
            f" · 素材 {fetched_total} 条，收录 {kept_total} 条，精选 {len(picked)} 条")
    if not used_llm:
        foot += " · 本次为本地兜底模式（LLM 未参与）"
    if unmatched_note:
        foot += " · 分析文本未按格式返回，已自动降级"
    lines.append("---")
    lines.append(f"*{foot}*")
    if not used_llm and llm_error:
        lines.append(f"*LLM 失败原因：{str(llm_error)[:200]}*")

    markdown = "\n".join(lines).strip() + "\n"

    headline = ""
    if picked:
        headline = (picked[0]["item"].get("title") or "").strip()
    short = headline if len(headline) <= 30 else headline[:30] + "…"
    subject = f"📰 {date_str[5:]} 简报｜{short}" if short else f"📰 今日新闻简报 {date_str}"
    return {"markdown": markdown, "subject": subject, "headline": headline, "matched": len(picked)}
