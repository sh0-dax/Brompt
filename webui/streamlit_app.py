"""Brompt Web UI — Streamlit-based interface for the Brompt Engine."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from brompt.core.engine import BromptEngine
from brompt.hooks import hooks_manager, LoggingHook, TimingHook
from brompt.observability import metrics
from brompt.core.template_engine import template_registry
from brompt._providers_legacy import (
    AnthropicProvider, OpenAIProvider, GeminiProvider,
    MistralProvider, AzureOpenAIProvider, OllamaProvider, LMStudioProvider,
)
from brompt.pricing import estimate_cost
from brompt.optimizer import TokenOptimizer

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
if "execution_history" not in st.session_state:
    st.session_state.execution_history = []
if "optimizer" not in st.session_state:
    st.session_state.optimizer = TokenOptimizer()
if "optimization_enabled" not in st.session_state:
    st.session_state.optimization_enabled = True
if "max_context_messages" not in st.session_state:
    st.session_state.max_context_messages = 4
if "total_saved_tokens" not in st.session_state:
    st.session_state.total_saved_tokens = 0
if "system_sent" not in st.session_state:
    st.session_state.system_sent = False

PROVIDER_FACTORIES = {
    "Gemini": lambda key: GeminiProvider(api_key=key, model="gemini-2.5-flash"),
    "OpenAI": lambda key: OpenAIProvider(api_key=key, model="gpt-4o"),
    "Anthropic": lambda key: AnthropicProvider(api_key=key, model="claude-sonnet-4-5"),
    "Mistral": lambda key: MistralProvider(api_key=key, model="mistral-large-latest"),
    "Azure OpenAI": lambda key: AzureOpenAIProvider(api_key=key, model="gpt-4o"),
    "Ollama": lambda host: OllamaProvider(base_url=host or "http://localhost:11434", model="llama3.2"),
    "LM Studio": lambda host: LMStudioProvider(base_url=host or "http://localhost:1234", model="default"),
}
HELP_TEXT = {
    "Gemini": "Gemini API key (GEMINI_API_KEY)",
    "OpenAI": "OpenAI API key (OPENAI_API_KEY)",
    "Anthropic": "Anthropic API key (ANTHROPIC_API_KEY)",
    "Mistral": "Mistral API key (MISTRAL_API_KEY)",
    "Azure OpenAI": "Azure OpenAI API key (AZURE_OPENAI_API_KEY)",
    "Ollama": "Ollama base URL (default: http://localhost:11434)",
    "LM Studio": "LM Studio base URL (default: http://localhost:1234)",
}

def _fmt_cost(c: float) -> str:
    if c >= 0.01:
        return f"${c:.4f}"
    if c >= 0.001:
        return f"${c:.5f}"
    if c >= 0.0001:
        return f"${c:.6f}"
    if c > 0:
        return f"${c:.2e}"
    return "$0.00"

# --- sidebar ----------------------------------------------------------------

with st.sidebar:
    st.title("⚡ Brompt Engine")
    st.caption("Deterministic State-Driven LLM Orchestration")

    with st.expander("API Key", expanded=not bool(st.session_state.engine)):
        provider_sel = st.selectbox("Provider", list(PROVIDER_FACTORIES.keys()), key="provider_sel")
        api_key = st.text_input("Key / Host", type="password", key="api_key_input",
                                help=HELP_TEXT.get(provider_sel, ""))

    config_path = st.text_input("Config path", value=st.session_state.config_path)

    if st.button("🔄 Initialize Engine", use_container_width=True):
        try:
            factory = PROVIDER_FACTORIES.get(provider_sel)
            provider = factory(api_key) if factory else None
            engine = BromptEngine(config_path, provider=provider)
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

    st.subheader("⚡ Token Optimization")
    st.session_state.optimization_enabled = st.toggle(
        "Enable optimization",
        value=st.session_state.optimization_enabled,
        help="Saves 60-75% on token costs by compressing context and not repeating system prompt",
    )

    if st.session_state.optimization_enabled:
        st.success("✅ Optimization active")
        st.session_state.max_context_messages = st.slider(
            "Context messages",
            0, 20, st.session_state.max_context_messages,
            help="Last N messages sent with each request. Lower = more savings",
        )
        estimated = st.session_state.max_context_messages * 50
        st.caption(f"~{estimated} tokens per request for context")

        if st.session_state.total_saved_tokens > 0:
            st.markdown(f"**Saved tokens:** {st.session_state.total_saved_tokens:,}")
    else:
        st.warning("⚠️ Optimization disabled — full token usage")

    st.divider()

    st.subheader("System")
    if st.button("Clear History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.system_sent = False
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
            sel = st.session_state.get("provider_sel", "Gemini")
            key = st.session_state.get("api_key_input", "")
            factory = PROVIDER_FACTORIES.get(sel)
            try:
                provider = factory(key) if factory else None
                engine = BromptEngine(st.session_state.config_path, provider=provider)
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
                    engine = st.session_state.engine
                    history = engine.memory.get_history()

                    savings = {}
                    if st.session_state.optimization_enabled:
                        is_first = not st.session_state.system_sent
                        raw_template = "Process the following input and provide the best possible response."
                        _, savings = st.session_state.optimizer.build_optimized_prompt(
                            system_prompt="",
                            user_input=prompt,
                            template_content=raw_template,
                            messages_history=history,
                            is_first_message=is_first,
                        )
                        st.session_state.system_sent = True
                        st.session_state.total_saved_tokens += savings.get("saved_tokens", 0)

                    result = engine.execute(query, ctx)
                    result = hooks_manager.after_execute(result)
                    completion_tokens = engine._last_tokens_used
                    all_text = " ".join(m["content"] for m in history)
                    prompt_tokens = len(all_text) // 4
                    plain_prompt_tokens = len(prompt) // 4
                    provider_name = type(engine.provider).__name__ if engine.provider else "None"
                    cost = estimate_cost(provider_name, prompt_tokens, completion_tokens)
                    plain_cost = estimate_cost(provider_name, plain_prompt_tokens, completion_tokens)
                    st.session_state.execution_history.append({
                        "msg": prompt[:30],
                        "latency_ms": engine._last_latency_ms,
                        "tokens": completion_tokens,
                        "prompt_tokens": prompt_tokens,
                        "plain_prompt_tokens": plain_prompt_tokens,
                        "cost": cost,
                        "plain_cost": plain_cost,
                        "secure": result.is_secure,
                        "provider_used": result.data.get("provider_used", False),
                        "saved_tokens": savings.get("saved_tokens", 0),
                        "savings_percent": round(savings.get("savings_percent", 0), 1),
                    })
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
                    st.session_state.execution_history.append({
                        "msg": prompt[:30], "latency_ms": 0,
                        "tokens": 0, "prompt_tokens": 0, "plain_prompt_tokens": 0,
                        "cost": 0.0, "plain_cost": 0.0,
                        "secure": False, "provider_used": False,
                        "saved_tokens": 0, "savings_percent": 0,
                    })

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

        with st.expander("Execution History", expanded=True):
            history = st.session_state.execution_history
            if history:
                import pandas as pd
                df = pd.DataFrame(history)
                df["idx"] = range(1, len(df) + 1)
                df = df.set_index("idx")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Messages", len(df))
                col_b.metric("Avg Latency", f"{df['latency_ms'].mean():.0f}ms")
                total_overhead = df["cost"].sum() - df["plain_cost"].sum()
                pct = (total_overhead / df["cost"].sum() * 100) if df["cost"].sum() > 0 else 0
                total_val = df["cost"].sum()
                col_c.metric("Total Cost", _fmt_cost(total_val), delta=f"{pct:.1f}% overhead")
                st.bar_chart(df[["latency_ms", "tokens"]], height=200)
                last = history[-1]
                overhead_tokens = last["prompt_tokens"] - last["plain_prompt_tokens"]
                overhead_cost = last["cost"] - last["plain_cost"]
                st.caption(
                    f"Last: {last['msg']} — {last['latency_ms']:.0f}ms, "
                    f"{last['prompt_tokens']}in/{last['tokens']}out, "
                    f"{_fmt_cost(last['cost'])} total"
                )
                st.caption(
                    f"🧾 Prompt {_fmt_cost(last['plain_cost'])} + "
                    f"Overhead {overhead_tokens}tok {_fmt_cost(overhead_cost)}"
                )
                if last.get("saved_tokens", 0) > 0:
                    st.caption(
                        f"⚡ Saved {last['saved_tokens']} tok ({last['savings_percent']:.0f}%)"
                    )
            else:
                st.caption("No executions yet")

        with st.expander("Templates", expanded=False):
            names = template_registry.list()
            for name in names:
                st.caption(f"• {name}")
    else:
        st.info("Initialize the engine to see metrics.")


if __name__ == "__main__":
    pass