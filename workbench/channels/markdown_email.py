"""把简报 Markdown 渲染成有排版的邮件 HTML，以及纯文本版本。

设计目标：
- 编辑晨报质感：暖石浅底 + 深石板报头 + 独立卡片式重点新闻 + 柔和色块趋势与信号卡
- 100% 内联 CSS + table 布局，兼容 QQ 邮箱 / Apple Mail / Gmail / Outlook / 移动端
- 修复旧版痛点：正文与标题/元信息左对齐统一、取消多行标题下划线噪点、每条重点清晰分隔
- 严格 HTML 转义，防止新闻标题中的特殊字符或标签破坏排版
"""
from __future__ import annotations

import html
import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 样式常量

FONT = ("-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC','Hiragino Sans GB',"
        "'Microsoft YaHei',sans-serif")
LINK_STYLE = "color:#0f4c81;text-decoration:none;border-bottom:1px solid rgba(15,76,129,0.28);"
S_ITEM_TITLE = "font-size:16px;font-weight:700;color:#0f2b4c;text-decoration:none;line-height:1.48;letter-spacing:-0.1px;"
S_BADGE = ("display:inline-block;min-width:24px;height:21px;line-height:21px;text-align:center;"
           "background:#0f172a;color:#ffffff;border-radius:6px;font-size:12px;font-weight:700;"
           "margin-right:8px;vertical-align:middle;padding:0 4px;")
S_SRC_PILL = ("display:inline-block;background:#eaf2fb;color:#124a84;border-radius:999px;"
              "padding:2px 9px;font-size:12px;font-weight:600;line-height:1.4;vertical-align:middle;"
              "margin-right:6px;")
S_CAT_PILL = ("display:inline-block;background:#f1f5f9;color:#475569;border-radius:999px;"
              "padding:2px 8px;font-size:12px;font-weight:500;line-height:1.4;vertical-align:middle;"
              "margin-right:6px;")
S_TIME = "font-size:12px;color:#8391a5;vertical-align:middle;"
S_META = "margin:0 0 8px 0;font-size:12px;color:#8391a5;line-height:1.6;"
S_CARD = ("margin:0 0 13px;padding:15px 18px 16px;background:#fbfcfe;"
          "border:1px solid #e6edf5;border-radius:12px;")
S_BODY = "margin:9px 0 0;font-size:14px;color:#334155;line-height:1.78;"
S_SECTION = ("margin:26px 0 14px;padding:2px 0 2px 11px;border-left:4px solid #d49b3a;"
             "font-size:15px;font-weight:700;color:#0f172a;line-height:1.35;letter-spacing:0.3px;")
S_TREND_BOX = ("margin:0 0 12px;padding:14px 18px;background:#fcf9f2;"
               "border:1px solid #efe4ce;border-left:3px solid #d49b3a;border-radius:10px;")
S_SIGNAL_BOX = ("margin:0 0 12px;padding:12px 18px 8px;background:#f8fafc;"
                "border:1px solid #e6edf5;border-radius:12px;")
S_BRIEF_BOX = ("margin:0 0 12px;padding:4px 16px;background:#ffffff;"
               "border:1px solid #e6edf5;border-radius:12px;")
S_P = "margin:0 0 12px;font-size:14px;color:#334155;line-height:1.8;"
S_LI = "margin:0 0 9px;font-size:14px;color:#334155;line-height:1.72;"
S_SRC = ("display:inline-block;background:#f1f5f9;color:#64748b;border-radius:999px;"
         "padding:1px 8px;font-size:12px;margin-left:6px;white-space:nowrap;")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_ITEM_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*•]\s+(.*)$")
_META_RE = re.compile(r"^\*(.+?)\*$")
_LINK_RE = re.compile(r"\[(.+?)\]\((https?://[^\s)]+)\)")
_HR_RE = re.compile(r"^\s*-{3,}\s*$")


# ---------------------------------------------------------------- 行内格式化

def _inline(text: str, link_style: str = LINK_STYLE) -> str:
    """转义 + 行内语法（链接、粗体、斜体）。先取链接占位，避免转义破坏 URL。"""
    links: List[Tuple[str, str]] = []

    def _stash(m: "re.Match") -> str:
        links.append((m.group(1), m.group(2)))
        return f"\x00{len(links) - 1}\x00"

    text = _LINK_RE.sub(_stash, text)
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", out)

    def _restore(m: "re.Match") -> str:
        label, url = links[int(m.group(1))]
        return (f'<a href="{html.escape(url, quote=True)}" style="{link_style}">'
                f"{html.escape(label)}</a>")

    return re.sub("\x00(\\d+)\x00", _restore, out)


def first_link(md: str) -> Tuple[str, str]:
    """取简报中第一条 `### n. [标题](链接)` 的标题与链接（用作邮件预览行）。"""
    for line in (md or "").splitlines():
        m = _HEADING_RE.match(line.strip())
        if not m or len(m.group(1)) != 3:
            continue
        item = _ITEM_RE.match(m.group(2).strip())
        if not item:
            continue
        link = _LINK_RE.search(item.group(2))
        if link:
            return link.group(1), link.group(2)
    return "", ""


def _extract_stats_pill(md: str) -> str:
    """从页脚提取本期条数摘要，展示在报头徽章里。"""
    m = re.search(r"(本期\s*\d+\s*条（[^）]+）)", md or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------- 结构化渲染

def _render_meta_pills(meta_text: str) -> str:
    """把 `TechCrunch · 科技 · 11-26 03:44` 渲染成清爽的徽章行。"""
    parts = [p.strip() for p in meta_text.split("·") if p.strip()]
    if not parts:
        return ""
    chips: List[str] = []
    # 第一段是来源名
    chips.append(f'<span style="{S_SRC_PILL}">{html.escape(parts[0])}</span>')
    for part in parts[1:]:
        if re.match(r"^\d{2}-\d{2}\s+\d{2}:\d{2}$", part):
            chips.append(f'<span style="{S_TIME}">{html.escape(part)}</span>')
        elif "来源摘要" in part:
            chips.append(
                '<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                'border-radius:999px;padding:2px 8px;font-size:12px;margin-left:4px;'
                f'vertical-align:middle;">{html.escape(part)}</span>'
            )
        else:
            chips.append(f'<span style="{S_CAT_PILL}">{html.escape(part)}</span>')
    return "".join(chips)


def _render_highlight_card(card: Dict) -> str:
    num = card["num"]
    rest = card["rest"]
    meta = card.get("meta") or ""
    body_lines = card.get("body") or []

    link = _LINK_RE.search(rest)
    if link:
        title_html = (f'<a href="{html.escape(link.group(2), quote=True)}" '
                      f'style="{S_ITEM_TITLE}">{html.escape(link.group(1))}</a>')
    else:
        title_html = f'<span style="{S_ITEM_TITLE}">{html.escape(rest)}</span>'

    top_row_parts = [f'<span style="{S_BADGE}">{html.escape(num)}</span>']
    if meta:
        top_row_parts.append(_render_meta_pills(meta))
    top_row = f'<div style="margin:0 0 9px;line-height:1.5;">{"".join(top_row_parts)}</div>'
    title_row = f'<div style="margin:0;">{title_html}</div>'
    body_html = "".join(
        f'<p style="{S_BODY}">{_inline(p)}</p>' for p in body_lines
    )
    return f'<div style="{S_CARD}">{top_row}{title_row}{body_html}</div>'


def _brief_row(text: str, is_last: bool) -> str:
    border = "" if is_last else "border-bottom:1px solid #eef2f6;"
    m = re.match(r"^(.*?)\s+—\s+(.+)$", text)
    brief_link_style = "color:#1e293b;text-decoration:none;font-weight:500;"
    if m and _LINK_RE.search(m.group(1)):
        content = (f'{_inline(m.group(1), link_style=brief_link_style)}'
                   f'<span style="{S_SRC}">{html.escape(m.group(2))}</span>')
    else:
        content = _inline(text, link_style=brief_link_style)
    return (f'<div style="padding:10px 0;{border}font-size:14px;color:#334155;'
            f'line-height:1.58;">'
            f'<span style="color:#d49b3a;font-weight:700;margin-right:7px;">›</span>'
            f'{content}</div>')


def md_to_html(md: str) -> str:
    """简报 Markdown → 邮件正文 HTML 片段（不含外层模板）。"""
    out: List[str] = []
    section_kind = ""
    pending_card: Optional[Dict] = None
    trend_paras: List[str] = []
    bullets: List[str] = []

    def flush_card() -> None:
        nonlocal pending_card
        if pending_card is not None:
            out.append(_render_highlight_card(pending_card))
            pending_card = None

    def flush_trend() -> None:
        if trend_paras:
            inner = "".join(
                f'<p style="margin:0 0 {0 if idx == len(trend_paras) - 1 else 10}px;'
                f'font-size:14px;color:#3b3222;line-height:1.82;">{_inline(p)}</p>'
                for idx, p in enumerate(trend_paras)
            )
            out.append(f'<div style="{S_TREND_BOX}">{inner}</div>')
            trend_paras.clear()

    def flush_bullets() -> None:
        if not bullets:
            return
        if section_kind == "briefs":
            rows = "".join(
                _brief_row(item, idx == len(bullets) - 1)
                for idx, item in enumerate(bullets)
            )
            out.append(f'<div style="{S_BRIEF_BOX}">{rows}</div>')
        elif section_kind == "signals":
            items_html = "".join(
                f'<li style="{S_LI}">{_inline(item)}</li>' for item in bullets
            )
            out.append(
                f'<div style="{S_SIGNAL_BOX}">'
                f'<ul style="margin:0 0 0 18px;padding:0;color:#d49b3a;">{items_html}</ul>'
                f'</div>'
            )
        else:
            items_html = []
            for item in bullets:
                m = re.match(r"^(.*?)\s+—\s+(.+)$", item)
                if m and _LINK_RE.search(m.group(1)):
                    items_html.append(
                        f'<li style="{S_LI}">{_inline(m.group(1))} '
                        f'<span style="{S_SRC}">{html.escape(m.group(2))}</span></li>'
                    )
                else:
                    items_html.append(f'<li style="{S_LI}">{_inline(item)}</li>')
            out.append('<ul style="margin:0 0 18px 20px;padding:0;">' + "".join(items_html) + "</ul>")
        bullets.clear()

    def flush_all() -> None:
        flush_card()
        flush_trend()
        flush_bullets()

    for raw in (md or "").splitlines():
        line = raw.strip()

        if not line:
            flush_bullets()
            continue

        if _HR_RE.match(line):
            flush_all()
            section_kind = "footer"
            out.append('<div style="margin:26px 0 14px;border-top:1px solid #e6edf5;"></div>')
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush_all()
            level, text = len(heading.group(1)), heading.group(2).strip()
            if level <= 2:
                if "趋势" in text or "观察" in text:
                    section_kind = "trend"
                elif "信号" in text or "风险" in text:
                    section_kind = "signals"
                elif "其他" in text or "快讯" in text or "一读" in text:
                    section_kind = "briefs"
                elif "重点" in text or "头条" in text:
                    section_kind = "highlights"
                else:
                    section_kind = ""
                out.append(f'<div style="{S_SECTION}">{html.escape(text)}</div>')
            else:
                item = _ITEM_RE.match(text)
                if item:
                    pending_card = {
                        "num": item.group(1),
                        "rest": item.group(2).strip(),
                        "meta": "",
                        "body": [],
                    }
                else:
                    out.append(f'<div style="margin:20px 0 10px;font-size:15px;'
                               f'font-weight:700;color:#0f172a;">{html.escape(text)}</div>')
            continue

        meta = _META_RE.match(line)
        if meta:
            inner = meta.group(1)
            if pending_card is not None and not pending_card["meta"] and "个人智能工作台" not in inner:
                pending_card["meta"] = inner
            else:
                flush_all()
                if "个人智能工作台" in inner or "LLM 失败原因" in inner:
                    out.append(f'<div style="margin:4px 0;font-size:12px;color:#8391a5;'
                               f'line-height:1.7;">{html.escape(inner)}</div>')
                else:
                    out.append(f'<div style="{S_META}">{_inline(inner)}</div>')
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            flush_card()
            flush_trend()
            bullets.append(bullet.group(1).strip())
            continue

        if pending_card is not None:
            pending_card["body"].append(line)
            continue

        if section_kind == "trend":
            trend_paras.append(line)
            continue

        flush_bullets()
        out.append(f'<p style="{S_P}">{_inline(line)}</p>')

    flush_all()
    return "\n".join(out)


def render_email(md: str, subject: str, date_text: str = "") -> str:
    """生成完整的邮件 HTML（内联样式 + 隐藏预览行）。"""
    headline, _headline_url = first_link(md)
    preview = headline[:80] if headline else subject
    if date_text == "":
        m = re.search(r"(\d{4}-\d{2}-\d{2})", md or "")
        date_text = m.group(1) if m else ""
    stats_pill = _extract_stats_pill(md)

    preview_html = ""
    if preview:
        preview_html = (f'<div style="display:none;max-height:0;overflow:hidden;'
                        f'font-size:1px;color:#eef2f6;">{html.escape(preview)}</div>')

    stats_badge = ""
    if stats_pill:
        stats_badge = (
            f'<span style="display:inline-block;margin:4px 6px 0 0;padding:3px 10px;'
            f'border-radius:999px;background:rgba(255,255,255,0.12);color:#e2e8f0;'
            f'font-size:12px;vertical-align:middle;">{html.escape(stats_pill)}</span>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#eef2f6;">
{preview_html}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#eef2f6;padding:24px 12px;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="max-width:680px;background:#ffffff;border-radius:16px;overflow:hidden;
                  border:1px solid #e2e8f0;box-shadow:0 4px 20px rgba(15,23,42,0.06);
                  font-family:{FONT};">
      <tr><td style="height:4px;background:#d49b3a;font-size:0;line-height:0;">&nbsp;</td></tr>
      <tr><td style="background:#0f172a;background-image:linear-gradient(135deg,#0f172a 0%,#1e293b 60%,#1c385a 100%);padding:26px 28px 24px;">
        <div style="font-size:11px;letter-spacing:2.4px;color:#94a3b8;
                    text-transform:uppercase;font-weight:600;">Personal Workbench · Daily Briefing</div>
        <div style="margin-top:8px;font-size:24px;font-weight:700;color:#ffffff;
                    letter-spacing:0.3px;line-height:1.25;">今日新闻简报</div>
        <div style="margin-top:8px;font-size:13px;color:#cbd5e1;line-height:1.5;">
          <span style="display:inline-block;margin:4px 6px 0 0;padding:3px 10px;border-radius:999px;background:rgba(212,155,58,0.22);color:#f6d38b;font-size:12px;font-weight:600;vertical-align:middle;">{html.escape(date_text or subject)}</span>{stats_badge}
        </div>
      </td></tr>
      <tr><td style="padding:8px 26px 28px;">
{md_to_html(md)}
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


# ---------------------------------------------------------------- 纯文本

def md_to_text(md: str) -> str:
    """简报 Markdown → 纯文本（不支持 HTML 的客户端 / 通知渠道使用）。

    链接保留 URL，方便在纯文本环境里复制打开。
    """
    out: List[str] = []
    for raw in (md or "").splitlines():
        line = raw.strip()
        if not line:
            out.append("")
            continue
        if _HR_RE.match(line):
            out.append("─" * 32)
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            level, text = len(heading.group(1)), heading.group(2).strip()
            if level <= 2:
                out.append("")
                out.append(f"【{text}】")
                out.append("")
            else:
                item = _ITEM_RE.match(text)
                if item:
                    link = _LINK_RE.search(item.group(2))
                    num, title = item.group(1), (link.group(1) if link else item.group(2))
                    out.append("")
                    out.append(f"{num}. {title}")
                    if link:
                        out.append(f"   {link.group(2)}")
                else:
                    out.append("")
                    out.append(text)
            continue
        meta = _META_RE.match(line)
        if meta:
            out.append(f"   （{meta.group(1)}）")
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            text = bullet.group(1).strip()
            link = _LINK_RE.search(text)
            if link:
                text = (text[:link.start()] + f"{link.group(1)} {link.group(2)}"
                        + text[link.end():])
            out.append(f"· {text}")
            continue
        link = _LINK_RE.search(line)
        if link:
            line = line[:link.start()] + f"{link.group(1)}（{link.group(2)}）" + line[link.end():]
        out.append(re.sub(r"\*\*(.+?)\*\*", r"\1", line))

    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
