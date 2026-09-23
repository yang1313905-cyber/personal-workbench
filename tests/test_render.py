"""简报渲染与邮件 HTML 的单元测试。

覆盖三件事：
1. LLM 输出解析的容错性（多种编号写法、越界编号、完全不合格式）
2. 标题/链接必须来自真实素材（按编号回填），而不是模型自己写的
3. 邮件 HTML 有字体层级、链接可点、且对标题做 HTML 转义
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workbench.channels.markdown_email import first_link, md_to_html, md_to_text, render_email  # noqa: E402
from workbench.modules.news_digest import render  # noqa: E402


def _item(i: int, source: str = "TechCrunch", title: str = "", link: str = "") -> dict:
    return {
        "source_id": f"s{i}", "source_name": source, "category": "tech", "lang": "en",
        "title": title or f"标题{i}", "link": link or f"https://example.com/{i}",
        "published": "2026-09-23T00:12:00+00:00", "summary": f"摘要{i}", "weight": 1.0,
    }


ITEMS = [_item(1, "TechCrunch"), _item(2, "The Verge"), _item(3, "华尔街见闻"),
         _item(4, "BBC World"), _item(5, "Reuters"), _item(6, "TechCrunch")]


# ---------------------------------------------------------------- 解析

def test_parse_standard_format():
    text = "## 今日重点\n[1] 事实与分析一\n[3] 事实与分析二\n\n## 趋势观察\n整体走向。\n\n## 信号与风险\n- 信号甲\n- 信号乙"
    p = render.parse(text)
    assert [h["index"] for h in p["highlights"]] == [1, 3]
    assert p["highlights"][0]["text"] == "事实与分析一"
    assert p["trend"] == "整体走向。"
    assert p["signals"] == ["信号甲", "信号乙"]


def test_parse_tolerates_other_number_styles():
    """模型偶尔会写成 【7】/#7/7. 或带列表符号，都要能认出来。"""
    text = ("## 今日重点\n- 【5】甲\n* #6 乙\n7. 丙\n"
            "（这里还有一行续写）\n## 信号与风险\n1. 信号一\n")
    p = render.parse(text)
    assert [h["index"] for h in p["highlights"]] == [5, 6, 7]
    assert "续写" in p["highlights"][2]["text"]
    assert p["signals"] == ["信号一"]


def test_parse_handles_section_wording_variants():
    text = "## 今日要闻\n[2] 甲\n## 整体趋势\n走向\n## 值得关注的信号/风险\n- 风险"
    p = render.parse(text)
    assert p["highlights"][0]["index"] == 2
    assert p["trend"] == "走向"
    assert p["signals"] == ["风险"]


# ---------------------------------------------------------------- 回填与越界

def test_out_of_range_and_duplicate_indices_are_dropped():
    parsed = {"highlights": [{"index": 99, "text": "越界"}, {"index": 1, "text": "有效"},
                             {"index": 1, "text": "重复"}, {"index": 2, "text": ""}],
              "trend": "", "signals": []}
    picked, used = render.resolve(parsed, ITEMS)
    assert [p["item"]["title"] for p in picked] == ["标题1"]
    assert used == {1}


def test_titles_and_links_come_from_real_items_not_llm():
    """模型只给编号；标题与链接必须来自素材，模型无法伪造。"""
    parsed = {"highlights": [{"index": 2, "text": "分析文字"}], "trend": "", "signals": []}
    built = render.build(parsed, ITEMS, "2026-09-23", used_llm=True, fetched_total=99, kept_total=6)
    md = built["markdown"]
    assert "### 1. [标题2](https://example.com/2)" in md
    assert built["headline"] == "标题2"
    assert built["subject"].startswith("📰 09-23 简报｜标题2")


def test_hallucinated_index_falls_back_to_real_items():
    """模型完全没按格式输出时，简报仍必须是「有标题有链接」的正常样子。"""
    built = render.build(render.parse("这是一段没有编号的自由发挥文字"),
                         ITEMS, "2026-09-23", used_llm=True)
    md = built["markdown"]
    assert built["matched"] == 5
    assert "### 1. [标题1](https://example.com/1)" in md
    assert "未按格式返回" in md


def test_fallback_mode_is_annotated():
    built = render.build(render.parse("## 今日重点\n[1] 兜底内容"), ITEMS, "2026-09-23",
                         used_llm=False, llm_error="401 Unauthorized")
    md = built["markdown"]
    assert "本地兜底模式" in md
    assert "401 Unauthorized" in md


def test_appendix_contains_links_for_unused_items():
    parsed = {"highlights": [{"index": 1, "text": "甲"}], "trend": "", "signals": []}
    md = render.build(parsed, ITEMS, "2026-09-23", used_llm=True)["markdown"]
    assert "## 其他值得一读" in md
    assert "[标题2](https://example.com/2)" in md
    assert "[标题1](https://example.com/1)" not in md.split("## 其他值得一读")[1]


# ---------------------------------------------------------------- 邮件 HTML

def test_email_html_has_hierarchy_and_clickable_titles():
    md = render.build({"highlights": [{"index": 1, "text": "分析"}], "trend": "趋势段",
                       "signals": ["风险一"]}, ITEMS, "2026-09-23",
                      used_llm=True, fetched_total=10, kept_total=6)["markdown"]
    html = md_to_html(md)
    assert 'href="https://example.com/1"' in html          # 标题可点击
    assert "font-size:16px" in html                        # 条目标题最大
    assert "font-size:15px" in html                        # 章节次级
    assert "font-size:14px" in html                        # 正文
    assert "font-size:12px" in html                        # 元信息最小
    assert "border-left:4px solid" in html                 # 章节有视觉标记


def test_email_escapes_html_in_titles():
    items = [_item(1, title='<script>alert("x")</script> & "引号"')]
    md = render.build({"highlights": [{"index": 1, "text": "分析"}], "trend": "", "signals": []},
                      items, "2026-09-23")["markdown"]
    html = md_to_html(md)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_full_email_template_and_preheader():
    md = render.build({"highlights": [{"index": 4, "text": "分析"}], "trend": "", "signals": []},
                      ITEMS, "2026-09-23")["markdown"]
    html = render_email(md, subject="📰 09-23 简报｜标题4")
    assert html.startswith("<!DOCTYPE html>")
    assert "今日新闻简报" in html
    assert "display:none" in html                 # 收件箱预览行
    assert "标题4" in html
    title, url = first_link(md)
    assert (title, url) == ("标题4", "https://example.com/4")


def test_plain_text_keeps_urls():
    md = render.build({"highlights": [{"index": 1, "text": "分析"}], "trend": "",
                       "signals": ["风险"]}, ITEMS, "2026-09-23")["markdown"]
    text = md_to_text(md)
    assert "1. 标题1" in text
    assert "https://example.com/1" in text        # 纯文本版也要能看到链接
    assert "【今日重点】" in text
    assert "· 风险" in text
    assert "<" not in text.replace("─", "")       # 不应残留 HTML 标签
