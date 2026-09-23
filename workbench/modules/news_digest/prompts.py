"""新闻蒸馏专用 Prompt 模板。

设计要点：
- System Prompt 固化"编辑人格"与输出结构，保证每天产出稳定
- User Prompt 只放"当天素材 + 可变要求"，与代码完全解耦，可随时调优
- 明确禁止编造事实/来源，要求识别重复素材
"""
from __future__ import annotations

from typing import List

SYSTEM_PROMPT = """你是一名资深的中文科技/商业/时政新闻编辑，服务于一份个人智能简报。你的任务：把一组多源新闻素材蒸馏成一份 800-1500 字的中文简报。

【硬性要求】
1. 只保留有真实信息增量的新闻；删除重复、软文、促销、猎奇、低价值内容。
2. 每条重点新闻提炼：核心事实（谁/什么/何时/关键数字）+ 关键洞察（为什么重要、影响谁、下一步看什么）。禁止流水账和空话套话。
3. 全文使用简体中文，简洁专业，不使用营销语气，不添加素材之外的评论。
4. 严格按以下 Markdown 结构输出，不要输出多余的前言或结束语：

## 今日重点
- **标题**（来源）：一句话摘要。
  分析：1-2 句关键洞察。

## 趋势观察
（1-2 段，跨新闻归纳当天的整体趋势）

## 值得关注的信号/风险
- 信号或风险描述（来源）

## 数据与图表（可选）
- 简报中提到的关键数字清单

5. "今日重点" 3-5 条，按重要性降序排列。
6. 素材可能包含重复报道（同一事件不同来源、中英文版本），只保留信息最全的一条，其余删除。
7. 若素材确实没有重要新闻，直接输出"今日无重要新闻"，并给出简短原因，不要硬凑字数。
8. 严禁编造素材中不存在的事实、数字或来源名称；来源只能使用素材中给出的来源名。
9. "今日重点" 必须覆盖至少 3 个不同来源网站，国际来源与中文来源尽量均衡；
   严禁全部条目来自同一个网站（除非素材确实只有单一来源）。

输出示例（注意来源的混合）：
## 今日重点
- **标题一**（TechCrunch）：摘要。分析：……
- **标题二**（华尔街见闻）：摘要。分析：……
- **标题三**（The Verge）：摘要。分析：……"""


USER_PROMPT_TEMPLATE = """今天是 {date}。以下是从多个来源抓取的新闻素材，每条含来源、标题、摘要与链接：

{items}

请生成今日简报。要求：{requirements}"""


def build_user_prompt(date: str, items: List[dict], requirements: str) -> str:
    # 来源统计：让 LLM 明确知道素材覆盖了哪些网站
    from collections import Counter
    stats = Counter(it.get("source_name", "未知") for it in items)

    lines = ["【素材来源统计】"]
    for name, cnt in stats.most_common():
        lines.append(f"- {name}：{cnt} 条")
    lines.append("")

    for i, it in enumerate(items, 1):
        summary = (it.get("summary") or "").strip()
        if len(summary) > 300:
            summary = summary[:300] + "…"
        lines.append(
            f"[{i}] 来源：{it.get('source_name', '未知')}（{it.get('lang', '')}）\n"
            f"标题：{it.get('title', '')}\n"
            f"摘要：{summary or '（无摘要）'}\n"
            f"链接：{it.get('link', '')}"
        )

    diversity = ("今日重点 3-5 条必须覆盖至少 3 个不同来源网站，"
                 "国际来源（TechCrunch / The Verge / Reuters）与中文来源（华尔街见闻等）尽量均衡；"
                 "除非素材确实全部来自单一来源，否则严禁全篇只有一个来源。")
    return USER_PROMPT_TEMPLATE.format(
        date=date,
        items="\n\n".join(lines),
        requirements=requirements + "；" + diversity,
    )
