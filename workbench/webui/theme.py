"""Apple 风格主题：全局 CSS 注入。

设计语言参考 apple.com：
- 背景 #f5f5f7 浅灰、卡片纯白大圆角、柔和阴影
- 主色 Apple Blue #0071e3，按钮胶囊形（border-radius 980px）
- 侧边栏磨砂玻璃（backdrop-filter blur）
- 系统字体栈（SF Pro / PingFang SC）
"""
from __future__ import annotations

APPLE_CSS = """
<style>
/* ================= 全局 ================= */
:root {
  --wb-blue: #0071e3;
  --wb-blue-soft: #e8f1fd;
  --wb-bg: #f5f5f7;
  --wb-card: #ffffff;
  --wb-text: #1d1d1f;
  --wb-gray: #86868b;
  --wb-border: rgba(0, 0, 0, 0.06);
}
html, body, .stApp, [class*="css"] {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
               "Helvetica Neue", "PingFang SC", "Hiragino Sans GB",
               "Microsoft YaHei", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.stApp { background: var(--wb-bg); color: var(--wb-text); }
.block-container { max-width: 1100px; padding-top: 2rem; padding-bottom: 4rem; }
a { color: var(--wb-blue); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ================= 标题 ================= */
h1, h2, h3, h4 {
  color: var(--wb-text);
  letter-spacing: -0.015em;
  font-weight: 700;
}
h1 { font-size: 2.05rem; margin-bottom: 0.4rem; }
h2 { font-size: 1.4rem; padding-top: 0.6rem; }
h3 { font-size: 1.12rem; }

/* ================= 卡片 / 容器 ================= */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--wb-card);
  border-radius: 18px;
  border: 1px solid var(--wb-border);
  box-shadow: 0 2px 14px rgba(0, 0, 0, 0.05);
  padding: 0.4rem 1rem 0.8rem;
  transition: box-shadow 0.25s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.09);
}

/* ================= 指标卡 ================= */
div[data-testid="stMetric"] {
  background: var(--wb-card);
  border-radius: 18px;
  border: 1px solid var(--wb-border);
  box-shadow: 0 2px 14px rgba(0, 0, 0, 0.05);
  padding: 0.9rem 1.1rem;
}
div[data-testid="stMetricValue"] {
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--wb-text);
}
div[data-testid="stMetricLabel"] {
  color: var(--wb-gray);
  font-size: 0.78rem;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

/* ================= 按钮（Apple 胶囊） ================= */
[data-testid="baseButton-primary"], [data-testid="stBaseButton-primary"] {
  background: var(--wb-blue);
  border: none;
  border-radius: 980px;
  font-weight: 600;
  padding: 0.4rem 1.4rem;
  box-shadow: 0 2px 8px rgba(0, 113, 227, 0.25);
  transition: all 0.2s ease;
}
[data-testid="baseButton-primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
  background: #0077ed;
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(0, 113, 227, 0.35);
}
[data-testid="baseButton-secondary"], [data-testid="stBaseButton-secondary"],
[data-testid="baseButton-tertiary"], [data-testid="stBaseButton-tertiary"] {
  border-radius: 980px;
  font-weight: 500;
}

/* ================= 侧边栏（磨砂玻璃） ================= */
[data-testid="stSidebar"] {
  background: rgba(255, 255, 255, 0.78);
  -webkit-backdrop-filter: blur(24px) saturate(1.6);
  backdrop-filter: blur(24px) saturate(1.6);
  border-right: 1px solid rgba(0, 0, 0, 0.05);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: var(--wb-text); }
[data-testid="stSidebarNav"] a, a[data-testid="stSidebarNavLink"] {
  border-radius: 12px;
  transition: background 0.15s ease;
}
[data-testid="stSidebarNav"] a:hover, a[data-testid="stSidebarNavLink"]:hover {
  background: rgba(0, 113, 227, 0.08);
}

/* ================= 输入控件 ================= */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.1);
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
  border-color: var(--wb-blue);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15);
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div { border-radius: 12px; }

/* ================= 折叠面板 / 标签页 ================= */
div[data-testid="stExpander"] {
  border-radius: 16px;
  border: 1px solid var(--wb-border);
  background: var(--wb-card);
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.04);
  overflow: hidden;
}
button[data-baseweb="tab"] {
  border-radius: 10px;
  font-weight: 600;
}
button[data-baseweb="tab"][aria-selected="true"] { color: var(--wb-blue); }

/* ================= 提示条 / 代码块 ================= */
[data-testid="stAlert"] { border-radius: 14px; }
[data-testid="stCodeBlock"] pre {
  border-radius: 14px;
  border: 1px solid var(--wb-border);
}
[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }

/* ================= Hero 横幅 ================= */
.wb-hero {
  background: linear-gradient(135deg, #0071e3 0%, #42a5f5 55%, #5ac8fa 100%);
  border-radius: 24px;
  padding: 1.9rem 2.2rem;
  color: #fff;
  margin-bottom: 1.3rem;
  box-shadow: 0 10px 32px rgba(0, 113, 227, 0.28);
}
.wb-hero-title { font-size: 1.85rem; font-weight: 700; letter-spacing: -0.02em; }
.wb-hero-sub { font-size: 0.95rem; opacity: 0.92; margin-top: 0.35rem; }
.wb-badge {
  display: inline-block;
  background: rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  padding: 0.22rem 0.8rem;
  font-size: 0.75rem;
  margin-top: 0.7rem;
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
}
.wb-pill {
  display: inline-block;
  background: var(--wb-card);
  border: 1px solid var(--wb-border);
  border-radius: 999px;
  padding: 0.18rem 0.9rem;
  font-size: 0.78rem;
  color: var(--wb-gray);
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.06);
}
.wb-step-done { color: #34c759; font-weight: 600; }
.wb-step-warn { color: #ff9500; font-weight: 600; }
.wb-step-muted { color: var(--wb-gray); }

/* ================= 移动端 ================= */
@media (max-width: 768px) {
  .block-container { padding-left: 0.6rem; padding-right: 0.6rem; }
  [data-testid="stSidebar"] { width: 272px !important; }
  .wb-hero { padding: 1.4rem 1.4rem; }
  .wb-hero-title { font-size: 1.5rem; }
}
</style>
"""
