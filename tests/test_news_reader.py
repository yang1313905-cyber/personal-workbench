import json
from datetime import datetime, timezone
from streamlit.testing.v1 import AppTest
from workbench.webui import news_reader
from workbench.webui.config_editor import YamlEditor


def test_reader_filters_and_pagination(monkeypatch, tmp_path):
    cfg = {'paths': {'output': str(tmp_path)}, 'news_digest': {'interest_keywords': ['AI']}}
    items = [dict(title=f'AI model {i}', summary='', source_id='a', source_name='A', published='', link='') for i in range(25)]
    items += [dict(title='Other news', summary='', source_id='b', source_name='B', published='', link='')]
    (tmp_path / 'news-latest.json').write_text(json.dumps({'items': items, 'updated_at': datetime.now(timezone.utc).isoformat()}))
    monkeypatch.setattr(news_reader.wctx, 'get_cfg', lambda: cfg)
    monkeypatch.setattr(news_reader, 'current_user', lambda: {'role': 'viewer'})
    at = AppTest.from_string('from workbench.webui.news_reader import render\nrender()').run()
    assert not at.exception
    assert len(at.button) == 0
    at.number_input[0].set_value(2).run()
    assert not at.exception
    at.text_input[0].set_value('Other news').run()
    assert not at.exception
    assert at.number_input[0].value == 1
    assert any('共 1 条' in c.value for c in at.caption)
    at.selectbox[0].select('只看兴趣匹配').run()
    assert any('暂无匹配新闻' in info.value for info in at.info)


def test_preferences_saved_with_chinese_delimiters(monkeypatch, tmp_path):
    config = tmp_path / 'config.yaml'
    config.write_text('news_digest: {}\n')
    monkeypatch.setattr(news_reader.wctx, 'get_cfg', lambda: {'paths': {'output': str(tmp_path)}, 'news_digest': {}})
    monkeypatch.setattr(news_reader, 'current_user', lambda: {'role': 'admin'})
    monkeypatch.setattr(news_reader.ce, 'config_editor', lambda: YamlEditor(config))
    monkeypatch.setattr(news_reader.wctx, 'invalidate', lambda: None)
    at = AppTest.from_string('from workbench.webui.news_reader import render\nrender()').run()
    at.text_area[0].set_value('AI，创业\nAI')
    next(b for b in at.button if b.label == '保存阅读偏好').click().run()
    assert not at.exception
    assert YamlEditor(config).get('news_digest.interest_keywords') == ['AI', '创业']


def test_news_card_escapes_html_and_rejects_non_http_links():
    from zoneinfo import ZoneInfo
    card = news_reader._render_news_card({
        'title': '<img src=x onerror=alert(1)> AI News',
        'summary': '<script>bad()</script> summary',
        'source_name': '<b>Src</b>',
        'category': 'ai',
        'link': 'javascript:alert(1)',
        'published': '2026-11-26T00:00:00+00:00',
        'interest_matches': ['AI'],
    }, ZoneInfo('Asia/Shanghai'))
    assert '<script>' not in card
    assert '<img ' not in card
    assert 'javascript:' not in card
    assert '&lt;img src=x onerror=alert(1)&gt;' in card
    assert '#AI' in card


def test_dashboard_hides_manual_push_controls_for_viewer(monkeypatch):
    from workbench.webui.pages import dashboard
    monkeypatch.setattr(dashboard, 'current_user', lambda: {'role': 'viewer'})
    at = AppTest.from_string('from workbench.webui.pages.dashboard import render\nrender()').run()
    assert not at.exception
    assert not any('立即生成今日简报' in b.label for b in at.button)


def test_sources_page_is_read_only_for_viewer(monkeypatch):
    from workbench.webui.pages import sources
    monkeypatch.setattr(sources, 'current_user', lambda: {'role': 'viewer'})
    at = AppTest.from_string('from workbench.webui.pages.sources import render\nrender()').run()
    assert not at.exception
    assert len(at.button) == 0
    assert any('只读模式' in info.value for info in at.info)
