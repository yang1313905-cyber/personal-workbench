# 云端网页版（Streamlit Community Cloud）

把工作台的 Web 管理界面部署到云端，**任何设备打开浏览器就能用**，不需要本机开机。

- 平台：Streamlit Community Cloud（免费、免信用卡、原生支持 Streamlit）
- 仓库：`yang1313905-cyber/personal-workbench`（私有）
- 入口文件：`app.py`
- 预计网址：`https://<你填的子域名>.streamlit.app`

## 一次性部署步骤

1. 打开 <https://share.streamlit.io> → **Continue with GitHub** → 授权（只读仓库权限）
2. 点 **Create app** → 选 **Deploy a public app from GitHub**
3. 按下表填写：

   | 字段 | 值 |
   | --- | --- |
   | Repository | `yang1313905-cyber/personal-workbench` |
   | Branch | `main` |
   | Main file path | `app.py` |
   | App URL（子域名） | 你喜欢的名字，例如 `hannibal-workbench` |

4. 展开 **Advanced settings → Secrets**，粘贴 `CLOUD-SECRETS` 里那份配置（见下）
5. 点 **Deploy**，等 1–3 分钟构建完成，浏览器会打开你的网址

## Secrets 配置

Secrets 分两节：`[auth]` 是登录凭据（**只存哈希，不存明文**），`[env]` 是运行时密钥。

```toml
[auth]
username = "Hannibal"
password_hash = "pbkdf2_sha256$260000$<salt>$<hash>"
role = "admin"
display = "Hannibal"

[env]
LLM_API_KEY = "..."
SMTP_USER = "..."
SMTP_PASSWORD = "..."
SMTP_FROM = "..."
SMTP_TO = "..."
```

生成新密码哈希：

```bash
cd ~/personal-workbench
.venv/bin/python -m workbench.webui.auth --hash '你的新密码'
```

## 登录与权限

- **入口即登录页**：未登录无法看到任何业务页面（`app.py` 第一个动作就是过网关）。
- **角色**：
  - `admin`：全部 9 个页面，含配置中心、运行日志、蒸馏中心、推送中心
  - `viewer`：只读页面（仪表盘 / 新闻源 / 简报详情 / 历史简报 / 关于）
  - 想看只读效果，把 Secrets 里的 `role` 改成 `viewer` 即可
- **退出登录**：侧边栏底部「🚪 退出登录」
- **暴力猜解防护**：10 分钟内失败 5 次锁定 5 分钟，且每次失败有固定延时

## 安全设计（重要）

| 风险 | 处理 |
| --- | --- |
| 公网裸奔 | 云端**没有配置 `[auth]` 时拒绝提供服务**（fail closed），而不是放行 |
| 密钥出现在网页里 | 云端模式配置中心**不回显、不可编辑** `.env`，只显示「已配置/未配置」与打码值 |
| `.env` 进仓库 | `.env`、`.streamlit/secrets.toml` 都在 `.gitignore` 里，从未提交 |
| 密钥进仓库 | 云端密钥只存在于 Streamlit Secrets（加密存储），仓库里只有占位符 |
| 口令泄露 | 仓库与配置里只有 PBKDF2 哈希；明文口令不落盘 |
| 越权访问 | 页面按角色过滤；admin-only 页面非管理员根本不会出现在导航里 |

> ⚠️ 注意：网址本身是公开可达的，保护完全依赖登录口令。**请勿把网址和口令一起发在公开场合**；
> 若口令外泄，用上面的 `--hash` 命令换一个并更新 Secrets 即可立即生效。

## 云端网页能做什么 / 不能做什么

- ✅ 查看今日简报、历史简报、新闻源、最后运行状态（这些数据由每日工作流提交回仓库）
- ✅ 手机 / 平板 / 别的电脑打开，看排版好的简报原文
- ⚠️ 云端实例的磁盘是临时的：在配置中心做的修改、以及在云端触发「立即生成」产生的新文件，
  在实例重启后会丢失。**配置的长期来源永远是仓库里的 `config/` 与 Streamlit Secrets。**
- ℹ️ 免费实例闲置一段时间会休眠，下次打开首次加载需要几十秒预热

## 排错

| 现象 | 原因 / 处理 |
| --- | --- |
| 页面显示「已拒绝提供服务」 | Secrets 没配 `[auth]`，按上面模板补上后 Reboot app |
| 登录一直提示密码错误 | 哈希与口令不匹配，用 `--hash` 重新生成并更新 Secrets |
| 打开是空白/报错 | 看 Streamlit Cloud 右侧 **Manage app → Logs** |
| 数据是空的 | 每日工作流的「Persist digest to repo」那步没成功，去 Actions 看该步日志 |
