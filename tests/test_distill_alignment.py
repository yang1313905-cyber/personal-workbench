"""Regression coverage for isolated single-item analysis, alignment, dedupe and diversity."""
import json
import re
from collections import Counter

import pytest

from workbench.modules.news_digest import cleaner, distill, prompts, recommend, render


DATE = "2026-11-26"
PASSWORD_HEADLINES = (
    "1Password breach leaked customer names and emails, but not passwords",
    "1Password said hackers broke into its internal systems, but customer passwords are safe",
)
NVIDIA_HEADLINES = (
    "S&P considers Nvidia credit downgrade over governance and 'key man' risks",
    "Jensen Huang broke Nvidia's code of conduct, and his employees may not forget it",
)
FUNDING_HEADLINES = (
    "OpenAI raises $1 billion funding round",
    "Anthropic raises $2 billion funding round",
)
SEQUOIA_HEADLINES = (
    "OpenAI secures Series B backed by Sequoia in San Francisco",
    "Anthropic secures Series B backed by Sequoia in San Francisco",
)
SYNTHESIS = (
    "## 趋势观察\n企业关注信息披露。\n"
    "## 信号与风险\n- **信号**：\n- 跟踪披露措施\n- 核查后续数据\n- 留意合规影响"
)


def _item(title, index, source="TechCrunch"):
    return {
        "title": title,
        "summary": f"{title.split()[0]} 对应的原始摘要。",
        "source_name": source,
        "source_id": source,
        "lang": "zh" if source == "华尔街见闻" else "en",
        "hash": f"hash-{index}",
        "link": f"https://example.test/story/{index}",
    }


def _analysis(item):
    return f"{item['title'].split()[0]} 有新的情况。后续需核对影响。"


def _entries(stories):
    return [
        {"id": item["id"], "title_echo": item["title"], "analysis": _analysis(item)}
        for item in stories
    ]


def _compose(items, count):
    return distill.compose(items, DATE, {"news_digest": {"highlight_count": count}})


def _assert_aligned(parsed, items):
    picked, used = render.resolve(parsed, items)
    assert len(picked) == len(used) == len(parsed["highlights"])
    assert all(entry["analysis"] == _analysis(entry["item"]) for entry in picked)


@pytest.mark.parametrize("failure", ["numbered_text", "numeric_ids", "wrong_title_echo",
                                     "duplicate_id", "truncated"])
def test_isolated_single_item_analysis_recovers_bad_response(monkeypatch, failure):
    items = [
        _item("Dario Amodei discusses Anthropic funding plans", 1),
        _item(PASSWORD_HEADLINES[0], 2),
        _item("Reuters details central bank guidance", 3),
    ]
    attempts = Counter()
    seen_batch_sizes = []

    def llm_chat(_cfg, system, user):
        data = json.loads(user)
        if system == prompts.SYSTEM_PROMPT:
            return json.dumps({"selected_ids": [item["id"] for item in data["candidates"]]})
        if system == prompts.SYNTHESIS_SYSTEM_PROMPT:
            return SYNTHESIS

        assert system == prompts.ANALYSIS_SYSTEM_PROMPT
        stories = data["items"]
        seen_batch_sizes.append(len(stories))
        assert len(stories) == 1  # Isolated single-item call: impossible to leak sibling stories
        story = stories[0]
        attempts[story["title"]] += 1
        entries = _entries(stories)
        if story["title"] == items[0]["title"] and attempts[story["title"]] == 1:
            if failure == "numbered_text":
                return f"[1] {entries[0]['analysis']}"
            if failure == "numeric_ids":
                entries[0]["id"] = "1"
            elif failure == "wrong_title_echo":
                entries[0]["title_echo"] = PASSWORD_HEADLINES[0]
            elif failure == "duplicate_id":
                entries.append({**entries[0], "analysis": "重复条目"})
            elif failure == "truncated":
                return json.dumps({"items": entries})[:-3]
        return json.dumps({"items": entries})

    monkeypatch.setattr(distill, "llm_chat", llm_chat)
    raw, used_llm, error = _compose(items, 3)

    assert used_llm and error is None
    assert set(seen_batch_sizes) == {1}
    assert attempts[items[0]["title"]] == 2
    parsed = render.parse(raw)
    assert [entry["index"] for entry in parsed["highlights"]] == [1, 2, 3]
    _assert_aligned(parsed, items)
    # Bare heading bullet "**信号**：" is stripped cleanly
    assert parsed["signals"] == ["跟踪披露措施", "核查后续数据", "留意合规影响"]


def test_verify_batch_alignment_rejects_swapped_and_cross_item_entries():
    batch = {
        "A1B2": _item("Dario Amodei discusses Anthropic funding plans", 1),
        "C3D4": _item(PASSWORD_HEADLINES[0], 2),
    }
    swapped = [
        {"id": "C3D4", "title_echo": batch["A1B2"]["title"], "analysis": "Anthropic 融资讨论。"},
        {"id": "A1B2", "title_echo": batch["C3D4"]["title"], "analysis": "1Password 泄露客户邮箱。"},
    ]
    assert distill.verify_batch_alignment(swapped, batch) == {}

    cross_item = [
        {"id": "A1B2", "title_echo": batch["A1B2"]["title"], "analysis": "1Password 遭到入侵，客户密码未泄露。"},
        {"id": "C3D4", "title_echo": batch["C3D4"]["title"], "analysis": "1Password 客户姓名和邮箱泄露。"},
    ]
    verified = distill.verify_batch_alignment(cross_item, batch)
    assert list(verified.keys()) == ["C3D4"]


@pytest.mark.parametrize("selection", ["single_source", "two_sources"])
def test_full_digest_with_opaque_ids_diversity_and_exact_indices(monkeypatch, selection):
    sources = ("TechCrunch", "The Verge", "Reuters", "华尔街见闻")
    items = [
        _item(f"Topic{i:02d} update", i, sources[i % 4] if i < 40 else sources[0])
        for i in range(65)
    ]
    submitted_batches = []
    proposed_indices = []
    synthesis_inputs = []

    def llm_chat(_cfg, system, user):
        data = json.loads(user)
        if system == prompts.SYSTEM_PROMPT:
            candidates = data["candidates"]
            ids = [item["id"] for item in candidates]
            assert ids == prompts.candidate_ids(items)
            assert len(set(ids)) == 65
            assert all(re.fullmatch("[A-Z][0-9][A-Z][0-9]", key) for key in ids)
            ranked = {source: [(i, item["id"]) for i, item in enumerate(candidates, 1)
                               if item["source"] == source]
                      for source in sources[:2]}
            best_a = list(reversed(ranked[sources[0]]))
            if selection == "single_source":
                proposed = best_a[:15]
            else:
                proposed = best_a[:8] + ranked[sources[1]][:7]
            proposed_indices.extend(i for i, _ in proposed)
            selected_ids = [key for _, key in proposed]
            payload = json.dumps({"selected_ids": [65, "ABCD", selected_ids[0], *selected_ids]})
            return f"选题结果\n```json\n{payload}\n```\n已完成。"
        if system == prompts.SYNTHESIS_SYSTEM_PROMPT:
            synthesis_inputs.append(data["highlights"])
            return "## 今日重点\n[999] 意外进入合成的编号\n" + SYNTHESIS

        assert system == prompts.ANALYSIS_SYSTEM_PROMPT
        stories = data["items"]
        submitted_batches.append(stories)
        payload = json.dumps({"items": _entries(stories)})
        return f"```json\n{payload}\n```\n分析完毕。"

    monkeypatch.setattr(distill, "llm_chat", llm_chat)
    raw, used_llm, error = _compose(items, 15)

    assert used_llm and error is None
    assert len(submitted_batches) == 15 and all(len(b) == 1 for b in submitted_batches)
    parsed = render.parse(raw)
    actual_indices = [entry["index"] for entry in parsed["highlights"]]
    assert len(actual_indices) == 15
    if selection == "single_source":
        assert actual_indices[:9] == proposed_indices[:9]
    else:
        assert len(set(actual_indices) & set(proposed_indices)) == 14
    assert any(index > 15 for index in actual_indices)
    _assert_aligned(parsed, items)
    counts = Counter(items[index - 1]["source_name"] for index in actual_indices)
    assert len(counts) >= 3 and max(counts.values()) <= 9
    if selection == "single_source":
        assert "华尔街见闻" in counts
    assert parsed["trend"] == "企业关注信息披露。"
    assert parsed["signals"] == ["跟踪披露措施", "核查后续数据", "留意合规影响"]
    assert len(synthesis_inputs) == 1 and len(synthesis_inputs[0]) == 15
    built = render.build(parsed, items, DATE, highlight_count=15, appendix_limit=30)
    assert built["matched"] == 15
    assert len(set(built["shown_indices"])) == 45
    assert built["headline"] == items[actual_indices[0] - 1]["title"]


def test_failed_single_item_is_backfilled_with_source_summary_label(monkeypatch):
    items = [_item(f"Topic{i:02d} update", i) for i in range(4)]

    def llm_chat(_cfg, system, user):
        data = json.loads(user)
        if system == prompts.SYSTEM_PROMPT:
            return json.dumps({"selected_ids": [item["id"] for item in data["candidates"]]})
        if system == prompts.SYNTHESIS_SYSTEM_PROMPT:
            return SYNTHESIS
        story = data["items"][0]
        if story["title"] == items[0]["title"]:
            return "{}"  # Always fails
        return json.dumps({"items": _entries([story])})

    monkeypatch.setattr(distill, "llm_chat", llm_chat)
    raw, used_llm, error = _compose(items, 4)

    assert used_llm and error is None
    built = render.build(render.parse(raw), items, DATE, used_llm=True, highlight_count=4)
    assert built["matched"] == 4
    assert built["markdown"].count("来源摘要") == 1
    assert items[0]["summary"] in built["markdown"]


def test_short_selection_is_filled_without_a_duplicate_event(monkeypatch):
    items = [
        _item(PASSWORD_HEADLINES[0], 1),
        _item(PASSWORD_HEADLINES[1], 2, "The Verge"),
        _item("Reuters details central bank guidance", 3, "Reuters"),
        _item("华尔街见闻 追踪市场资金动向", 4, "华尔街见闻"),
        _item("NASA maps Artemis flight schedule", 5, "The Verge"),
    ]

    def llm_chat(_cfg, system, user):
        data = json.loads(user)
        if system == prompts.SYSTEM_PROMPT:
            first, second = data["candidates"][:2]
            return json.dumps({"selected_ids": [first["id"], second["id"], first["id"], "1"]})
        if system == prompts.SYNTHESIS_SYSTEM_PROMPT:
            return SYNTHESIS
        return json.dumps({"items": _entries(data["items"])})

    monkeypatch.setattr(distill, "llm_chat", llm_chat)
    raw, used_llm, error = _compose(items, 4)

    assert used_llm and error is None
    parsed = render.parse(raw)
    assert [entry["index"] for entry in parsed["highlights"]] == [1, 3, 4, 5]
    _assert_aligned(parsed, items)


def test_all_llm_calls_fail_uses_local_digest(monkeypatch):
    items = [_item("NASA maps Artemis flight schedule", 1), _item(PASSWORD_HEADLINES[0], 2)]
    reason = "provider unavailable"
    systems = []

    def fail(_cfg, system, _user):
        systems.append(system)
        raise RuntimeError(reason)

    monkeypatch.setattr(distill, "llm_chat", fail)
    monkeypatch.setattr("workbench.core.retry.time.sleep", lambda _: None)
    assert _compose(items, 2) == (distill.fallback_digest(items, reason, 2), False, reason)
    assert Counter(systems) == {prompts.SYSTEM_PROMPT: 3, prompts.ANALYSIS_SYSTEM_PROMPT: 4}


def test_cross_source_dedupe_real_november_headlines_and_distinct_funding():
    titles = (*PASSWORD_HEADLINES, *NVIDIA_HEADLINES, *FUNDING_HEADLINES)
    items = [
        {**_item(title, i, f"source-{i}"), "weight": 2 if i == 1 else 1}
        for i, title in enumerate(titles)
    ]
    assert cleaner.overlap_ratio(*(cleaner.tokens(title) for title in PASSWORD_HEADLINES)) < 0.55
    assert cleaner.is_same_event(*PASSWORD_HEADLINES)
    assert not cleaner.is_same_event(*NVIDIA_HEADLINES)
    assert not cleaner.is_same_event(*FUNDING_HEADLINES)
    assert not cleaner.is_same_event(*SEQUOIA_HEADLINES)
    assert [item["title"] for item in cleaner.dedupe(items)] == [
        PASSWORD_HEADLINES[1], *NVIDIA_HEADLINES, *FUNDING_HEADLINES,
    ]


def test_recommend_select_interleaves_sources_by_best_score_and_handles_null_published():
    assert recommend.published_at({"published": None}) is None
    items = [
        {"source_id": source, "score": score, "interest_matches": ["AI"] if source != "C" else []}
        for source, score in [("A", 10), ("A", 9), ("A", 8), ("B", 7), ("B", 6), ("C", 4), ("C", 2)]
    ]
    output = recommend.select(items, limit=5, per_source=2, discovery_ratio=0.2)
    assert [(item["source_id"], item["score"]) for item in output] == [
        ("A", 10), ("B", 7), ("C", 4), ("A", 9), ("B", 6),
    ]
