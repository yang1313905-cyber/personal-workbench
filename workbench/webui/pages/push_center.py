"""推送中心：连接并验证所有最终推送软件。

一站式完成：查看渠道状态 → 配置凭据 → 发送测试消息 → 启用/停用。
"""
from __future__ import annotations

import streamlit as st

from workbench.channels import build_channel

from .. import config_editor as ce
from .. import context as wctx
from .. import data as wdata

CHANNEL_ICONS = {
    "telegram": "✈️", "wecom": "🏢", "feishu": "📘",
    "dingtalk": "🐜", "smtp": "📧", "webhook": "🔗",
}
CHANNEL_DESC = {
    "telegram": "Telegram Bot —— 最稳定，免费无限制",
    "wecom": "企业微信群机器人 —— 国内最快，群内消息",
    "feishu": "飞书群机器人 —— 卡片消息，国内办公场景",
    "dingtalk": "钉钉群机器人 —— 卡片消息，国内办公场景",
    "smtp": "SMTP 邮件 —— 永不失效，天然归档",
    "webhook": "通用 Webhook —— Server酱 / PushPlus / WxPusher / Bark",
}
STATUS_BADGE = {"ok": "✅ 就绪", "missing": "⚠️ 缺配置", "disabled": "⛔ 未启用"}

GUIDE_MD = """
**✈️ Telegram**：找 @BotFather → `/newbot` 创建 → 得到 token；向 @userinfobot 发 `/start` 拿到 chat_id。
**🏢 企业微信**：任意群 → 右上角 `...` → 添加群机器人 → 复制 Webhook 地址。
**📘 飞书**：群设置 → 群机器人 → 自定义机器人 → 复制 Webhook。
**🐜 钉钉**：群设置 → 智能群助手 → 自定义机器人 → 复制 Webhook（建议关闭安全设置或选用「自定义关键词」）。
**📧 邮件**：QQ 邮箱 → 设置 → 账户 → 开启 SMTP 服务 → 生成**授权码**（非登录密码）；Gmail 用「应用专用密码」。
**🔗 通用 Webhook**：Server酱（sct.ftqq.com，5条/天）/ PushPlus（pushplus.plus，200条/天）/ WxPusher / Bark。
"""


def _status(cfg: dict, cid: str, cc: dict) -> str:
    if not cc.get("enabled"):
        return "disabled"
    try:
        build_channel(cfg, cid).validate()
        return "ok"
    except ValueError:
        return "missing"


def _send_test(cfg: dict, cid: str) -> None:
    try:
        ch = build_channel(cfg, cid)
        with st.spinner(f"正在通过 {cid} 发送…"):
            ch.send("✅ 推送中心测试",
                    "如果你收到这条消息，说明推送链路已经打通 🎉\n\n—— 个人智能工作台")
        st.toast(f"{cid} 测试成功 🎉")
        st.success(f"✅ {cid} 测试消息发送成功！")
    except Exception as e:  # noqa: BLE001
        st.error(f"❌ {cid} 测试失败：{e}")


def _toggle_channel(cid: str, current: bool, enabled: bool) -> None:
    if enabled == current:
        return
    ed = ce.config_editor()
    try:
        ed.set(f"channels.{cid}.enabled", bool(enabled))
        ed.save()
        wctx.invalidate()
        st.success(f"渠道 {cid} 已{'启用' if enabled else '停用'}")
        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.error(f"保存失败：{e}")


def render() -> None:
    st.title("📡 推送中心")
    st.caption("连接最终推送软件：查看状态 → 配置凭据 → 发送测试 → 启用，一条龙完成。")

    cfg = wctx.get_cfg()
    channels = cfg.get("channels", {})

    # ---------------- 概览指标 ----------------
    enabled = [cid for cid, cc in channels.items() if cc.get("enabled")]
    ready = [cid for cid in enabled if _status(cfg, cid, channels[cid]) == "ok"]
    last_push = wdata.read_status().get("push") or {}

    c1, c2, c3 = st.columns(3)
    c1.metric("启用渠道", f"{len(enabled)} / {len(channels)}")
    c2.metric("已配置就绪", len(ready))
    c3.metric("上次推送成功", f"{sum(1 for v in last_push.values() if v)}/{len(last_push)}"
              if last_push else "—")
    st.markdown('<span class="wb-pill">推送顺序：news_digest.push.channels（留空=全部启用渠道）</span>',
                unsafe_allow_html=True)
    st.divider()

    # ---------------- 渠道卡片 ----------------
    for cid, cc in channels.items():
        status = _status(cfg, cid, cc)
        icon = CHANNEL_ICONS.get(cid, "📦")
        with st.container(border=True):
            col1, col2, col3 = st.columns([1.1, 2.6, 1.6])
            with col1:
                st.markdown(f"### {icon} `{cid}`\n\n**{STATUS_BADGE[status]}**")
            with col2:
                st.markdown(f"**{CHANNEL_DESC.get(cid, '')}**")
                if status == "missing":
                    keys = ce.CHANNEL_ENV_KEYS.get(cid, [])
                    st.caption(f"待配置：{'、'.join(keys)}"
                               "（去「配置中心 → 环境变量」或云端 Secrets 填写）")
                elif status == "disabled":
                    st.caption("当前未启用，下方开关可随时启用")
                else:
                    st.caption("配置完整，可直接使用")
            with col3:
                _toggle_channel(cid, bool(cc.get("enabled")),
                                st.toggle("启用", value=bool(cc.get("enabled")),
                                          key=f"push_toggle_{cid}"))
                if status != "disabled":
                    if st.button("📨 发送测试消息", key=f"push_test_{cid}",
                                 use_container_width=True):
                        _send_test(cfg, cid)

    st.divider()

    # ---------------- 最近推送记录 ----------------
    st.subheader("🕘 最近推送记录")
    rows = []
    for d in wdata.list_digest_dates()[:7]:
        rec = wdata.digest_record(d)
        if rec:
            rows.append({"日期": d, "推送渠道": "、".join(rec["channels"]) or "—",
                         "生成时间 (UTC)": rec["created_at"]})
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("暂无推送记录 —— 先去首页生成一份简报")

    # ---------------- 指南 ----------------
    with st.expander("📖 各渠道凭据获取指南（点开查看）"):
        st.markdown(GUIDE_MD)
