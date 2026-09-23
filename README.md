# 个人智能工作台（Personal Workbench）

模块化、低维护的个人 Agent 工作台。**第一个模块：每日新闻简报**
（多源抓取 → 去重去噪 → LLM 蒸馏 → 定时推送手机），后续功能按标准接口即插即用。

- 技术栈：Python 3.9+，轻量依赖（requests / feedparser / PyYAML / APScheduler / python-dotenv），全部免费开源
- 双入口：**CLI + 定时任务**（`workbench digest`）与 **Streamlit Web 管理界面**（`streamlit run app.py`）
- 推送：Telegram / 企业微信 / 飞书 / 钉钉 / 邮件 / Server酱 / PushPlus / WxPusher / Bark
- LLM：任意 OpenAI 兼容接口（DeepSeek / OpenAI / Moonshot / 本地 Ollama…）
- 部署：本地 cron / systemd / Docker / GitHub Actions / Streamlit Cloud / Railway / Render / Fly.io

---

## 目录

1. [架构总览](#1-架构总览)
2. [快速开始（5 分钟跑通）](#2-快速开始)
3. [Web 管理界面](#3-web-管理界面)
4. [推送渠道配置](#4-推送渠道配置)
5. [调度方式](#5-调度方式)
6. [部署方案](#6-部署方案)
7. [扩展指南：添加新模块](#7-扩展指南添加新模块)
8. [可观测性](#8-可观测性)
9. [注意事项与优化建议](#9-注意事项与优化建议)

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│  调度层    cron / systemd timer / worker 进程 / 手动 CLI   │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  核心层 core（与业务无关）                                 │
│  config(配置) logging(日志) retry(重试)                   │
│  state(SQLite去重/记录) status(运行状态)                  │
│  registry(模块注册表) scheduler(定时器)                   │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  模块层 modules（业务，互不依赖，即插即用）                 │
│  news_digest(新闻简报)   ← 当前唯一模块                    │
│  todo_list(待办)  kb_summary(知识库)  mail(邮件) ... ← 预留 │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  渠道层 channels（所有模块共用）                           │
│  telegram wecom feishu dingtalk smtp webhook(通用)       │
└─────────────────────────────────────────────────────────┘
```

**关键设计**：模块层通过 `register(Module(...))` 自我注册，核心零改动；
渠道层对模块透明，模块只调 `broadcast(title, content)`。

## 2. 快速开始

```bash
cd personal-workbench

# 1. 安装依赖（建议先建虚拟环境）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置密钥
cp .env.example .env          # 填入 LLM_API_KEY 和至少一个推送渠道
# （项目自动加载 .env；也可以直接 export）

# 3. 发送一条测试消息，验证渠道
python -m workbench.cli test-channel telegram

# 4. 立即生成并推送今日简报
python -m workbench.cli digest

# 5. 只生成不推送（先看效果）
python -m workbench.cli digest --no-push
cat data/output/digest-$(date +%F).md
```

> 安装为全局命令（可选）：`pip install -e .`，之后直接 `workbench digest`。

**常见问题**：
- `LLM_API_KEY` 未配置 → 自动降级为「本地兜底简报」（标题+摘要+链接），推送不中断。
- 某些国外源超时 → 在 `config.yaml` 的 `http.proxies` 配代理，或改用镜像/RSSHub。

## 3. Web 管理界面（Streamlit）

可视化网站：首页仪表盘 / 简报详情 / 历史搜索 / 手动生成 / 配置中心 / 运行日志，
手机浏览器直接访问，核心逻辑与 CLI 完全共用。

```bash
# 依赖已含 streamlit 与 ruamel.yaml（requirements.txt）
streamlit run app.py          # 本地打开 http://localhost:8501
```

**功能清单**：

| 页面 | 能力 |
|---|---|
| 📊 首页仪表盘 | Apple 风格 Hero + 今日简报预览、最近 5 期列表、一键生成（后台异步+实时进度）、状态指标 |
| 🧠 蒸馏中心 | 新闻蒸馏母平台：流水线五步状态、数据源总览（含失败标记）、LLM 引擎与连通性测试 |
| 📡 推送中心 | 连接最终推送软件：渠道状态卡（就绪/缺配置/停用）、一键测试发送、启用开关、最近推送记录、凭据获取指南 |
| 📰 新闻源管理 | **专用接口**：添加新闻源（真实抓取「测试并预览」验证后才可保存）、编辑/删除/启用、权重调整、添加源所需材料说明 |
| 📄 简报详情 | 完整 Markdown 渲染、下载、推送记录；URL 带 `?date=` 可手机分享 |
| 🗂️ 历史简报 | 全文搜索 + 分页浏览 |
| ⚙️ 配置中心 | 新闻源增删改/启用、LLM 参数、推送时间、渠道开关、.env 密钥管理、有效配置查看 |
| 📜 运行日志 | 按级别过滤、自动刷新 |
| ℹ️ 关于 | 已注册模块、运行路径、云端部署提示 |

**界面与交互**：Apple 风格主题（`workbench/webui/theme.py`）——浅灰背景、白色大圆角卡片、
Apple Blue 胶囊按钮、磨砂玻璃侧边栏；侧边栏可一键**隐藏/重现**（全宽阅读模式）。

**多源权重体系**（`news_digest` 配置段）：
- `max_per_source: 8` —— **每源配额制**：每个来源最多入选 N 条候选，保证简报覆盖多个网站，单一来源无法霸榜
- `weight` —— 每个来源的优先级（0-1），去重时高权重源胜出、排序更靠前
- **程序化多源强制**：LLM 生成的简报若全部来自单一来源，自动带纠正指令重写一次（30 个测试覆盖）

**与 CLI / 定时任务的关系**：
- 同一套 `workbench` 核心：Web 的「立即生成」就是 `registry.run_module("news_digest")`，
  与 `workbench digest` 行为一致；
- 新增**跨进程防重锁**（`workbench/core/lock.py`）：Web / CLI / 定时任务同时触发时
  只允许一个真正执行，其余提示"已有任务在运行"，避免重复抓取与重复推送；
- 配置中心改的是同一份 `config.yaml` / `feeds.yaml` / `.env`，cron 与 CLI 立即生效；
- 配置中心用 ruamel.yaml **保注释**原地修改，写前校验 + 自动备份 `.bak`。

## 4. 推送渠道配置

| 渠道 | 免费额度 | 稳定性 | 获取方式 |
|---|---|---|---|
| **Telegram** | 无限制 | ★★★★★ | 找 @BotFather 建 Bot，@userinfobot 查 chat_id |
| **企业微信机器人** | 无限制 | ★★★★★ | 群 → 添加群机器人 → 复制 Webhook |
| **邮件 SMTP** | 邮箱自带 | ★★★★ | QQ/163/Gmail 开启 SMTP 拿授权码 |
| **Server酱3**（个人微信） | 5 条/天 | ★★★★ | sct.ftqq.com 微信扫码登录拿 SendKey |
| **PushPlus**（个人微信） | 200 条/天 | ★★★★ | pushplus.plus 登录拿 token |
| **WxPusher**（个人微信） | 无限制(限速) | ★★★ | 需关注其公众号，appToken+uid |
| **飞书/钉钉机器人** | 无限制 | ★★★★ | 群内添加自定义机器人 |
| **Bark**（iOS） | 无限制 | ★★★★ | App Store 装 Bark 拿 key |

**推荐组合（2-3 个）**：
1. **Telegram + 邮件**：最稳、零限制、互为备份。适合日常主力。
2. **企业微信机器人**：国内网络最快，无需梯子；缺点是被限制在群内。
3. **PushPlus 或 Server酱**：唯一能把消息推到「个人微信」的方式（第三方中转），
   有每日条数上限，作为 Telegram/邮件之外的补充。

配置示例（`config.yaml` channels 段 + `.env`），密钥一律 `${ENV}` 注入：

```yaml
channels:
  telegram:
    enabled: true
    bot_token: ${TELEGRAM_BOT_TOKEN}
    chat_id: ${TELEGRAM_CHAT_ID}
  wecom:
    enabled: true
    webhook: ${WECOM_WEBHOOK}
```

## 5. 调度方式

**方式 A：cron（推荐，最稳定）**

```bash
bash scripts/install_cron.sh        # 自动写入每天 08:00 的任务
crontab -l                          # 查看
```

**方式 B：内置 worker 进程（无 cron 环境）**

```bash
python -m workbench.cli worker      # 常驻；nohup / systemd / Docker 托管
```

**方式 C：GitHub Actions（免费云调度，电脑不用开机）** —— 见 [部署方案](#6-部署方案)。

三种方式共用同一份 `config.yaml`，可随时切换。

## 6. 部署方案

### 5.1 本机（Mac/Linux）

```bash
crontab -e
# 加入一行（每天 08:00）：
# 0 8 * * * cd /path/to/personal-workbench && .venv/bin/python -m workbench.cli digest >> data/logs/cron.log 2>&1
```

### 5.2 轻量云服务器（推荐长期方案）

```bash
# systemd 服务：每天 08:00 执行
sudo tee /etc/systemd/system/workbench-digest.service > /dev/null <<'EOF'
[Unit]
Description=Personal Workbench Daily Digest
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/personal-workbench
ExecStart=/opt/personal-workbench/.venv/bin/python -m workbench.cli digest
EOF

sudo tee /etc/systemd/system/workbench-digest.timer > /dev/null <<'EOF'
[Unit]
Description=Run digest at 08:00

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl enable --now workbench-digest.timer
```

### 5.3 GitHub Actions（零成本云调度）

```yaml
# .github/workflows/digest.yml
name: daily-digest
on:
  schedule:
    - cron: "0 8 * * *"        # UTC 08:00 = 北京时间 16:00，按需调整
  workflow_dispatch:           # 支持手动触发

jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: python -m workbench.cli digest
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
```

> Actions 出口 IP 抓取部分站点可能被限流，适合抓取国内源为主 + 国际源为辅的组合。

### 5.4 云函数（腾讯云/阿里云定时触发）

把项目打成 zip 部署到云函数，定时触发器调用 `python main.py` 入口
（云函数入口需要 handler 包装，参考 5.3 的命令行调用即可）。

### 5.5 Streamlit Community Cloud（免费，Web 界面最简单）

```text
1. 把项目推到 GitHub（私有仓库即可）
2. 打开 https://share.streamlit.io → New app → 选仓库/分支
3. Main file 填 app.py，Python 版本选 3.11
4. Advanced settings → Secrets 粘贴（等价于 .env）：
   LLM_API_KEY = "sk-..."
   TELEGRAM_BOT_TOKEN = "..."
   TELEGRAM_CHAT_ID = "..."
5. Deploy 完成，浏览器访问 https://<app>.streamlit.app（手机同样可访问）
```

注意：免费版实例**休眠**且**文件系统临时**——配置中心的写盘修改重启后丢失；
请用 Secrets（环境变量）承载密钥；每日定时推送仍由 GitHub Actions 承担。

### 5.6 Railway / Render / Fly.io（免费额度，可常驻）

仓库已内置 `Dockerfile`、`render.yaml`、`Procfile`、`runtime.txt`、`fly.toml.example`。

**Railway**（约 $5 免费额度 / 月，够跑 1 个服务）：
```bash
railway init && railway up        # 或 GitHub 集成自动部署
# 环境变量在面板设置；如需持久化 data/ 可加 Volume（付费项）
```

**Render**（免费 Web Service，15 分钟无访问休眠）：
```text
New → Blueprint → 选本仓库（自动读 render.yaml）
密钥在 Environment 页添加 LLM_API_KEY 等
健康检查 /_stcore/health 已配置
```

**Fly.io**（免费额度约 3 台共享 VM，需绑卡）：
```bash
cp fly.toml.example fly.toml      # 改 app 名称
fly launch --no-deploy
fly secrets set LLM_API_KEY=... TELEGRAM_BOT_TOKEN=...
fly deploy                          # 可选：挂载 volume 持久化 data/
```

三个平台都支持 `docker` 方式：`docker build -t workbench . && docker run -p 8501:8501 -e LLM_API_KEY=... workbench`。

## 7. 扩展指南：添加新模块

以「每日待办提醒」为例，三步接入，核心代码零改动：

**第 1 步**：新建包 `workbench/modules/todo_reminder/`

**第 2 步**：写模块主体 `todo_reminder/module.py`：

```python
# workbench/modules/todo_reminder/module.py
from ...core.registry import Module, register

def run(ctx):
    """ctx: Context —— config / state / status / log 都在这里"""
    cfg = ctx.config.get("todo_reminder", {})
    # ... 你的业务逻辑：读数据 → 处理 → 推送 ...
    from ...channels import broadcast
    results = broadcast("📋 今日待办", "1. ...\n2. ...", ctx.config, ctx.log)
    ctx.status.update(module="todo_reminder", push=results)
    return {"module": "todo_reminder", "push": results}

register(Module(id="todo_reminder", name="待办提醒", run=run))
```

**第 3 步**：在 `config/config.yaml` 加模块配置段 + 调度器里加一行定时任务
（`core/scheduler.py` 的 `add_job` 处）。

**扩展点汇总**：

| 想扩展什么 | 改哪里 |
|---|---|
| 加新闻源 | `config/feeds.yaml` |
| 调简报风格/结构 | `modules/news_digest/prompts.py`（纯文本模板） |
| 加推送渠道 | 继承 `channels/base.py` + 注册进 `channels/__init__.py` |
| 加新数据源类型（API/X） | `modules/news_digest/fetcher.py` 的 `fetch_source` 分发处 |
| 换 LLM / 改蒸馏逻辑 | `distill.py` / `config.yaml llm 段` |
| 加新功能模块 | 按上面三步 |

## 8. 可观测性

```bash
python -m workbench.cli status            # 上次运行摘要 + 最近错误
python -m workbench.cli status --json     # 机器可读
python -m workbench.cli serve             # http://127.0.0.1:8123/status.json
tail -f data/logs/workbench.log           # 全量日志（滚动 5MB×3）
```

每次运行的状态（抓取数/保留数/是否 LLM 生成/推送结果/错误）写入
`data/status/status.json`，推送失败只记错误不影响其他渠道。

## 9. 注意事项与优化建议

**成本**
- 默认每天 1 次 LLM 调用（约 3-5k token 输入 + 2.5k 输出），DeepSeek-chat 约 ¥0.01-0.03/天；
- 用便宜模型跑蒸馏完全够用；`max_items` 调小可进一步降本。

**合规与版权**
- 简报是「事实摘要 + 个人分析」，非原文转载；每条附来源链接；
- 遵守目标站点 robots.txt 与 ToS，抓取频率限制在每天 1 次（远低于正常访问）；
- 个人使用无风险，请勿用于商业分发。

**反爬与稳定性**
- 每天仅抓 1 次，不要增加频率；被 403/429 时检查 UA 与代理；
- 源挂了不影响整体（单源失败只记录）；推送渠道支持多路冗余；
- 源地址会变，`feeds.yaml` 集中管理，坏了改一行即可。

**推送稳定性**
- 每个渠道独立 try/except，互不拖累；
- 邮件/Telegram 尽量配 2 个以上，互为备份；
- 企业微信/钉钉/飞书机器人有频率限制（如 20 条/分钟），本项目每天 1 条远未触及。

**后续扩展建议**（架构已预留）
- 待办/日历提醒：同一 `broadcast` + 新模块；
- 知识库总结：模块内复用 `llm_chat`，数据落 `data/` 或接 SQLite；
- 多模块调度：在 `scheduler.py` 的 add_job 处按模块逐个注册即可。
