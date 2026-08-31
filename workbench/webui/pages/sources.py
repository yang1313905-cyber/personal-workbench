"""新闻源管理：添加 / 测试 / 编辑新闻源的专门界面。

- 「测试并预览」直接抓取一次，验证地址可用、条目可读，再保存
- 权重体系：weight（越大越优先）+ 每源配额 max_per_source（保证多源覆盖）
- 添加一个源只需准备一个 RSS/Atom 地址（详见页面内「需要准备什么」）
"""
from __future__ import annotations

import streamlit as st

from workbench.modules.news_digest import fetcher

from .. import config_editor as ce
from .. import context as wctx
from .. import data as wdata

KINDS = ["rss", "wallstreetcn"]
LANGS = ["zh", "en"]
CATEGORIES = ["tech", "business", "politics", "social", "other"]

GUIDE_MD = """
### 🔧 添加一个新闻源需要准备什么？

**核心：一个 RSS/Atom 订阅地址**（90% 的网站适用）。常见规律：
- 直接试：`https://网站.com/feed`、`/rss`、`/rss.xml`、`/atom.xml`、`/feed.xml`
- 不确定有没有 → 用 **Google News 生成检索订阅**（无需知道该站是否有 RSS）：
  ```
  https://news.google.com/rss/search?q=site:网站域名&hl=zh-CN&gl=CN&ceid=CN:zh-Hans
  ```
- 或把网址发我，我帮你找/生成

**其他字段（都有默认值，可不填）：**

| 字段 | 说明 | 默认 |
|---|---|---|
| id | 唯一标识：小写字母/数字/连字符 | 自动生成 |
| 名称 | 简报里显示的名称 | 同 id |
| 类型 | `rss`（标准订阅）；`wallstreetcn`（华尔街见闻专用 JSON） | rss |
| 语言 | zh / en | zh |
| 分类 | tech / business / politics / social / other | tech |
| 权重 | 0-1，**越大越优先**（去重时高权重源胜出、排序更靠前） | 0.8 |

**没有 RSS 的网站/账号**：用上面的 Google News 检索 RSS 即可（零代码）；
特殊 API 源（如华尔街见闻）需要我写适配器，把接口地址发我即可。
"""


def _test_source(url: str, kind: str, http_cfg: dict):
    """真实抓取测试。返回 (ok, message, items)。"""
    url = (url or "").strip()
    if not url:
        return False, "URL 为空", []
    src = {"id": "test", "name": "test", "kind": kind, "url": url, "limit": 5}
    try:
        items = fetcher.fetch_source(src, http_cfg)
        return True, f"抓取成功：{len(items)} 条", items
    except Exception as e:  # noqa: BLE001
        return False, str(e), []


def _save(editor: ce.YamlEditor, msg: str) -> None:
    try:
        editor.save()
        wctx.invalidate()
        st.success(f"✅ {msg}（已备份 .bak，立即生效）")
        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.error(f"❌ 保存失败：{e}")


def _source_form() -> None:
    st.subheader("➕ 添加数据源")
    http_cfg = wctx.get_cfg().get("http", {})
    with st.form("add_source"):
        col1, col2 = st.columns(2)
        n_id = col1.text_input("id（唯一标识，可留空自动生成）", placeholder="my-news")
        n_name = col2.text_input("名称（显示名）", placeholder="我的新闻源")
        n_url = st.text_input("RSS / Atom 地址（必填）", placeholder="https://example.com/feed")
        col3, col4, col5 = st.columns(3)
        n_kind = col3.selectbox("类型", KINDS, index=0)
        n_lang = col4.selectbox("语言", LANGS, index=0)
        n_cat = col5.selectbox("分类", CATEGORIES, index=0)
        col6, col7 = st.columns(2)
        n_weight = col6.slider("权重（越大越优先）", 0.0, 1.0, 0.8, 0.05)
        n_enabled = col7.toggle("添加后立即启用", True)

        col_t, col_s = st.columns(2)
        clicked_test = col_t.form_submit_button("🔍 测试并预览")
        clicked_save = col_s.form_submit_button("💾 保存数据源", type="primary")

    if clicked_test:
        with st.spinner("正在抓取测试…"):
            ok, msg, items = _test_source(n_url, n_kind, http_cfg)
        if ok:
            st.success(f"✅ {msg}，预览前 3 条：")
            for it in items[:3]:
                st.markdown(f"- **{it['title']}**\n  <sub>{it['link']}</sub>", unsafe_allow_html=True)
        else:
            st.error(f"❌ 抓取失败：{msg}")

    if clicked_save:
        with st.spinner("正在验证地址…"):
            ok, msg, items = _test_source(n_url, n_kind, http_cfg)
        if not ok:
            st.error(f"❌ 未保存：地址不可用 — {msg}\n\n请用「🔍 测试并预览」排查，或更换地址。")
        elif not n_url.strip():
            st.error("❌ 未保存：URL 必填")
        else:
            ed = ce.feeds_editor()
            src_id = (n_id.strip() or f"src{len(ed.sources()) + 1}")
            ed.append_source({
                "id": src_id,
                "name": n_name.strip() or src_id,
                "kind": n_kind,
                "url": n_url.strip(),
                "lang": n_lang,
                "category": n_cat,
                "weight": float(n_weight),
                "enabled": bool(n_enabled),
            })
            _save(ed, f"已添加「{n_name.strip() or src_id}」（验证抓取 {len(items)} 条）")


def _existing_sources() -> None:
    st.subheader("📋 现有数据源")
    ed = ce.feeds_editor()
    sources = ed.sources()
    if not sources:
        st.info("还没有数据源，先在上方添加一个。")
        return
    http_cfg = wctx.get_cfg().get("http", {})
    failed = {e.get("source") for e in (wdata.read_status().get("fetch_errors") or [])}

    for i, src in enumerate(list(sources)):
        enabled = bool(src.get("enabled", True))
        sid = src.get("id", "?")
        status_icon = "⛔ 停用" if not enabled else ("❌ 上次失败" if sid in failed else "✅ 正常")
        with st.expander(f"{status_icon}　{src.get('name', sid)}　·　{src.get('lang')} · 权重 {src.get('weight')}",
                         expanded=False):
            f_id = st.text_input("id", str(src.get("id", "")), key=f"src_id_{i}")
            f_name = st.text_input("名称", str(src.get("name", "")), key=f"src_name_{i}")
            f_url = st.text_input("URL", str(src.get("url", "")), key=f"src_url_{i}")
            f_kind = st.selectbox("类型", KINDS,
                                  index=KINDS.index(src.get("kind")) if src.get("kind") in KINDS else 0,
                                  key=f"src_kind_{i}")
            f_lang = st.selectbox("语言", LANGS,
                                  index=LANGS.index(src.get("lang")) if src.get("lang") in LANGS else 0,
                                  key=f"src_lang_{i}")
            f_cat = st.selectbox("分类", CATEGORIES,
                                 index=CATEGORIES.index(src.get("category")) if src.get("category") in CATEGORIES else 0,
                                 key=f"src_cat_{i}")
            f_weight = st.slider("权重（越大越优先）", 0.0, 1.0,
                                 float(src.get("weight", 0.8)), 0.05, key=f"src_w_{i}")
            f_enabled = st.toggle("启用", enabled, key=f"src_en_{i}")

            col_a, col_b, col_c, col_d = st.columns(4)
            if col_a.button("🔍 测试", key=f"src_test_{i}", use_container_width=True):
                with st.spinner("抓取中…"):
                    ok, msg, items = _test_source(f_url, f_kind, http_cfg)
                if ok:
                    st.success(f"✅ {msg}")
                    for it in items[:2]:
                        st.markdown(f"- {it['title']}")
                else:
                    st.error(msg)
            if col_b.button("💾 保存", key=f"src_save_{i}", use_container_width=True):
                for k, v in {"id": f_id.strip() or sid, "name": f_name.strip() or f_id.strip() or sid,
                             "url": f_url.strip(), "kind": f_kind, "lang": f_lang,
                             "category": f_cat, "weight": float(f_weight),
                             "enabled": bool(f_enabled)}.items():
                    sources[i][k] = v
                _save(ed, f"「{sources[i].get('name')}」已保存")
            if col_c.button("⏹ 启用/停用", key=f"src_toggle_{i}", use_container_width=True):
                sources[i]["enabled"] = not enabled
                _save(ed, "已切换启用状态")
            if col_d.button("🗑️ 删除", key=f"src_del_{i}", use_container_width=True):
                ed.remove_source(i)
                _save(ed, "数据源已删除")


def render() -> None:
    st.title("📰 新闻源管理")
    st.caption("添加 / 测试 / 编辑新闻源。每个源保存前都会真实抓取验证一次，"
               "不会保存无效地址。多源配额制（config → `max_per_source`）保证每份简报覆盖多个网站。")

    with st.expander("📖 添加源需要准备什么？（点开查看）", expanded=False):
        st.markdown(GUIDE_MD)

    _source_form()
    st.divider()
    _existing_sources()
