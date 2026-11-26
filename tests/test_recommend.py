from datetime import datetime, timezone
from workbench.modules.news_digest.recommend import rank, select

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def story(title, date='2026-10-29T10:00:00+00:00', source='a', weight=1):
    return dict(title=title, summary='', published=date, source_id=source, weight=weight)


def test_interest_beats_source_weight_and_english_words_are_bounded():
    ranked = rank([story('Daily mail'), story('New AI model', weight=.5)], {'interest_keywords': ['AI']}, NOW)
    assert ranked[0]['title'] == 'New AI model'
    assert ranked[1]['interest_matches'] == []


def test_stale_future_missing_and_timezone_dates():
    ranked = rank([story('old', '2026-10-01T00:00:00Z'), story('unknown', ''),
                   story('future', '2027-01-01T00:00:00Z'),
                   story('recent', '2026-10-29T19:00:00+08:00')], {}, NOW)
    assert [x['title'] for x in ranked] == ['recent', 'unknown']


def test_discovery_and_source_limits():
    items = rank([story('AI ' + str(i), source=str(i % 3)) for i in range(10)] +
                 [story('science discovery', source='science')], {'interest_keywords': ['AI']}, NOW)
    chosen = select(items, 5, 2, .2)
    assert len(chosen) == 5
    assert any(x['title'] == 'science discovery' for x in chosen)
    assert all(sum(x['source_id'] == source for x in chosen) <= 2 for source in ['0', '1', '2'])
    assert select(items, 0) == []


def test_empty_interests_still_provide_news():
    assert len(rank([story('news')], {}, NOW)) == 1
