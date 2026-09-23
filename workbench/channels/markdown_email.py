"""把简报 Markdown 渲染成有排版的邮件 HTML，以及纯文本版本。

为什么需要它：原来 SMTP 渠道把正文塞进一个 ``<pre>`` 里，导致
1）所有文字一个字号、没有重点；2）Markdown 链接不会变成可点的超链接。
这里实现一个只针对**本简报实际使用的 Markdown 子集**的小型渲染器，
全部输出内联样式（QQ 邮箱等客户端对内联样式支持最好），并做好 HTML 转义。

支持的语法：``##`` 章节 / ``### 1. [标题](链接)`` 编号条目 / ``*元信息*`` /
``- 列表`` / ``---`` 分隔线 / ``**粗体**`` / ``[文本](链接)``。
"""
from __future__ import annotations

import html
import re
from typing import List, Tuple

# ---------------------------------------------------------------- 样式常量

FONT = ("-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB',"
        "'Microsoft YaHei',sans-serif")
LINK_STYLE = "color:#0b5fa5;text-decoration:none;border-bottom:1px solid rgba(11,95,165,.35);"
S_ITEM_TITLE = f"font-size:16px;font-weight:700;color:#0b5fa5;text-decoration:none;line-height:1.5;{LINK_STYLE}"
S_BADGE = ("display:inline-block;min-width:22px;height:22px;line-height:22px;text-align:center;"
           "background:#1a2a3a;color:#ffffff;border-radius:7px;font-size:12px;font-weight:700;"
           "margin-right:9px;vertical-align:2px;")
S_META = "margin:7px 0 0 31px;font-size:12px;color:#8a94a6;line-height:1.6;"
S_BODY = "margin:9px 0 22px 31px;font-size:14px;color:#2b3440;line-height:1.8;"
S_SECTION = ("margin:30px 0 14px;padding-left:11px;border-left:4px solid #c8892b;"
             "font-size:15px;font-weight:700;color:#1a2a3a;line-height:1.3;")
S_P = "margin:0 0 15px;font-size:14px;color:#2b3440;line-height:1.8;"
S_LI = "margin:0 0 9px;font-size:14px;color:#2b3440;line-height:1.7;"
S_SRC = "color:#9aa4b2;font-size:12px;"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_ITEM_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*•]\s+(.*)$")
_META_RE = re.compile(r"^\*(.+?)\*$")
_LINK_RE = re.compile(r"\[(.+?)\]\((https?://[^\s)]+)\)")
_HR_RE = re.compile(r"^\s*-{3,}\s*$")


# ---------------------------------------------------------------- 行内格式化

def _inline(text: str) -> str:
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
        return (f'<a href="{html.escape(url, quote=True)}" style="{LINK_STYLE}">'
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


# ---------------------------------------------------------------- HTML

def _item_block(num: str, rest: str) -> str:
    link = _LINK_RE.search(rest)
    if link:
        title_html = (f'<a href="{html.escape(link.group(2), quote=True)}" '
                      f'style="{S_ITEM_TITLE}">{html.escape(link.group(1))}</a>')
    else:
        title_html = f'<span style="{S_ITEM_TITLE}">{html.escape(rest)}</span>'
    return (f'<div style="margin:0 0 2px;">'
            f'<span style="{S_BADGE}">{html.escape(num)}</span>{title_html}</div>')


def _li_block(text: str) -> str:
    m = re.match(r"^(.*?)\s+—\s+(.+)$", text)
    if m and _LINK_RE.search(m.group(1)):
        return (f'<li style="{S_LI}">{_inline(m.group(1))} '
                f'<span style="{S_SRC}">— {html.escape(m.group(2))}</span></li>')
    return f'<li style="{S_LI}">{_inline(text)}</li>'


def md_to_html(md: str) -> str:
    """简报 Markdown → 邮件正文 HTML 片段（不含外层模板）。"""
    out: List[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in (md or "").splitlines():
        line = raw.strip()

        if not line:
            close_ul()
            continue

        if _HR_RE.match(line):
            close_ul()
            out.append('<div style="margin:26px 0 14px;border-top:1px solid #e8ebef;"></div>')
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            close_ul()
            level, text = len(heading.group(1)), heading.group(2).strip()
            if level <= 2:
                out.append(f'<div style="{S_SECTION}">{html.escape(text)}</div>')
            else:
                item = _ITEM_RE.match(text)
                if item:
                    out.append(_item_block(item.group(1), item.group(2).strip()))
                else:
                    out.append(f'<div style="margin:20px 0 10px;font-size:15px;'
                               f'font-weight:700;color:#1a2a3a;">{html.escape(text)}</div>')
            continue

        meta = _META_RE.match(line)
        if meta:
            close_ul()
            inner = meta.group(1)
            if "个人智能工作台" in inner:
                out.append(f'<div style="margin:6px 0;font-size:12px;color:#9aa4b2;'
                           f'line-height:1.7;">{html.escape(inner)}</div>')
            else:
                out.append(f'<div style="{S_META}">{_inline(inner)}</div>')
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            if not in_ul:
                out.append('<ul style="margin:0 0 20px 34px;padding:0;">')
                in_ul = True
            out.append(_li_block(bullet.group(1).strip()))
            continue

        close_ul()
        out.append(f'<p style="{S_P}">{_inline(line)}</p>')

    close_ul()
    return "\n".join(out)


def render_email(md: str, subject: str, date_text: str = "") -> str:
    """生成完整的邮件 HTML（内联样式 + 隐藏预览行）。"""
    headline, headline_url = first_link(md)
    preview = headline[:80] if headline else subject
    if date_text == "":
        m = re.search(r"(\d{4}-\d{2}-\d{2})", md or "")
        date_text = m.group(1) if m else ""

    preview_html = ""
    if preview:
        preview_html = (f'<div style="display:none;max-height:0;overflow:hidden;'
                        f'font-size:1px;color:#f4f5f7;">{html.escape(preview)}</div>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#f4f5f7;">
{preview_html}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#f4f5f7;padding:24px 12px;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="max-width:680px;background:#ffffff;border-radius:14px;overflow:hidden;
                  box-shadow:0 1px 3px rgba(16,24,40,.08);font-family:{FONT};">
      <tr><td style="background:#1a2a3a;padding:24px 28px;">
        <div style="font-size:11px;letter-spacing:2.5px;color:#8fa6bd;
                    text-transform:uppercase;">Personal Workbench</div>
        <div style="margin-top:8px;font-size:23px;font-weight:700;color:#ffffff;
                    letter-spacing:.5px;">今日新闻简报</div>
        <div style="margin-top:6px;font-size:13px;color:#a9bccf;">{html.escape(date_text or subject)}</div>
      </td></tr>
      <tr><td style="padding:10px 28px 26px;">
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
