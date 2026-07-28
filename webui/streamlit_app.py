"""Brompt Web UI — Streamlit-based interface for the Brompt Engine."""

import os
import sys
import json
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from brompt.core.engine import BromptEngine
from brompt.hooks import hooks_manager, LoggingHook, TimingHook
from brompt.observability import metrics, tracer
from brompt.core.template_engine import template_registry

st.set_page_config(
    page_title="Brompt Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- session state ----------------------------------------------------------

if "engine" not in st.session_state:
    st.session_state.engine = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "config_path" not in st.session_state:
    st.session_state.config_path = "agent.brompt.yaml"

# --- provider env var mapping -----------------------------------------------

PROVIDER_ENV_VARS = {
    "Gemini": "GEMINI_API_KEY",
    "OpenAI": "OPENAI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "Mistral": "MISTRAL_API_KEY",
    "Azure OpenAI": "AZURE_OPENAI_API_KEY",
    "Ollama": "OLLAMA_HOST",
    "LM Studio": "LM_STUDIO_HOST",
}


def _set_api_key(provider: str, key: str):
    for env_var in PROVIDER_ENV_VARS.values():
        os.environ.pop(env_var, None)
    env_var = PROVIDER_ENV_VARS.get(provider)
    if env_var and key:
        os.environ[env_var] = key


# --- sidebar ----------------------------------------------------------------

with st.sidebar:
    st.title("⚡ Brompt Engine")
    st.caption("Deterministic State-Driven LLM Orchestration")

    with st.expander("API Key", expanded=not bool(st.session_state.engine)):
        provider_sel = st.selectbox("Provider", list(PROVIDER_ENV_VARS.keys()), key="provider_sel")
        api_key = st.text_input("Key / Host", type="password", key="api_key_input",
                                help=f"Sets {PROVIDER_ENV_VARS.get(provider_sel, '')}")

    config_path = st.text_input("Config path", value=st.session_state.config_path)

    if st.button("🔄 Initialize Engine", use_container_width=True):
        _set_api_key(provider_sel, api_key)
        env_var = PROVIDER_ENV_VARS.get(provider_sel, "?")
        st.write(f"DEBUG: selected=`{provider_sel}`, env_var=`{env_var}`, value=`{os.environ.get(env_var, '')[:8]}...`")
        try:
            from brompt._providers_legacy import build_provider_from_env
            p = build_provider_from_env()
            st.write(f"DEBUG: build_provider_from_env() -> {type(p).__name__ if p else 'None'}")
            engine = BromptEngine(config_path)
            hooks_manager.register(LoggingHook())
            hooks_manager.register(TimingHook())
            st.session_state.engine = engine
            st.session_state.config_path = config_path
            provider_name = type(engine.provider).__name__ if engine.provider else "dry-run"
            st.success(f"Engine initialized: {provider_name}")
        except Exception as exc:
            st.error(f"Failed to initialize: {exc}")

    st.divider()

    st.subheader("Templates")
    template_names = template_registry.list()
    selected_template = st.selectbox("Select template", [""] + template_names)
    if selected_template:
        tpl = template_registry.get(selected_template)
        st.code(tpl.source[:500] if tpl else "", language="text")

    st.divider()

    st.subheader("System")
    if st.button("Clear History", use_container_width=True):
        st.session_state.messages = []
        if st.session_state.engine:
            st.session_state.engine.memory.clear()
        st.rerun()

# --- main panel -------------------------------------------------------------

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("💬 Chat")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Type your message..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        if not st.session_state.engine:
            _set_api_key(
                st.session_state.get("provider_sel", "Gemini"),
                st.session_state.get("api_key_input", ""),
            )
            try:
                engine = BromptEngine(st.session_state.config_path)
                hooks_manager.register(LoggingHook())
                hooks_manager.register(TimingHook())
                st.session_state.engine = engine
            except Exception as exc:
                st.error(f"Cannot auto-init engine: {exc}")
                st.stop()

        with st.chat_message("assistant"):
            with st.spinner("Processing..."):
                try:
                    query, ctx = hooks_manager.before_execute(prompt, None)
                    result = st.session_state.engine.execute(query, ctx)
                    result = hooks_manager.after_execute(result)
                    if result.is_secure:
                        response = result.data.get("llm_response", "")
                        if response:
                            st.markdown(response)
                            st.session_state.messages.append({"role": "assistant", "content": response})
                        else:
                            st.info("No response (dry-run mode)")
                    else:
                        st.error(f"Error: {result.error_message}")
                except Exception as exc:
                    st.error(f"Error: {exc}")

with col2:
    st.subheader("📊 Metrics")

    if st.session_state.engine:
        engine = st.session_state.engine
        provider_name = type(engine.provider).__name__ if engine.provider else "None"

        with st.expander("Engine Status", expanded=True):
            st.metric("Provider", provider_name)
            st.metric("State ID", engine.state_id[:16])
            st.metric("History", len(engine.memory.get_history()))
            st.metric("Audit Entries", len(engine.audit.read_all()))

        with st.expander("Observability", expanded=False):
            snap = metrics.snapshot()
            st.json(snap)

        with st.expander("Audit Log", expanded=False):
            entries = engine.audit.read_all()
            if entries:
                st.json(entries[-10:])
            else:
                st.caption("No entries")

        with st.expander("Templates", expanded=False):
            names = template_registry.list()
            for name in names:
                st.caption(f"• {name}")
    else:
        st.info("Initialize the engine to see metrics.")


if __name__ == "__main__":
    pass
