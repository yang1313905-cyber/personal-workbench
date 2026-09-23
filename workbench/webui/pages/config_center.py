"""配置中心：新闻源 / LLM / 调度 / 推送渠道 / 环境变量 / 有效配置。

保存策略：
- YAML 用 ruamel 保注释原地修改，写前校验、写前备份（.bak）
- 密钥统一走 .env（环境变量优先于配置文件，云端部署用 Secrets 即可）
- 保存后清空进程内配置缓存，立即生效
"""
from __future__ import annotations

import streamlit as st

from .. import config_editor as ce
from .. import context as wctx

TIMEZONES = ["Asia/Shanghai", "Asia/Hong_Kong", "Asia/Tokyo", "Europe/London",
             "America/New_York", "America/Los_Angeles", "UTC"]


def _save(editor: ce.YamlEditor, msg: str) -> None:
    """保存 + 校验 + 缓存失效。"""
    try:
        editor.save()
        wctx.invalidate()
        st.success(f"✅ {msg}（原文件已备份为 .bak，立即生效）")
        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.error(f"❌ 保存失败，未写入文件：{e}")


def _feeds_tab() -> None:
    st.subheader("📰 新闻源（feeds.yaml）")
    st.caption("修改后点击「保存」；每条源独立保存，不影响其他配置。"
               "新增源请填完整字段；禁用源抓取时会跳过。")
    ed = ce.feeds_editor()
    sources = ed.sources()

    for i, src in enumerate(list(sources)):
        enabled = bool(src.get("enabled", True))
        with st.expander(f"{'✅' if enabled else '⛔'} {src.get('name', src.get('id', '?'))}",
                         expanded=False):
            f_id = st.text_input("id（唯一标识）", str(src.get("id", "")), key=f"feeds_id_{i}")
            f_name = st.text_input("名称", str(src.get("name", "")), key=f"feeds_name_{i}")
            f_url = st.text_input("URL / 接口地址", str(src.get("url", "")), key=f"feeds_url_{i}")
            f_kind = st.selectbox("类型", ["rss", "wallstreetcn"],
                                  index=0 if src.get("kind", "rss") == "rss" else 1,
                                  key=f"feeds_kind_{i}")
            f_lang = st.selectbox("语言", ["en", "zh"],
                                  index=0 if src.get("lang", "en") == "en" else 1,
                                  key=f"feeds_lang_{i}")
            f_weight = st.slider("权重（越大越优先）", 0.0, 1.0,
                                 float(src.get("weight", 1.0)), 0.05, key=f"feeds_w_{i}")
            f_enabled = st.toggle("启用该源", enabled, key=f"feeds_en_{i}")

            c1, c2, c3 = st.columns(3)
            if c1.button("💾 保存", key=f"feeds_save_{i}", use_container_width=True):
                for k, v in {"id": f_id, "name": f_name, "url": f_url, "kind": f_kind,
                             "lang": f_lang, "weight": float(f_weight),
                             "enabled": bool(f_enabled)}.items():
                    sources[i][k] = v
                _save(ed, f"数据源「{f_name or f_id}」已保存")
            if c2.button("🗑️ 删除", key=f"feeds_del_{i}", use_container_width=True):
                ed.remove_source(i)
                _save(ed, "数据源已删除")
            if c3.button("⏹ 禁用/启用", key=f"feeds_toggle_{i}", use_container_width=True):
                sources[i]["enabled"] = not enabled
                _save(ed, "已切换启用状态")

    st.divider()
    st.subheader("➕ 新增数据源")
    with st.form("new_feed", clear_on_submit=True):
        n_id = st.text_input("id", placeholder="my-source")
        n_name = st.text_input("名称", placeholder="我的媒体")
        n_url = st.text_input("URL", placeholder="https://example.com/rss")
        n_kind = st.selectbox("类型", ["rss", "wallstreetcn"])
        n_lang = st.selectbox("语言", ["zh", "en"])
        submitted = st.form_submit_button("添加")
        if submitted:
            if not n_id or not n_url:
                st.error("id 和 URL 必填")
            else:
                ed.append_source({"id": n_id, "name": n_name or n_id, "kind": n_kind,
                                  "url": n_url, "lang": n_lang, "weight": 0.8,
                                  "enabled": True})
                _save(ed, f"已新增数据源「{n_name or n_id}」")


def _llm_tab() -> None:
    st.subheader("🤖 LLM 参数（config.yaml → llm）")
    st.caption("支持任意 OpenAI 兼容接口：OpenAI / DeepSeek / Moonshot / 硅基流动 / 智谱 GLM / Groq / 本地 Ollama。"
               "API Key 直接在下方输入框填写（保存到 .env 的 LLM_API_KEY，密钥不落配置文件）。")
    ed = ce.config_editor()
    llm = ed.get("llm", {}) or {}
    current_key = ce.env_value("LLM_API_KEY")

    with st.form("llm_form"):
        base_url = st.text_input("Base URL", str(llm.get("base_url", "")),
                                 placeholder="https://api.deepseek.com/v1")
        model = st.text_input("模型", str(llm.get("model", "")),
                              placeholder="glm-4-flash / deepseek-chat / gpt-4o-mini / llama3")
        api_key = st.text_input(
            "API Key（LLM_API_KEY）",
            value=current_key,
            type="password",
            help="留空则保持原值；保存后用于 ${LLM_API_KEY} 注入。"
                 "本地 Ollama 等无需密钥的服务可留空。",
        )
        temperature = st.slider("Temperature", 0.0, 2.0, float(llm.get("temperature", 0.4)), 0.05)
        max_tokens = st.number_input("Max Tokens", 500, 8000, int(llm.get("max_tokens", 2500)), 100)
        timeout = st.number_input("超时（秒）", 30, 600, int(llm.get("timeout", 120)), 10)
        if st.form_submit_button("💾 保存 LLM 配置", type="primary"):
            try:
                for k, v in {"base_url": base_url, "model": model,
                             "temperature": float(temperature),
                             "max_tokens": int(max_tokens), "timeout": int(timeout)}.items():
                    ed.set(f"llm.{k}", v)
                ce.set_env("LLM_API_KEY", api_key.strip())  # 空值=删除该键
                _save(ed, "LLM 配置已保存")
            except KeyError as e:
                st.error(f"保存失败：{e}")

    if not current_key:
        st.warning("⚠️ 尚未配置 LLM_API_KEY：LLM 蒸馏会失败并降级为「本地兜底简报」。"
                   "若你的服务商需要密钥（如 Groq / DeepSeek），请在上方填写后保存。")


def _schedule_tab() -> None:
    st.subheader("⏰ 调度（config.yaml → schedule）")
    st.caption("影响 `workbench worker` 进程与 Web 端提示；**cron 任务修改后需重新运行 "
               "`bash scripts/install_cron.sh`**（或按新的时间手动改 crontab）。")
    ed = ce.config_editor()
    sched = ed.get("schedule", {}) or {}

    with st.form("schedule_form"):
        t = str(sched.get("time", "08:00"))
        time_text = st.text_input("每日推送时间（HH:MM）", t)
        tz = st.selectbox("时区", TIMEZONES,
                          index=TIMEZONES.index(sched.get("timezone"))
                          if sched.get("timezone") in TIMEZONES else 0)
        catch_up = st.toggle("错过补发（启动时若今日未生成则立即执行）",
                             bool(sched.get("catch_up", True)))
        if st.form_submit_button("💾 保存调度配置", type="primary"):
            try:
                ed.set("schedule.time", time_text.strip())
                ed.set("schedule.timezone", tz)
                ed.set("schedule.catch_up", bool(catch_up))
                _save(ed, "调度配置已保存")
            except KeyError as e:
                st.error(f"保存失败：{e}")


def _channels_tab() -> None:
    st.subheader("📤 推送渠道（config.yaml → channels）")
    st.caption("开关写入配置文件；密钥类字段（Token/Webhook/授权码）写入 .env（或云端 Secrets）。"
               "保存后可用首页「立即生成」或 `workbench test-channel <id>` 验证。")
    ed = ce.config_editor()
    channels = ed.get("channels", {}) or {}

    for cid, cc in channels.items():
        enabled = bool(cc.get("enabled"))
        with st.expander(f"{'✅' if enabled else '⛔'} {cid}", expanded=False):
            col1, _ = st.columns([1, 3])
            new_enabled = col1.toggle("启用", enabled, key=f"ch_en_{cid}")
            if new_enabled != enabled:
                try:
                    ed.set(f"channels.{cid}.enabled", new_enabled)
                    _save(ed, f"渠道 {cid} 已{'启用' if new_enabled else '禁用'}")
                except KeyError:
                    pass

            # 部分渠道的直连参数写在配置文件里
            if cid == "smtp":
                with st.form(f"smtp_cfg_{cid}", clear_on_submit=False):
                    c_host = st.text_input("SMTP 主机", str(cc.get("host", "")), key="smtp_host")
                    # 端口允许写成 ${SMTP_PORT:-465} 这类环境变量表达式（云端用 Secret 覆盖），
                    # 因此不能无条件当整数解析，否则配置页会直接报错。
                    raw_port = cc.get("port", 465)
                    try:
                        c_port = st.number_input("端口", 1, 65535, int(raw_port), key="smtp_port")
                        port_is_int = True
                    except (TypeError, ValueError):
                        c_port = st.text_input(
                            "端口", str(raw_port), key="smtp_port",
                            help="可填数字；也可保留 ${SMTP_PORT:-465} 这类环境变量表达式",
                        )
                        port_is_int = False
                    c_ssl = st.toggle("SSL", bool(cc.get("use_ssl", True)), key="smtp_ssl")
                    if st.form_submit_button("💾 保存 SMTP 参数"):
                        try:
                            port_val = int(c_port) if port_is_int else str(c_port).strip()
                            if not str(port_val):
                                raise ValueError("端口不能为空")
                            ed.set("channels.smtp.host", c_host)
                            ed.set("channels.smtp.port", port_val)
                            ed.set("channels.smtp.use_ssl", bool(c_ssl))
                            _save(ed, "SMTP 参数已保存")
                        except (KeyError, ValueError) as e:
                            st.error(f"保存失败：{e}")

            env_keys = ce.CHANNEL_ENV_KEYS.get(cid, [])
            if env_keys:
                st.markdown("**需要配置的环境变量（写入 .env）：**")
                for key in env_keys:
                    current = ce.env_value(key)
                    val = st.text_input(key, value=current, type="password" if "TOKEN" in key or "PASSWORD" in key or "KEY" in key else "default",
                                        key=f"env_{cid}_{key}")
                    if st.button(f"💾 保存 {key}", key=f"envsave_{cid}_{key}"):
                        ce.set_env(key, val.strip())
                        wctx.invalidate()
                        st.success(f"{key} 已保存" + ("（已清空）" if not val.strip() else ""))


def _env_tab() -> None:
    st.subheader("🔑 环境变量（.env）")
    st.caption("这里保存的密钥以 ${KEY} 形式注入配置。云端部署时请改用平台 Secrets"
               "（本页在云端为临时文件，实例重启后丢失）。")

    col1, col2 = st.columns([3, 2])
    if col1.button("📄 从 .env.example 初始化（仅当 .env 不存在或想重置）"):
        n = ce.init_env_from_example()
        wctx.invalidate()
        st.success(f"已生成 .env（{n} 个键，值均为空，请逐个填写）")
        st.rerun()
    if col2.button("🔄 重新读取"):
        st.rerun()

    entries = ce.load_env()
    kv_entries = [e for e in entries if e[0] == "kv"]
    st.markdown(f"当前共 **{len(kv_entries)}** 个环境变量")

    # 编辑现有变量
    for kind, key, value in kv_entries:
        with st.container(border=True):
            col_a, col_b, col_c = st.columns([2, 3, 1])
            col_a.markdown(f"**{key}**")
            is_secret = any(s in key for s in ("TOKEN", "PASSWORD", "KEY", "SECRET"))
            new_val = col_b.text_input("值", value=value, key=f"env_edit_{key}",
                                       type="password" if is_secret else "default")
            if col_c.button("保存", key=f"env_save_{key}", use_container_width=True):
                ce.set_env(key, new_val.strip())
                wctx.invalidate()
                st.success(f"{key} 已保存")
                st.rerun()

    # 新增变量
    st.divider()
    st.subheader("➕ 新增环境变量")
    with st.form("new_env", clear_on_submit=True):
        n_key = st.text_input("变量名", placeholder="MY_VAR")
        n_val = st.text_input("值")
        if st.form_submit_button("添加"):
            if re_key_ok(n_key):
                ce.set_env(n_key.strip(), n_val.strip())
                wctx.invalidate()
                st.success(f"已添加 {n_key.strip()}")
                st.rerun()
            else:
                st.error("变量名仅允许字母、数字、下划线，且不能以数字开头")


def re_key_ok(key: str) -> bool:
    import re
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key.strip()))


def _effective_tab() -> None:
    st.subheader("📋 有效配置（只读）")
    st.caption("环境变量插值后的最终生效配置（密钥已打码）。云端排查问题时优先看这里。")
    try:
        eff = ce.effective_config()
        st.json(eff)
    except Exception as e:  # noqa: BLE001
        st.error(f"读取有效配置失败：{e}")


def render() -> None:
    st.title("⚙️ 配置中心")
    st.caption("所有修改实时写入项目配置文件（YAML 保注释、写前备份），核心代码无需改动。")

    tab_feeds, tab_llm, tab_sched, tab_channels, tab_env, tab_eff = st.tabs(
        ["📰 新闻源", "🤖 LLM 参数", "⏰ 调度", "📤 推送渠道", "🔑 环境变量", "📋 有效配置"])

    with tab_feeds:
        _feeds_tab()
    with tab_llm:
        _llm_tab()
    with tab_sched:
        _schedule_tab()
    with tab_channels:
        _channels_tab()
    with tab_env:
        _env_tab()
    with tab_eff:
        _effective_tab()
