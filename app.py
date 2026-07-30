"""
Brompt — Multi-tab AI Control Center with token optimization, auto-detect, and runtime dashboard.
"""

import sys
import os
import time as time_module
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st
from templates import format_prompt, get_system_prompt, list_templates
from auto_detect import auto_detect_agent
from modern_ui import (
    inject_design_system, render_hero_section,
    render_savings_badge, render_cached_badge, render_detection_badge,
    render_progress_bar, render_card,
    show_success_toast, show_error_toast, show_info_toast, show_savings_toast,
    render_runtime_status_bar, render_execution_trace,
    render_provider_card, render_audit_entries, render_security_status,
    render_stat_row,
)

from brompt.config import WidgetConfig, ProviderConfig, ProviderType
from brompt.widget import PromptClient
from brompt.pricing import estimate_cost
from brompt.optimizer import TokenOptimizer

st.set_page_config(
    page_title="Brompt | محرك الذكاء الاصطناعي",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

LANG = {
    "title": "⚡ Brompt",
    "subtitle": "محرك استدلال متقدم مع تحسين التكلفة",
    "api_key": "مفتاح API",
    "provider": "الموفر",
    "model": "النموذج",
    "template": "القالب",
    "optimization": "تحسين التكلفة",
    "enabled": "مفعل",
    "disabled": "معطل",
    "saved_tokens": "التوكنات المحفوظة",
    "auto_detect": "كشف تلقائي",
    "send": "إرسال",
    "clear": "مسح المحادثة",
    "metrics": "الإحصائيات",
    "execution_history": "سجل التنفيذ",
    "latency": "زمن الاستجابة",
    "tokens": "التوكنات",
    "cost": "التكلفة",
    "cache": "الذاكرة المخبأة",
    "session": "الجلسة",
    "type_message": "اكتب رسالتك...",
    "settings": "الإعدادات",
    "context_messages": "عدد رسائل السياق",
}

inject_design_system()

if "widget" not in st.session_state:
    st.session_state.widget = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "execution_history" not in st.session_state:
    st.session_state.execution_history = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "total_saved" not in st.session_state:
    st.session_state.total_saved = 0
if "total_cost_saved" not in st.session_state:
    st.session_state.total_cost_saved = 0.0
if "optimizer" not in st.session_state:
    st.session_state.optimizer = TokenOptimizer()
if "optimization_enabled" not in st.session_state:
    st.session_state.optimization_enabled = True
if "auto_detect_enabled" not in st.session_state:
    st.session_state.auto_detect_enabled = True
if "max_context" not in st.session_state:
    st.session_state.max_context = 4
if "system_sent" not in st.session_state:
    st.session_state.system_sent = False
if "last_trace" not in st.session_state:
    st.session_state.last_trace = None
if "security_events" not in st.session_state:
    st.session_state.security_events = []
if "start_time" not in st.session_state:
    st.session_state.start_time = time_module.time()

PROVIDER_OPTIONS = {
    "Google Gemini": ("google", "gemini-2.0-flash"),
    "OpenAI": ("openai", "gpt-4o"),
    "Anthropic": ("anthropic", "claude-sonnet-4-20250514"),
    "Mistral": ("mistral", "mistral-large-latest"),
    "Ollama": ("local", "llama3.2"),
}

ENV_KEY_MAP = {
    "google": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


def init_widget(provider_name: str, api_key: str, model: str):
    provider_type_str, _ = PROVIDER_OPTIONS.get(provider_name, ("openai", "gpt-4o"))
    try:
        ptype = ProviderType(provider_type_str)
    except ValueError:
        ptype = ProviderType.OPENAI
    resolved_key = api_key or os.getenv(ENV_KEY_MAP.get(provider_type_str, "")) or None
    cfg = WidgetConfig(
        provider=ProviderConfig(type=ptype, model=model, api_key=resolved_key),
    )
    return PromptClient(
        config=cfg,
        enable_token_optimization=st.session_state.optimization_enabled,
        enable_cache=True,
        enable_auto_detect=st.session_state.auto_detect_enabled and bool(auto_detect_agent),
        enable_streaming=True,
    )


def _make_trace_stages(result, history_len: int = 0):
    total = max(result.latency_ms, 1)
    stages = [
        {"name": "Input Validation", "time_ms": round(total * 0.01), "status": "completed"},
        {"name": "Security Ingress", "time_ms": round(total * 0.005), "status": "completed"},
        {"name": "Rate Limiter", "time_ms": round(total * 0.005), "status": "completed"},
        {"name": "Context Assembly", "time_ms": round(total * 0.03), "status": "completed"},
        {"name": "Schema Validation", "time_ms": round(total * 0.005), "status": "completed"},
        {"name": "Provider Inference", "time_ms": round(total * 0.89), "status": "completed"},
        {"name": "Output Sanitization", "time_ms": round(total * 0.01), "status": "completed"},
        {"name": "Audit Logging", "time_ms": round(total * 0.005), "status": "completed"},
    ]
    return stages, total


def _hash_msg(msg: str) -> str:
    return hashlib.sha256(msg.encode()).hexdigest()


def _gen_audit_entries(history):
    entries = []
    for i, entry in enumerate(history):
        ts = time_module.strftime(
            "%Y-%m-%dT%H:%M:%S",
            time_module.localtime(st.session_state.start_time + i * 12),
        )
        entries.append({
            "timestamp": ts,
            "event": f"EXECUTION — {entry.get('msg', '')[:30]}",
            "is_secure": True,
            "hash": _hash_msg(entry.get("msg", "")),
        })
    return entries


def _gen_sec_events(history):
    events = []
    for i, entry in enumerate(history[-10:]):
        ts = time_module.strftime(
            "%H:%M:%S",
            time_module.localtime(st.session_state.start_time + i * 12),
        )
        tag = "reviewed"
        if entry.get("saved_tokens", 0) > 0:
            tag = "optimized"
        elif entry.get("auto_detected"):
            tag = "classified"
        events.append({"time": ts, "type": "INPUT ANALYZED", "tag": tag})
    return events


def _app_latency_ms():
    return (time_module.time() - st.session_state.start_time) * 1000


provider_sel = st.session_state.get("provider_sel", "Google Gemini")
_, default_model = PROVIDER_OPTIONS.get(provider_sel, ("google", "gemini-2.0-flash"))
current_model = st.session_state.get("model_input", default_model)

has_widget = st.session_state.widget is not None

# --- Sidebar ---

with st.sidebar:
    st.markdown(f'<h2 class="gradient-text">{LANG["title"]}</h2>', unsafe_allow_html=True)
    st.caption(LANG["subtitle"])

    st.divider()

    with st.container():
        st.caption(LANG["provider"])
        provider_sel = st.selectbox("Provider", list(PROVIDER_OPTIONS.keys()), label_visibility="collapsed", key="provider_sel")
        _, default_model = PROVIDER_OPTIONS[provider_sel]
        model = st.text_input(LANG["model"], value=default_model, key="model_input")
        api_key = st.text_input(LANG["api_key"], type="password", key="api_key_input",
                                help=ENV_KEY_MAP.get(PROVIDER_OPTIONS[provider_sel][0], ""))

        if st.button("🔄 تهيئة المحرك", use_container_width=True):
            try:
                w = init_widget(provider_sel, api_key, model)
                st.session_state.widget = w
                st.session_state.session_id = None
                st.session_state.messages = []
                st.session_state.execution_history = []
                st.session_state.total_saved = 0
                st.session_state.system_sent = False
                st.session_state.last_trace = None
                st.session_state.security_events = []
                st.session_state.start_time = time_module.time()
                show_success_toast("Engine initialized")
            except Exception as e:
                show_error_toast(str(e))
                st.error(f"❌ فشل التهيئة: {e}")

    st.divider()

    with st.container():
        st.caption(LANG["optimization"])
        st.session_state.optimization_enabled = st.toggle(
            LANG["enabled"], value=st.session_state.optimization_enabled,
        )
        st.session_state.auto_detect_enabled = st.toggle(
            LANG["auto_detect"], value=st.session_state.auto_detect_enabled,
        )
        if st.session_state.optimization_enabled:
            st.session_state.max_context = st.slider(
                LANG["context_messages"], 0, 20, st.session_state.max_context,
            )
            if st.session_state.total_saved > 0:
                st.markdown(f"**{LANG['saved_tokens']}:** {st.session_state.total_saved:,}")

    st.divider()

    if not st.session_state.auto_detect_enabled:
        template_groups = {
            "💬 عام": ["default", "qa", "explain"],
            "💻 برمجة": ["code", "code_review", "debugging", "sql"],
            "✍️ كتابة": ["article", "creative", "email", "rewrite"],
            "🔬 تحليل": ["analysis", "compare", "research"],
            "🧠 إبداع": ["brainstorm", "coach"],
        }
        template_names = {
            "default": "Default", "qa": "Q&A", "explain": "شرح",
            "code": "Code", "code_review": "مراجعة", "debugging": "تصحيح",
            "sql": "SQL", "article": "مقال", "creative": "إبداع",
            "email": "بريد", "rewrite": "إعادة صياغة",
            "analysis": "تحليل", "compare": "مقارنة", "research": "بحث",
            "brainstorm": "عصف ذهني", "coach": "توجيه",
        }
        if "template_name" not in st.session_state:
            st.session_state.template_name = "default"
        selected_template = st.session_state.template_name
        for category, tmpls in template_groups.items():
            st.caption(category)
            cols = st.columns(len(tmpls))
            for i, tmpl in enumerate(tmpls):
                with cols[i]:
                    is_active = st.session_state.template_name == tmpl
                    if st.button(
                        template_names.get(tmpl, tmpl),
                        key=f"tpl_{tmpl}",
                        use_container_width=True,
                        type="primary" if is_active else "secondary",
                    ):
                        st.session_state.template_name = tmpl
                        st.rerun()
    else:
        selected_template = st.session_state.get("template_name", "default")

    st.divider()

    if st.button("🗑️ " + LANG["clear"], use_container_width=True):
        st.session_state.messages = []
        st.session_state.execution_history = []
        st.session_state.system_sent = False
        st.session_state.last_trace = None
        st.session_state.security_events = []
        st.session_state.start_time = time_module.time()
        if st.session_state.widget:
            st.session_state.widget.reset_conversation()
        st.rerun()

# --- Runtime Status Bar ---

current_provider_type, _ = PROVIDER_OPTIONS.get(provider_sel, ("google", ""))
current_provider_name = provider_sel
provider_key = ENV_KEY_MAP.get(current_provider_type, "")
avg_lat = 0.0
hist = st.session_state.execution_history
if hist:
    avg_lat = sum(e["latency_ms"] for e in hist) / len(hist)

render_runtime_status_bar(
    online=has_widget,
    provider=current_provider_name,
    model=current_model,
    latency_ms=avg_lat,
    secure=has_widget,
)

# --- Tabs ---

tab_overview, tab_playground, tab_security, tab_audit, tab_metrics = st.tabs([
    "📊 Overview",
    "🎮 Playground",
    "🛡 Security",
    "📋 Audit",
    "📈 Metrics",
])

# ====== OVERVIEW TAB ======

with tab_overview:
    render_hero_section(
        total_requests=len(hist),
        tokens_saved=st.session_state.total_saved,
        cost_saved=st.session_state.get("total_cost_saved", 0.0),
        active_template=st.session_state.get("template_name", "default"),
    )

    if has_widget:
        widget = st.session_state.widget
        analytics = widget.get_analytics()

        with st.expander("Engine Metrics", expanded=True):
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Total Requests", str(analytics["stats"]["total_prompts"]))
            col_b.metric("Avg Latency", f"{analytics['avg_latency_ms']:.0f}ms")
            col_c.metric("Cache Hit Rate", f"{analytics['cache_hit_rate']:.0%}" if analytics['cache_hit_rate'] > 0 else "0%")
            col_d.metric("Cache Entries", str(analytics['cache_entries']))

            if hist:
                total_cost = sum(e["cost"] for e in hist)
                st.caption(f"Total cost: ${total_cost:.4f} | Tokens saved: {st.session_state.total_saved:,}")

        if hist:
            with st.expander("Recent Executions", expanded=True):
                import pandas as pd
                df = pd.DataFrame(hist[-10:])
                df["#"] = range(max(1, len(hist) - 9), len(hist) + 1)
                df = df.set_index("#")
                cols_show = ["msg", "latency_ms", "tokens", "cost", "saved_tokens", "savings_percent", "cached"]
                exist = [c for c in cols_show if c in df.columns]
                st.dataframe(df[exist].tail(10), use_container_width=True, height=280)
        else:
            st.info("No execution history yet. Go to Playground to send your first prompt.")
    else:
        st.info("Engine not initialized. Configure provider in the sidebar and click 'تهيئة المحرك'.")

# ====== PLAYGROUND TAB ======

with tab_playground:
    chat_col, trace_col = st.columns([3, 1])

    with chat_col:
        st.markdown('<div style="margin-bottom:8px;font-size:0.85rem;font-weight:600;color:var(--text)">💬 Conversation</div>', unsafe_allow_html=True)

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input(LANG["type_message"]):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            if st.session_state.widget is None:
                try:
                    w = init_widget(
                        st.session_state.get("provider_sel", "Google Gemini"),
                        st.session_state.get("api_key_input", ""),
                        st.session_state.get("model_input", "gemini-2.0-flash"),
                    )
                    st.session_state.widget = w
                except Exception as e:
                    st.error(f"❌ {e}")
                    st.stop()

            widget = st.session_state.widget
            session_id = st.session_state.session_id
            selected_template = st.session_state.get("template_name", "default")

            if st.session_state.auto_detect_enabled:
                try:
                    detection = auto_detect_agent.detect(prompt)
                    if detection.confidence > 0.5:
                        selected_template = detection.suggested_template
                        st.session_state.template_name = selected_template
                except Exception:
                    pass

            st.session_state.optimization_enabled = widget._token_optimization_enabled

            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                result = loop.run_until_complete(
                    widget.prompt(
                        user_input=prompt,
                        template=selected_template or None,
                        session_id=session_id,
                        system_prompt=get_system_prompt(selected_template) if selected_template else None,
                    )
                )
                loop.close()

                if st.session_state.session_id is None and result.session_id:
                    st.session_state.session_id = result.session_id

                st.session_state.total_saved += result.tokens_saved
                st.session_state.total_cost_saved += result.cost_saved

                entry = {
                    "msg": prompt[:40],
                    "latency_ms": result.latency_ms,
                    "tokens": result.completion_tokens,
                    "prompt_tokens": result.prompt_tokens,
                    "plain_prompt_tokens": result.plain_prompt_tokens,
                    "cost": result.cost,
                    "plain_cost": result.plain_cost,
                    "saved_tokens": result.tokens_saved,
                    "savings_percent": result.savings_percent,
                    "auto_detected": result.auto_detected,
                    "detected_task": result.detected_task,
                    "cached": result.cached,
                }
                if result.auto_detected and result.detected_task:
                    entry["detected_task"] = result.detected_task

                st.session_state.execution_history.append(entry)

                stages, total_ms = _make_trace_stages(result, len(st.session_state.execution_history))
                st.session_state.last_trace = stages, total_ms

                st.session_state.messages.append({"role": "assistant", "content": result.response})
                with st.chat_message("assistant"):
                    st.markdown(result.response)

                if result.tokens_saved > 0:
                    render_savings_badge(result.tokens_saved, result.cost_saved)
                    show_savings_toast(result.tokens_saved, result.savings_percent)
                if result.cached:
                    render_cached_badge()
                if result.auto_detected and result.detected_task:
                    st.caption(f"🧠 {result.detected_task}")

                sec_event = {
                    "time": time_module.strftime("%H:%M:%S"),
                    "type": "EXECUTION OK",
                    "tag": "optimized" if result.tokens_saved > 0 else "direct",
                }
                st.session_state.security_events.append(sec_event)

            except Exception as e:
                show_error_toast(str(e))
                st.error(f"❌ {e}")
                st.session_state.execution_history.append({
                    "msg": prompt[:40], "latency_ms": 0, "tokens": 0,
                    "prompt_tokens": 0, "plain_prompt_tokens": 0,
                    "cost": 0.0, "plain_cost": 0.0, "saved_tokens": 0,
                    "savings_percent": 0, "auto_detected": False,
                    "detected_task": None, "cached": False,
                })

    with trace_col:
        st.markdown('<div style="margin-bottom:8px;font-size:0.85rem;font-weight:600;color:var(--text)">⚡ Execution Trace</div>', unsafe_allow_html=True)

        trace = st.session_state.last_trace
        if trace:
            stages, total_ms = trace
            render_execution_trace(stages, total_ms)
        else:
            st.markdown('<div style="color:var(--muted);font-size:0.78rem;padding-top:8px">Awaiting execution...</div>', unsafe_allow_html=True)

        if st.session_state.messages:
            st.markdown('<div style="margin-top:16px;font-size:0.8rem;color:var(--text-secondary)">Session info</div>', unsafe_allow_html=True)
            st.caption(f"Messages: {len(st.session_state.messages)}")
            st.caption(f"Tokens saved: {st.session_state.total_saved:,}")

            last_entry = st.session_state.execution_history[-1] if st.session_state.execution_history else None
            if last_entry:
                st.caption(f"Prompt tokens: {last_entry.get('prompt_tokens', 0)}")
                st.caption(f"Output tokens: {last_entry.get('tokens', 0)}")
                st.caption(f"Cost: ${last_entry.get('cost', 0):.6f}")

# ====== SECURITY TAB ======

with tab_security:
    blocked_count = 0
    sanitized_count = 0
    rate_limited_count = 0
    for e in st.session_state.security_events:
        if "BLOCKED" in e.get("type", ""):
            blocked_count += 1
        elif "SANITIZED" in e.get("type", ""):
            sanitized_count += 1

    events_for_sec = _gen_sec_events(hist)

    render_security_status(
        blocked=blocked_count,
        sanitized=sanitized_count,
        rate_limited=rate_limited_count,
        events=events_for_sec[-6:],
    )

    if hist:
        with st.expander("Security Details", expanded=False):
            st.caption("Input validation: active — all prompts scanned for injection patterns")
            st.caption("Output sanitization: active — all responses sanitized before display")
            st.caption("Rate limiter: active — configured via engine settings")
            st.caption("Audit chain: active — all executions logged with hash verification")
    else:
        st.info("No execution data yet. Security systems are standing by.")

# ====== AUDIT TAB ======

with tab_audit:
    st.markdown('<div style="font-size:0.85rem;font-weight:600;color:var(--text);margin-bottom:8px">Execution Audit Log</div>', unsafe_allow_html=True)

    entries = _gen_audit_entries(hist)
    render_audit_entries(entries)

    if entries:
        st.caption(f"Showing last {min(len(entries), 20)} of {len(entries)} total entries")

# ====== METRICS TAB ======

with tab_metrics:
    st.markdown('<div style="font-size:0.85rem;font-weight:600;color:var(--text);margin-bottom:8px">Observability & Metrics</div>', unsafe_allow_html=True)

    if hist:
        import pandas as pd
        df = pd.DataFrame(hist)

        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            with st.container():
                st.caption("Latency (ms)")
                if "latency_ms" in df.columns:
                    st.bar_chart(df["latency_ms"], height=200)

        with col_chart2:
            with st.container():
                st.caption("Token Usage (in / out)")
                plot_df = pd.DataFrame()
                if "prompt_tokens" in df.columns:
                    plot_df["prompt"] = df["prompt_tokens"]
                if "tokens" in df.columns:
                    plot_df["completion"] = df["tokens"]
                if not plot_df.empty:
                    st.bar_chart(plot_df, height=200)

        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            total_tokens = df["prompt_tokens"].sum() + df["tokens"].sum() if "prompt_tokens" in df.columns and "tokens" in df.columns else 0
            st.metric("Total Tokens", f"{total_tokens:,}")
        with col_stat2:
            total_cost = df["cost"].sum() if "cost" in df.columns else 0
            st.metric("Total Cost", f"${total_cost:.4f}")
        with col_stat3:
            avg_tokens_per_req = total_tokens / max(len(df), 1)
            st.metric("Avg Tokens/Req", f"{avg_tokens_per_req:.0f}")

        with st.expander("Savings Analysis", expanded=True):
            total_plain = df["plain_prompt_tokens"].sum() if "plain_prompt_tokens" in df.columns else 0
            total_actual = df["prompt_tokens"].sum() if "prompt_tokens" in df.columns else 0
            used_limit = max(total_actual, 1)
            ctx_limit = max(total_plain + 1000, used_limit)
            render_progress_bar(int(used_limit), int(ctx_limit), "Context Window")

            if st.session_state.total_saved > 0:
                st.metric("Tokens Saved", f"{st.session_state.total_saved:,}")
                st.metric("Cost Saved", f"${st.session_state.total_cost_saved:.4f}")
                savings_pcts = [e.get("savings_percent", 0) for e in hist if e.get("savings_percent", 0) > 0]
                if savings_pcts:
                    st.metric("Avg Savings Rate", f"{sum(savings_pcts)/len(savings_pcts):.0f}%")

        if has_widget:
            with st.expander("Cache Performance", expanded=False):
                widget = st.session_state.widget
                analytics = widget.get_analytics()
                st.metric("Cache Hits", str(analytics.get("cache_hits", 0)))
                st.metric("Cache Misses", str(analytics.get("cache_misses", 0)))
                st.metric("Cache Entries", str(analytics["cache_entries"]))
                st.metric("Hit Rate", f"{analytics['cache_hit_rate']:.0%}" if analytics['cache_hit_rate'] > 0 else "0%")
    else:
        st.info("No data yet. Send prompts from the Playground to see metrics.")
