"""Editorial 风格主题：全局 CSS 注入。

视觉语言：
- 晨报编辑感 + Apple 极简层次：暖石浅底 #f4f6f9、纯白卡片、柔和边框、深石板与暖金点缀
- 主色深海蓝 #0f4c81 / Apple Blue #0071e3，按钮胶囊形
- 为新闻广场、每日简报卡片、趋势观察与快讯索引提供统一的高可读排版样式
"""
from __future__ import annotations

APPLE_CSS = """
<style>
/* ================= 全局 ================= */
:root {
  --wb-blue: #0f4c81;
  --wb-blue-bright: #0071e3;
  --wb-blue-soft: #eaf2fb;
  --wb-gold: #d49b3a;
  --wb-gold-soft: #fcf9f2;
  --wb-bg: #f4f6f9;
  --wb-card: #ffffff;
  --wb-card-subtle: #fbfcfe;
  --wb-text: #0f172a;
  --wb-body: #334155;
  --wb-gray: #64748b;
  --wb-muted: #94a3b8;
  --wb-border: rgba(15, 23, 42, 0.08);
}
html, body, .stApp, [class*="css"] {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
               "Helvetica Neue", "PingFang SC", "Hiragino Sans GB",
               "Microsoft YaHei", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.stApp { background: var(--wb-bg); color: var(--wb-text); }
.block-container { max-width: 1080px; padding-top: 1.8rem; padding-bottom: 4rem; }
a { color: var(--wb-blue); text-decoration: none; }
a:hover { color: var(--wb-blue-bright); text-decoration: underline; }

/* ================= 标题 ================= */
h1, h2, h3, h4 {
  color: var(--wb-text);
  letter-spacing: -0.015em;
  font-weight: 700;
}
h1 { font-size: 2rem; margin-bottom: 0.4rem; }
h2 { font-size: 1.35rem; padding-top: 0.5rem; }
h3 { font-size: 1.1rem; }

/* ================= 卡片 / 容器 ================= */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--wb-card);
  border-radius: 16px;
  border: 1px solid var(--wb-border);
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.04);
  padding: 0.5rem 1.05rem 0.85rem;
  transition: box-shadow 0.22s ease, transform 0.22s ease, border-color 0.22s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  border-color: rgba(15, 76, 129, 0.16);
}

/* ================= 指标卡 ================= */
div[data-testid="stMetric"] {
  background: var(--wb-card);
  border-radius: 16px;
  border: 1px solid var(--wb-border);
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
  padding: 0.9rem 1.15rem;
}
div[data-testid="stMetricValue"] {
  font-size: 1.7rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--wb-text);
}
div[data-testid="stMetricLabel"] {
  color: var(--wb-gray);
  font-size: 0.78rem;
  letter-spacing: 0.03em;
}

/* ================= 按钮（胶囊） ================= */
[data-testid="baseButton-primary"], [data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, #0f4c81 0%, #1d64a6 100%);
  border: none;
  border-radius: 980px;
  font-weight: 600;
  padding: 0.42rem 1.4rem;
  box-shadow: 0 3px 10px rgba(15, 76, 129, 0.24);
  transition: all 0.2s ease;
}
[data-testid="baseButton-primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
  background: linear-gradient(135deg, #0c3d68 0%, #165590 100%);
  transform: translateY(-1px);
  box-shadow: 0 5px 16px rgba(15, 76, 129, 0.34);
}
[data-testid="baseButton-secondary"], [data-testid="stBaseButton-secondary"],
[data-testid="baseButton-tertiary"], [data-testid="stBaseButton-tertiary"] {
  border-radius: 980px;
  font-weight: 500;
}

/* ================= 侧边栏（磨砂玻璃） ================= */
[data-testid="stSidebar"] {
  background: rgba(255, 255, 255, 0.84);
  -webkit-backdrop-filter: blur(24px) saturate(1.5);
  backdrop-filter: blur(24px) saturate(1.5);
  border-right: 1px solid rgba(15, 23, 42, 0.06);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: var(--wb-text); }
[data-testid="stSidebarNav"] a, a[data-testid="stSidebarNavLink"] {
  border-radius: 11px;
  transition: background 0.15s ease;
}
[data-testid="stSidebarNav"] a:hover, a[data-testid="stSidebarNavLink"]:hover {
  background: rgba(15, 76, 129, 0.08);
}

/* ================= 输入控件 ================= */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 42, 0.11);
  background: #ffffff;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
  border-color: var(--wb-blue);
  box-shadow: 0 0 0 3px rgba(15, 76, 129, 0.14);
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div { border-radius: 12px; background: #ffffff; }

/* ================= 折叠面板 / 标签页 ================= */
div[data-testid="stExpander"] {
  border-radius: 16px;
  border: 1px solid var(--wb-border);
  background: var(--wb-card);
  box-shadow: 0 1px 8px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}
button[data-baseweb="tab"] {
  border-radius: 10px 10px 0 0;
  font-weight: 600;
  font-size: 0.96rem;
  padding: 0.5rem 1rem;
}
button[data-baseweb="tab"][aria-selected="true"] { color: var(--wb-blue); }

/* ================= 提示条 / 代码块 ================= */
[data-testid="stAlert"] { border-radius: 14px; }
[data-testid="stCodeBlock"] pre {
  border-radius: 14px;
  border: 1px solid var(--wb-border);
}
[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }

/* ================= Editorial Hero 报头 ================= */
.wb-hero {
  position: relative;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 58%, #1b3a5c 100%);
  border-radius: 20px;
  padding: 1.85rem 2.2rem 1.7rem;
  color: #ffffff;
  margin-bottom: 1.4rem;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.16);
  overflow: hidden;
  border-top: 4px solid var(--wb-gold);
}
.wb-hero-eyebrow {
  font-size: 0.72rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #94a3b8;
  font-weight: 600;
  margin-bottom: 0.45rem;
}
.wb-hero-title {
  font-size: 1.85rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.25;
}
.wb-hero-sub {
  font-size: 0.94rem;
  color: #cbd5e1;
  margin-top: 0.4rem;
}
.wb-hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.95rem;
}
.wb-badge {
  display: inline-flex;
  align-items: center;
  background: rgba(212, 155, 58, 0.22);
  color: #f6d38b;
  border-radius: 999px;
  padding: 0.24rem 0.85rem;
  font-size: 0.76rem;
  font-weight: 600;
}
.wb-badge-soft {
  display: inline-flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.12);
  color: #e2e8f0;
  border-radius: 999px;
  padding: 0.24rem 0.85rem;
  font-size: 0.76rem;
}
.wb-pill {
  display: inline-block;
  background: var(--wb-card);
  border: 1px solid var(--wb-border);
  border-radius: 999px;
  padding: 0.18rem 0.9rem;
  font-size: 0.78rem;
  color: var(--wb-gray);
  box-shadow: 0 1px 6px rgba(15, 23, 42, 0.05);
}

/* ================= 新闻广场卡片 ================= */
.wb-news-card {
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  padding: 1.15rem 1.35rem 1.2rem;
  margin-bottom: 0.85rem;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.035);
  transition: transform 0.18s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}
.wb-news-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  border-color: rgba(15, 76, 129, 0.2);
}
.wb-news-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
  margin-bottom: 0.55rem;
}
.wb-chip-source {
  display: inline-block;
  background: #eaf2fb;
  color: #124a84;
  border-radius: 999px;
  padding: 0.16rem 0.65rem;
  font-size: 0.76rem;
  font-weight: 600;
}
.wb-chip-cat {
  display: inline-block;
  background: #f1f5f9;
  color: #475569;
  border-radius: 999px;
  padding: 0.16rem 0.6rem;
  font-size: 0.74rem;
  font-weight: 500;
}
.wb-chip-time {
  font-size: 0.78rem;
  color: #8391a5;
}
.wb-news-title {
  margin: 0 0 0.5rem;
  font-size: 1.08rem;
  font-weight: 700;
  line-height: 1.45;
  color: #0f2b4c;
}
.wb-news-title a {
  color: #0f2b4c;
  text-decoration: none;
}
.wb-news-title a:hover {
  color: #0071e3;
  text-decoration: none;
}
.wb-news-summary {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.72;
  color: #334155;
}
.wb-news-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.7rem;
}
.wb-chip-match {
  display: inline-block;
  background: #fef6e4;
  color: #9a5b13;
  border: 1px solid #f4dfb4;
  border-radius: 999px;
  padding: 0.12rem 0.58rem;
  font-size: 0.74rem;
  font-weight: 600;
}

/* ================= 简报阅读视图 ================= */
.wb-digest-shell {
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  padding: 1.3rem 1.65rem 1.7rem;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.045);
  margin-bottom: 1rem;
}

.wb-step-done { color: #16a34a; font-weight: 600; }
.wb-step-warn { color: #d97706; font-weight: 600; }
.wb-step-muted { color: var(--wb-gray); }

/* ================= 移动端 ================= */
@media (max-width: 768px) {
  .block-container { padding-left: 0.65rem; padding-right: 0.65rem; }
  [data-testid="stSidebar"] { width: 272px !important; }
  .wb-hero { padding: 1.35rem 1.3rem; border-radius: 16px; }
  .wb-hero-title { font-size: 1.48rem; }
  .wb-news-card { padding: 0.95rem 1rem; }
  .wb-digest-shell { padding: 1rem 1rem 1.25rem; }
}
</style>
"""
