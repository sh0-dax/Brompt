"""
Brompt — Arabic Web UI with token optimization, auto-detect, and modern glassmorphism design.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st
from templates import format_prompt, get_system_prompt, list_templates
from auto_detect import auto_detect_agent
from modern_ui import (
    inject_design_system, render_hero_section,
    render_savings_badge, render_cached_badge, render_detection_badge,
    render_progress_bar, render_card,
    show_savings_toast, show_error_toast, show_info_toast,
)

from brompt.config import WidgetConfig, ProviderConfig, ProviderType
from brompt.widget import BromptWidget
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
    cfg = WidgetConfig(
        provider=ProviderConfig(type=ptype, model=model, api_key=api_key or os.getenv(ENV_KEY_MAP.get(provider_type_str, ""))),
    )
    return BromptWidget(
        config=cfg,
        enable_token_optimization=st.session_state.optimization_enabled,
        enable_cache=True,
        enable_auto_detect=st.session_state.auto_detect_enabled and bool(auto_detect_agent),
        enable_streaming=True,
    )


# --- Hero ---

render_hero_section(
    total_requests=len(st.session_state.execution_history),
    tokens_saved=st.session_state.total_saved,
    cost_saved=st.session_state.get("total_cost_saved", 0.0),
    active_template=st.session_state.get("template_name", "default"),
)

# --- Sidebar ---

with st.sidebar:
    st.markdown(f'<h2 class="gradient-text">{LANG["title"]}</h2>', unsafe_allow_html=True)
    st.caption(LANG["subtitle"])

    st.divider()

    with st.container():
        st.caption(LANG["provider"])
        provider_sel = st.selectbox("", list(PROVIDER_OPTIONS.keys()), label_visibility="collapsed", key="provider_sel")
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
        if st.session_state.widget:
            st.session_state.widget.reset_conversation()
        st.rerun()


# --- Main Panel ---

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("💬 المحادثة")

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

        if st.session_state.auto_detect_enabled:
            detection = auto_detect_agent.detect(prompt)
            if detection.confidence > 0.5:
                selected_template = detection.suggested_template
                st.session_state.template_name = selected_template
                render_detection_badge(
                    task=detection.task_type.value if hasattr(detection.task_type, 'value') else str(detection.task_type),
                    model=getattr(detection.suggested_model, 'model', ''),
                    template=detection.suggested_template,
                    confidence=detection.confidence,
                )

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

            st.session_state.execution_history.append({
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
            })

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

with col2:
    st.subheader(f"📊 {LANG['metrics']}")

    if st.session_state.widget:
        widget = st.session_state.widget
        analytics = widget.get_analytics()
        history = st.session_state.execution_history

        with st.expander("المحرك", expanded=True):
            st.metric("الطلبات", str(analytics["stats"]["total_prompts"]))
            st.metric("متوسط الزمن", f"{analytics['avg_latency_ms']:.0f}ms")
            st.metric("الرسائل", str(len(st.session_state.messages)))

        with st.expander(LANG["execution_history"], expanded=True):
            if history:
                import pandas as pd
                df = pd.DataFrame(history)
                df["#"] = range(1, len(df) + 1)
                df = df.set_index("#")

                col_a, col_b, col_c = st.columns(3)
                col_a.metric("الطلبات", len(df))
                col_b.metric("متوسط الزمن", f"{df['latency_ms'].mean():.0f}ms")
                total_cost = df["cost"].sum()
                col_c.metric("التكلفة", f"${total_cost:.4f}" if total_cost > 0.001 else f"${total_cost:.6f}")

                st.bar_chart(df[["latency_ms", "tokens"]], height=200)

                last = history[-1]
                overhead_cost = last["cost"] - last["plain_cost"]
                st.caption(
                    f"آخر: {last['msg']} — {last['latency_ms']:.0f}ms, "
                    f"{last['prompt_tokens']}in/{last['tokens']}out, "
                    f"${last['cost']:.6f}"
                )
                if last["saved_tokens"] > 0:
                    st.caption(f"⚡ وفر {last['saved_tokens']} توكن ({last['savings_percent']:.0f}%)")
                if last.get("auto_detected"):
                    st.caption(f"🔍 الكشف: {last['detected_task']}")

            else:
                st.caption("لا يوجد سجل بعد")

        with st.expander(LANG["cache"], expanded=False):
            st.metric(LANG["saved_tokens"], f"{analytics['total_saved_tokens']:,}")
            st.metric("نسبة الإصابة", f"{analytics['cache_hit_rate']:.0%}" if analytics['cache_hit_rate'] > 0 else "0%")
            st.metric("الإدخالات", analytics['cache_entries'])

    else:
        st.info("قم بتهيئة المحرك من القائمة الجانبية")
