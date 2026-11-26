"""Explainable interest ranking; reserve discovery space without hard filtering."""
from datetime import datetime, timezone
from itertools import zip_longest
import re


def published_at(item):
    try:
        raw = item.get('published') or ''
        if not isinstance(raw, str) or not raw:
            return None
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    except (ValueError, TypeError):
        return None


def matches(text, keyword):
    keyword = keyword.strip().lower()
    if not keyword:
        return False
    if re.fullmatch(r'[a-z0-9 .+_-]+', keyword):
        return bool(re.search(r'(?<![a-z0-9])' + re.escape(keyword) + r'(?![a-z0-9])', text.lower()))
    return keyword in text.lower()


def rank(items, cfg, now=None):
    now = now or datetime.now(timezone.utc)
    keywords = cfg.get('interest_keywords', [])
    max_age = float(cfg.get('max_age_hours', 168))
    result = []
    for original in items:
        item = dict(original)
        date = published_at(item)
        age = max(0, (now - date).total_seconds() / 3600) if date else None
        # Missing dates remain visible and explicitly labelled by the UI.
        if date and (date - now).total_seconds() > 3600:
            continue
        if max_age > 0 and age is not None and age > max_age:
            continue
        title, summary = item.get('title', ''), item.get('summary', '')
        hits = [k for k in keywords if matches(title + ' ' + summary, k)]
        interest = min(4, sum(2 if matches(title, k) else 1 for k in hits))
        freshness = 0.15 if age is None else 1 / (1 + age / 24)
        item['interest_matches'] = hits
        item['score'] = round(interest + freshness + 0.3 * float(item.get('weight', 0)), 4)
        result.append(item)
    return sorted(result, key=lambda it: (it['score'], it.get('published') or ''), reverse=True)


def select(items, limit, per_source=8, discovery_ratio=0.2):
    """Reserve discovery space and return the selected stories in source rounds."""
    limit = max(0, int(limit))
    counts, selected = {}, []

    def source_id(item):
        return item.get('source_id') or item.get('source_name') or ''

    def take(pool, amount):
        added = 0
        for item in pool:
            if added >= amount or len(selected) >= limit:
                break
            sid = source_id(item)
            if item in selected or (per_source > 0 and counts.get(sid, 0) >= per_source):
                continue
            selected.append(item)
            counts[sid] = counts.get(sid, 0) + 1
            added += 1
    explore = round(limit * max(0, min(1, discovery_ratio)))
    take([it for it in items if not it.get('interest_matches')], explore)
    take(items, limit - len(selected))
    by_source = {}
    for item in sorted(selected, key=lambda it: it['score'], reverse=True):
        by_source.setdefault(source_id(item), []).append(item)
    return [item for group in zip_longest(*by_source.values()) for item in group if item is not None]
