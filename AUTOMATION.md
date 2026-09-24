# 每日自动推送：云端运行（GitHub Actions）

工作台每天 **北京时间 08:00** 自动生成新闻简报并发送到 QQ 邮箱，**由 GitHub 的服务器执行**
——电脑关机、睡眠、断网、不在身边都不影响送达。

- 仓库（私有）：`yang1313905-cyber/personal-workbench`
- 工作流：`.github/workflows/digest.yml`
- 入口脚本：`scripts/daily_digest.py`

## 运行方式总览

| 方式 | 状态 | 说明 |
| --- | --- | --- |
| **GitHub Actions（云端）** | ✅ 当前生效 | 每天 08:00 在 GitHub 服务器运行 |
| 本地 launchd（本机） | ⏸ 已暂停 | 配置改名为 `com.dsh.personal-workbench.daily.plist.disabled` |

**云端与本地不要同时开启**：两边各自维护自己的状态库，互不知晓对方的发送记录，
同一天可能收到两封邮件。

## ⚠️ 已知问题：GitHub 的定时触发在本账号下不生效（2026-09-24 实测）

**现象**：2026-09-24 早上没有收到简报。仓库里 `event=schedule` 的运行数为 **0** ——
定时任务从未触发过，而手动触发（`workflow_dispatch`）每次都正常。

**已做的排查**：

| 排查项 | 结果 |
| --- | --- |
| 远端 workflow 的 cron 配置 | ✅ 正确（`0 0 * * *` / `30 0 * * *`） |
| 工作流状态 | ✅ `active`；仓库 Actions `enabled` |
| GitHub 平台状态 | ✅ Actions 组件 operational（当天的 incident 只影响 Projects 标签） |
| 02:00–03:00 两次定时 | ❌ 均未触发 |
| 临时探针（私有仓库，`*/5` 每 5 分钟） | ❌ 18 分钟内 4+ 次应触发，实际 0 次 |
| 临时探针（**公开**仓库，`*/5`） | ❌ 同样 0 次 |

**结论**：不是 cron 写法问题，也不是私有/公开仓库差异，而是**该账号的 schedule 事件没有被投递**。
GitHub 官方文档也说明 schedule 在高负载时会被延迟甚至丢弃；社区有同样案例
（[community#203822](https://github.com/orgs/community/discussions/203822)，
新仓库 schedule 完全不触发、`workflow_dispatch` 正常）。

**影响**：仅靠 GitHub cron **无法保证**每天早上送达。手动触发链路是好的，
所以可靠方案是「外部调度器 → 调用 GitHub API 触发同一条工作流」。

**当前缓解措施**：cron 错峰为 08:07 / 08:27 / 08:47 三次尝试；
入口脚本幂等，多次触发只会发出一封；每天未收到时可人工补发（见下）。



- **定时**：`7 0` / `27 0` / `47 0`（UTC）= 北京时间 **08:07 / 08:27 / 08:47 三次尝试**。
  cron 用 UTC，写成 `8 * * * *` 会变成下午 4 点。
  **为什么不用整点 08:00**：2026-09-24 实测配置的 `0 0 * * *`（08:00）与 `30 0 * * *`（08:30）
  两次都**没有触发**（`event=schedule` 运行数为 0），当天简报由人工补发。
  GitHub 官方文档说明 `schedule` 在高负载时会被延迟甚至丢弃，而 `00:00 UTC` 是全球最拥挤的 cron 时段。
  因此改为：错峰到 00:07 起 + 一小时内多次尝试；配合入口脚本幂等，多次触发也只会发出一封。
- **幂等**：`scripts/daily_digest.py` 只有当天**确实送达邮件**才记为完成，重试不会重复发信；
  上一次失败时会真正重发。
- **状态持久化**：Actions 每次都是全新容器，用 `actions/cache` 缓存 `data/` 目录跨天复用，
  以保留「跨天去重历史」与「当天已发送标记」。
- 定时路径与手动强制路径拆成两个 step（`if: github.event.inputs.force == 'true'`），
  正常路径不含任何表达式，避免 `schedule` 事件下 `inputs` 上下文缺失导致定时运行失败。
- 依赖使用 `requirements-cloud.txt`（仅 requests/feedparser/PyYAML），安装约 10 秒。

### 手动操作

```bash
R=yang1313905-cyber/personal-workbench

gh run list --repo $R --limit 5                    # 查看运行历史
gh workflow run daily-digest.yml --repo $R         # 手动补发（当天已发过会跳过）
gh run watch --repo $R                             # 实时跟踪最近一次运行
gh workflow enable daily-digest.yml --repo $R      # 若被 GitHub 自动停用则重新启用
```

需要**强制重发**时：仓库 Actions 页 → daily-digest → Run workflow → 勾选 `force`。

每次运行的 Summary 页会直接显示当日简报正文，Artifacts 里保存 md 存档（保留 30 天）。

### 依赖的仓库 Secrets

Settings → Secrets and variables → Actions（已配置完成）：

`LLM_API_KEY`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_FROM`、`SMTP_TO`

密钥只存在于 GitHub Secrets 与本地 `.env`；`.env` 已被 `.gitignore` 排除，
且已核验从未进入 git 历史（64 个被跟踪文件中无任何密钥值）。

## 本地常用命令

```bash
cd ~/personal-workbench

python3 scripts/daily_digest.py --force     # 本机立即生成并发送一封
python3 scripts/daily_digest.py --check     # 只查看今天是否已发送
.venv/bin/python -m workbench.cli status    # 运行状态
.venv/bin/streamlit run app.py              # Web 管理界面 http://127.0.0.1:8501
```

### 恢复本机每天 08:00 发送（默认关闭）

```bash
mv ~/Library/LaunchAgents/com.dsh.personal-workbench.daily.plist.disabled \
   ~/Library/LaunchAgents/com.dsh.personal-workbench.daily.plist
launchctl enable    gui/$(id -u)/com.dsh.personal-workbench.daily
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dsh.personal-workbench.daily.plist
```

## 简报格式（2026-09-23 改版）

邮件正文由「素材编号契约 + 程序渲染」两层构成：

1. **模型只输出编号与分析**：素材在 Prompt 里带 `[n]` 编号，模型按 `[n] 分析内容` 输出，
   不写标题、不写来源、不写链接。
2. **程序回填真实信息**：`workbench/modules/news_digest/render.py` 依据编号从真实抓取结果
   回填标题、来源、时间与原文链接，生成带层级的 Markdown。
   这样链接永远指向真实原文，杜绝模型编造 URL、标题与原文不符。
3. **邮件渲染**：`workbench/channels/markdown_email.py` 把 Markdown 渲染成内联样式 HTML
   （22px 报头 / 15px 章节 / 16px 条目标题+序号 / 14px 正文 / 12px 来源时间），
   标题即可点击的超链接；同时生成保留 URL 的纯文本版作为兜底。

其它要点：
- 重点条目按重要性**降序编号**；末尾「其他值得一读」附带条目级链接，方便随时跳转。
- 模型若没按编号格式输出，会自动纠正重写一次；仍失败则按排序降级渲染，邮件不会残缺。
- 分析开头若复述标题（模型常犯），由程序确定性删除该句。

## 为什么项目放在 ~/personal-workbench

macOS 的 TCC 隐私保护不允许 launchd 派生的后台进程读取 `~/Desktop`、`~/Documents`、`~/Downloads`，
本地定时任务在 `~/Desktop/...` 下会直接报 `PermissionError: Operation not permitted`。
项目实体因此在 `~/personal-workbench`，并在原路径
`~/Desktop/111/DEEP/Better/personal-workbench` 保留软链接，两边路径都可正常访问。

## 实测记录（2026-09-23）

| 项目 | 云端 GitHub Actions | 本机 |
| --- | --- | --- |
| 抓取条数 | **124 条，0 个来源失败** | 49 条，3 个来源失败 |
| 邮件送达 | ✅ `邮件推送成功` | ✅ |
| 重复触发 | ✅ 第二次运行正确跳过，未重复发信 | ✅ |

云端能访问 BBC、Google News 等在本机网络下不可达的来源，因此云端简报的来源覆盖更完整。
（本机 `config/feeds.yaml` 中 bbc-tech、bbc-world、reuters-google 三个来源因网络原因失败，
36氪 与 X 高影响力账号 的 url 仍是空占位。）
