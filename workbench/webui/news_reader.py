"""Browsable news pool and editable, transparent reading preferences."""
import html
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from workbench.modules.news_digest import recommend
from workbench.modules.news_digest.render import _CATEGORY_ZH, _md_url
from . import config_editor as ce, context as wctx, jobs
from .auth import current_user


def _render_news_card(item: dict, zone: ZoneInfo) -> str:
    title_raw = (item.get('title') or '（无标题）').strip()
    title_esc = html.escape(title_raw)
    link_raw = _md_url(item.get('link', ''))
    if link_raw and link_raw.startswith(('http://', 'https://')):
        title_html = (
            f'<a href="{html.escape(link_raw, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{title_esc}</a>'
        )
    else:
        title_html = title_esc

    source_name = html.escape((item.get('source_name') or '未知来源').strip())
    cat_key = str(item.get('category') or '').strip().lower()
    cat_label = _CATEGORY_ZH.get(cat_key, '')
    cat_html = f'<span class="wb-chip-cat">{html.escape(cat_label)}</span>' if cat_label else ''

    published = recommend.published_at(item)
    timestamp = published.astimezone(zone).strftime('%m-%d %H:%M') if published else '发布时间未知'

    summary = (item.get('summary') or '').strip()
    if len(summary) > 320:
        summary = summary[:320].rstrip() + '…'
    summary_html = f'<p class="wb-news-summary">{html.escape(summary)}</p>' if summary else ''

    matches = item.get('interest_matches') or []
    tags_html = ''
    if matches:
        chips = ''.join(f'<span class="wb-chip-match">#{html.escape(str(m))}</span>' for m in matches[:6])
        tags_html = f'<div class="wb-news-tags">{chips}</div>'

    return (
        '<article class="wb-news-card">'
        f'<div class="wb-news-top">'
        f'<span class="wb-chip-source">{source_name}</span>'
        f'{cat_html}'
        f'<span class="wb-chip-time">{html.escape(timestamp)}</span>'
        f'</div>'
        f'<h4 class="wb-news-title">{title_html}</h4>'
        f'{summary_html}'
        f'{tags_html}'
        '</article>'
    )


def render():
    cfg = wctx.get_cfg()
    nd = cfg.get('news_digest', {})
    st.subheader('为你发现 · 新闻广场')
    if (current_user() or {}).get('role') == 'admin':
        with st.expander('我的兴趣与阅读量', expanded=not bool(nd.get('interest_keywords'))):
            st.caption('兴趣只影响排序，不会屏蔽其他新闻。保存后列表立即重排，下次简报也会采用新偏好。')
            with st.form('reading_preferences'):
                keywords = st.text_area('感兴趣的关键词（逗号或换行分隔）', ', '.join(nd.get('interest_keywords', [])),
                                        placeholder='例如：人工智能, AI, 大模型, 半导体, 创业, 宏观经济')
                focus = st.text_input('给简报编辑的补充要求', nd.get('focus', ''))
                count = st.slider('每日推送重点条数', 3, 15, int(nd.get('highlight_count', 15)))
                appendix = st.slider('每日推送快讯条数', 10, 50, int(nd.get('appendix_limit', 30)))
                discovery = st.slider('探索其他方向的比例', 0, 50, round(float(nd.get('discovery_ratio', .2)) * 100), step=5)
                if st.form_submit_button('保存阅读偏好'):
                    ed = ce.config_editor()
                    values = {'interest_keywords': list(dict.fromkeys(k.strip() for k in re.split(r'[,，\n]', keywords) if k.strip())),
                              'focus': focus.strip(), 'highlight_count': count, 'appendix_limit': appendix,
                              'discovery_ratio': discovery / 100}
                    for key, value in values.items():
                        ed.set('news_digest.' + key, value)
                    ed.save()
                    wctx.invalidate()
                    st.rerun()
        col_btn, col_tip = st.columns([1.2, 3.8])
        with col_btn:
            if st.button('刷新新闻列表', type='primary', disabled=jobs.any_running(), use_container_width=True):
                job_id = jobs.start_digest(no_push=True, refresh_only=True)
                if job_id:
                    st.session_state['job_id'] = job_id
                    st.rerun()
                else:
                    st.info('已有任务正在运行，请稍候。')
        with col_tip:
            st.caption('刷新只抓取新闻，不调用模型、不发送推送。')

    @st.fragment(run_every=2.0)
    def refresh_progress():
        job_id = st.session_state.get('job_id')
        state = jobs.job_state(job_id) if job_id else None
        if not state:
            return
        if state['status'] == 'running':
            st.info(f"正在更新，已用时 {state['elapsed']:.0f} 秒…")
        elif state['status'] == 'done':
            st.success('更新完成')
            if st.button('查看最新内容', key='news_refresh_done'):
                st.session_state.pop('job_id', None)
                st.rerun()
        elif state['status'] == 'error':
            st.error('更新失败，请在运行日志中查看原因。')
    refresh_progress()

    path = Path(nd.get('output_dir', cfg['paths']['output'])) / 'news-latest.json'
    try:
        pool = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        st.info('新闻列表尚未建立，请刷新新闻或生成一次简报。')
        return
    updated = pool.get('updated_at', '')
    zone = ZoneInfo(cfg.get('app', {}).get('timezone', 'Asia/Shanghai'))
    try:
        stamp = datetime.fromisoformat(updated).astimezone(zone).strftime('%m-%d %H:%M')
    except ValueError:
        stamp = updated
    st.caption('最近更新：' + stamp + ' · ' + str(zone))
    try:
        if (datetime.now(timezone.utc) - datetime.fromisoformat(updated)).total_seconds() > 86400:
            st.warning('列表已超过 24 小时未更新，请刷新获取新内容。')
    except ValueError:
        pass
    if pool.get('errors'):
        with st.expander(f"{len(pool['errors'])} 个来源暂时不可用，其余内容正常显示"):
            for error in pool['errors']:
                st.write(error.get('source', '未知来源'))
    items = recommend.rank(pool.get('items', []), nd)
    a, b, c = st.columns(3)
    a.metric('可读新闻', len(items))
    b.metric('匹配兴趣', sum(bool(it['interest_matches']) for it in items))
    c.metric('覆盖来源', len({it.get('source_id') for it in items}))
    with st.container(border=True):
        query = st.text_input('搜索新闻', placeholder='输入标题、公司或关键词')
        col1, col2 = st.columns(2)
        sources = col1.multiselect('来源', sorted({it.get('source_name', '') for it in items}))
        ordering = col2.selectbox('阅读方式', ['推荐排序', '最新发布', '只看兴趣匹配'])
    if query:
        items = [it for it in items if query.lower() in (it.get('title', '') + ' ' + it.get('summary', '')).lower()]
    if sources:
        items = [it for it in items if it.get('source_name') in sources]
    if ordering == '只看兴趣匹配':
        items = [it for it in items if it['interest_matches']]
    elif ordering == '最新发布':
        items.sort(key=lambda it: recommend.published_at(it) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    if not items:
        st.info('暂无匹配新闻。可以放宽搜索条件，或在阅读偏好中补充关键词。')
        return
    pages = max(1, math.ceil(len(items) / 20))
    # Filter changes reset pagination to keep every selected page valid.
    signature = (query, tuple(sources), ordering, updated)
    if st.session_state.get('news_filter') != signature:
        st.session_state['news_page'] = 1
        st.session_state['news_filter'] = signature
    st.session_state['news_page'] = min(st.session_state.get('news_page', 1), pages)
    p_col1, p_col2 = st.columns([1, 3])
    with p_col1:
        page = st.number_input('页码', min_value=1, max_value=pages, step=1, key='news_page')
    with p_col2:
        st.caption(f'共 {len(items)} 条 · 每页 20 条 · 第 {page}/{pages} 页')
    cards_html = ''.join(_render_news_card(item, zone) for item in items[(page - 1) * 20:page * 20])
    st.markdown(cards_html, unsafe_allow_html=True)
