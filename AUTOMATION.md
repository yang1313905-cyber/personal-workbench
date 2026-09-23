# 每日自动推送：云端运行（GitHub Actions）

工作台每天 **北京时间 08:00** 自动生成新闻简报并发送到 QQ 邮箱，**由 GitHub 的服务器执行**
——电脑关机、睡眠、断网、不在身边都不影响送达。

## 运行方式总览

| 方式 | 状态 | 说明 |
| --- | --- | --- |
| **GitHub Actions（云端）** | ✅ 当前生效 | 每天 08:00 在 GitHub 服务器运行，见 `.github/workflows/digest.yml` |
| 本地 launchd（本机） | ⏸ 已暂停 | 原 `~/Library/LaunchAgents/com.dsh.personal-workbench.daily.plist.disabled` |

云端与本地**不要同时开启**，否则同一天可能收到两封邮件（两边各自维护自己的状态库，
互不知晓对方的发送记录）。

### 恢复 / 停用本地自动发送

```bash
# 恢复本机每天 08:00 发送
mv ~/Library/LaunchAgents/com.dsh.personal-workbench.daily.plist.disabled \
   ~/Library/LaunchAgents/com.dsh.personal-workbench.daily.plist
launchctl enable gui/$(id -u)/com.dsh.personal-workbench.daily
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dsh.personal-workbench.daily.plist

# 再次暂停
launchctl bootout gui/$(id -u)/com.dsh.personal-workbench.daily
launchctl disable gui/$(id -u)/com.dsh.personal-workbench.daily
```

## 云端运行机制

- **定时**：`0 0 * * *`（UTC）= 北京时间 08:00；另有 `30 0 * * *`（08:30）作为重试。
  GitHub 的定时任务在高峰期可能延迟数分钟到数十分钟，属正常现象（cron 用 UTC，不要写成 8）。
- **幂等**：入口 `scripts/daily_digest.py` 只有当天**确实送达邮件**才记为完成，
  所以重试不会重复发信；反之上一次失败时会真正重发。
- **状态持久化**：Actions 每次都是全新容器，用 `actions/cache` 缓存 `data/` 目录跨天复用，
  以保留「跨天去重历史」和「当天已发送标记」。
- **手动补发**：仓库 Actions 页 → daily-digest → Run workflow（可勾选 `force` 强制重发）。
- **查看结果**：每次运行的 Summary 页会直接显示当日简报正文，附件里也有 md 存档。

### 需要的仓库 Secrets

仓库 Settings → Secrets and variables → Actions：

| Secret | 值 |
| --- | --- |
| `LLM_API_KEY` | 智谱 API Key（open.bigmodel.cn） |
| `SMTP_USER` | 发件 QQ 邮箱 |
| `SMTP_PASSWORD` | QQ 邮箱 SMTP 授权码（16 位，非登录密码） |
| `SMTP_FROM` | 发件邮箱（同上） |
| `SMTP_TO` | 收件邮箱 |

密钥只存在于 GitHub Secrets 与本地 `.env`，`.env` 已被 `.gitignore` 排除，从未进入 git 历史。

## 本地常用命令

```bash
cd ~/personal-workbench

# 立即生成并发送一封（本机执行）
.venv/bin/python scripts/daily_digest.py --force

# 只查看今天是否已发送，不发信
.venv/bin/python scripts/daily_digest.py --check

# 查看运行状态 / 启动 Web 管理界面
.venv/bin/python -m workbench.cli status
.venv/bin/streamlit run app.py        # http://127.0.0.1:8501
```

## 为什么项目放在 ~/personal-workbench

macOS 的 TCC 隐私保护不允许 launchd 派生的后台进程读取 `~/Desktop`、`~/Documents`、`~/Downloads`，
本地定时任务在 `~/Desktop/...` 下会直接报 `PermissionError: Operation not permitted`。
因此项目实体位于 `~/personal-workbench`，并在原路径
`~/Desktop/111/DEEP/Better/personal-workbench` 保留软链接，两边路径都能正常访问。

## 已知情况

`config/feeds.yaml` 中 3 个来源在当前网络下不可达（bbc-tech、bbc-world、reuters-google），
`36氪`、`X 高影响力账号` 的 url 为空占位。当前每日简报实际来自
TechCrunch、The Verge、华尔街见闻。可在 Web 界面「源管理」页增删来源。
