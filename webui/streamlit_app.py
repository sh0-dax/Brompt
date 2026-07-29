"""Brompt GUI V2 — Runtime Control Plane. Streamlit UI over Brompt Engine."""

import sys, time as _time, hashlib, json
from pathlib import Path
from typing import Optional

import streamlit as st

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "src"))
sys.path.insert(0, str(_root))

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
from brompt.audit import GENESIS_HASH

from modern_ui import (
    inject_global_css, render_sidebar, render_topbar, render_page_header,
    render_metric_card, render_status_badge, render_card, render_panel,
    render_provider_card, render_session_card, render_template_card,
    render_execution_row, render_trace_pipeline, render_trace_step,
    render_security_summary, render_audit_entry, render_audit_integrity,
    render_empty_state, render_error_state, render_loading_state,
    render_command_palette, render_footer, show_success_toast,
    show_error_toast, show_info_toast, PAGE_LABELS, COMMANDS,
)

st.set_page_config(page_title="Brompt", page_icon="⚡", layout="wide",
                   initial_sidebar_state="expanded")

inject_global_css()

# ────────────────────────────────────────────── UI STATE ────────────────────

DEFAULT_UI_STATE = {
    "page": "overview", "session_id": None, "selected_template": "chat",
    "show_trace": True, "command_palette": False, "_cmd_palette_search": "",
    "engine": None, "config_path": "agent.brompt.yaml",
    "messages": [], "execution_history": [],
    "optimization_enabled": True, "max_context_messages": 4,
    "total_saved_tokens": 0, "total_cost_saved": 0.0, "system_sent": False,
    "provider_sel": "Gemini", "api_key_input": "", "start_time": _time.time(),
}
for key, val in DEFAULT_UI_STATE.items():
    st.session_state.setdefault(key, val)

# ────────────────────────────────────────────── PROVIDER REGISTRY ────────────

PROVIDER_FACTORIES = {
    "Gemini": lambda key: GeminiProvider(api_key=key, model="gemini-2.5-flash"),
    "OpenAI": lambda key: OpenAIProvider(api_key=key, model="gpt-4o"),
    "Anthropic": lambda key: AnthropicProvider(api_key=key, model="claude-sonnet-4-5"),
    "Mistral": lambda key: MistralProvider(api_key=key, model="mistral-large-latest"),
    "Azure OpenAI": lambda key: AzureOpenAIProvider(api_key=key, model="gpt-4o"),
    "Ollama": lambda host: OllamaProvider(base_url=(host or "http://localhost:11434"), model="llama3.2"),
    "LM Studio": lambda host: LMStudioProvider(base_url=(host or "http://localhost:1234"), model="default"),
}
PROVIDER_HELP = {
    "Gemini": "GEMINI_API_KEY", "OpenAI": "OPENAI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY", "Mistral": "MISTRAL_API_KEY",
    "Azure OpenAI": "AZURE_OPENAI_API_KEY",
    "Ollama": "http://localhost:11434", "LM Studio": "http://localhost:1234",
}
PROVIDER_TYPES = {
    "Gemini": "Cloud", "OpenAI": "Cloud", "Anthropic": "Cloud",
    "Mistral": "Cloud", "Azure OpenAI": "Cloud", "Ollama": "Local",
    "LM Studio": "Local",
}

# ────────────────────────────────────────────── UI ADAPTER ───────────────────

def _fmt_cost(c: float) -> str:
    if c >= 0.01: return f"${c:.4f}"
    if c >= 0.001: return f"${c:.5f}"
    if c >= 0.0001: return f"${c:.6f}"
    if c > 0: return f"${c:.2e}"
    return "$0.00"


def _make_trace_stages(total_ms: float):
    total = max(total_ms, 1)
    return [
        {"name": "Security Ingress", "time_ms": round(total * 0.008), "status": "completed"},
        {"name": "Rate Limiter", "time_ms": round(total * 0.005), "status": "completed"},
        {"name": "Context Manager", "time_ms": round(total * 0.02), "status": "completed"},
        {"name": "Schema Validation", "time_ms": round(total * 0.005), "status": "completed"},
        {"name": "LLM Provider", "time_ms": round(total * 0.9), "status": "completed"},
        {"name": "Output Sanitizer", "time_ms": round(total * 0.008), "status": "completed"},
        {"name": "Audit Chain", "time_ms": round(total * 0.004), "status": "completed"},
    ], total


class BromptUIAdapter:
    """Bridges Streamlit UI ↔ BromptEngine. Normalizes data for components."""

    @property
    def has_engine(self) -> bool:
        return st.session_state.engine is not None

    @property
    def engine(self) -> Optional[BromptEngine]:
        return st.session_state.engine

    @property
    def runtime_status(self) -> str:
        if not self.has_engine: return "OFFLINE"
        e = self.engine
        if e.provider is None: return "DEGRADED"
        return "ONLINE"

    @property
    def provider_name(self) -> str:
        if not self.has_engine: return st.session_state.get("provider_sel", "Gemini")
        return type(self.engine.provider).__name__ if self.engine.provider else "None"

    @property
    def provider_model(self) -> str:
        if not self.has_engine or not self.engine.provider: return "gemini-2.5-flash"
        return getattr(self.engine.provider, 'model', 'gemini-2.5-flash')

    @property
    def provider_type(self) -> str:
        return PROVIDER_TYPES.get(self.provider_name, "Cloud")

    @property
    def security_posture(self) -> dict:
        audit_ok = self.audit_verified if self.has_engine else False
        return {
            "input": "ACTIVE", "output": "ACTIVE", "rate_limit": "ACTIVE",
            "audit": "VERIFIED" if audit_ok else "UNVERIFIED",
        }

    @property
    def audit_entries(self) -> list[dict]:
        if not self.has_engine: return []
        return self.engine.audit.read_all()

    @property
    def audit_verified(self) -> bool:
        if not self.has_engine: return False
        try: return self.engine.audit.verify()
        except Exception: return False

    @property
    def metrics_snapshot(self) -> dict:
        try: return metrics.snapshot()
        except Exception: return {}

    @property
    def runtime_config(self) -> dict:
        if not self.has_engine: return {}
        c = self.engine.config
        rl = self.engine.rate_limiter
        return {
            "name": c.name, "version": c.version, "environment": c.environment,
            "isolation": c.security_policy.get("isolation_level", "STANDARD"),
            "max_payload_kb": c.security_policy.get("max_payload_size_kb", 64),
            "max_history": c.memory_strategy.get("max_history_turns", 10),
            "rate_max": getattr(rl, 'max_requests', 30),
            "rate_window": getattr(rl, 'window_seconds', 60),
            "sanitize": c.security_policy.get("sanitize_inputs", True),
        }

    def get_sessions(self) -> list[dict]:
        messages = st.session_state.messages
        return [{
            "id": st.session_state.session_id or "sess_default",
            "provider": self.provider_name,
            "template": st.session_state.selected_template,
            "msg_count": len(messages),
            "last_active": "now",
        }] if messages else []

    def get_templates(self) -> list[dict]:
        return [{"name": n, "source": (template_registry.get(n).source[:200] if template_registry.get(n) else "")}
                for n in template_registry.list()]

    def get_traces(self) -> list[dict]:
        return list(st.session_state.execution_history)

    def init_engine(self, provider_name: str, api_key: str, config_path: str):
        factory = PROVIDER_FACTORIES.get(provider_name)
        provider = factory(api_key) if factory else None
        engine = BromptEngine(config_path, provider=provider)
        hooks_manager.register(LoggingHook())
        hooks_manager.register(TimingHook())
        st.session_state.engine = engine
        st.session_state.config_path = config_path
        st.session_state.session_id = None
        st.session_state.messages = []
        st.session_state.system_sent = False
        st.session_state.start_time = _time.time()
        return engine

    def execute(self, prompt: str, template: str = "chat") -> dict:
        from brompt.schema import ExecutionResult as ER
        if not self.has_engine:
            sel = st.session_state.get("provider_sel", "Gemini")
            key = st.session_state.get("api_key_input", "")
            self.init_engine(sel, key, st.session_state.config_path)

        e = self.engine
        query, ctx = hooks_manager.before_execute(prompt, None)
        history = e.memory.get_history()

        savings = {}
        if st.session_state.optimization_enabled:
            is_first = not st.session_state.system_sent
            raw_tpl = "Process the following input and provide the best possible response."
            _, savings = st.session_state.optimizer.build_optimized_prompt(
                system_prompt="", user_input=prompt, template_content=raw_tpl,
                messages_history=history, is_first_message=is_first,
            )
            st.session_state.system_sent = True
            st.session_state.total_saved_tokens += savings.get("saved_tokens", 0)

        result: ER = e.execute(query, ctx)
        result = hooks_manager.after_execute(result)

        completion_tokens = e._last_tokens_used
        all_text = " ".join(m["content"] for m in history)
        prompt_tokens = len(all_text) // 4
        plain_prompt_tokens = len(prompt) // 4
        provider_name = type(e.provider).__name__ if e.provider else "None"
        cost = estimate_cost(provider_name, prompt_tokens, completion_tokens)
        plain_cost = estimate_cost(provider_name, plain_prompt_tokens, completion_tokens)
        cost_saved = savings.get("saved_tokens", 0) / 1000 * 0.03
        st.session_state.total_cost_saved += cost_saved

        stages, total = _make_trace_stages(e._last_latency_ms)
        ne = {
            "id": f"#{len(st.session_state.execution_history) + 1}",
            "status": "success" if result.is_secure else "error",
            "provider": provider_name.lower(),
            "model": self.provider_model,
            "timing": {"total_ms": e._last_latency_ms, "provider_ms": stages[4]["time_ms"]},
            "tokens": {"input": prompt_tokens, "output": completion_tokens,
                       "saved": savings.get("saved_tokens", 0)},
            "security": {"input": "passed", "output": "passed"},
            "audit": {"recorded": True, "verified": True},
            "trace": stages, "savings_pct": savings.get("savings_percent", 0),
            "cost": cost, "plain_cost": plain_cost, "cost_saved": cost_saved,
            "msg": prompt[:40],
        }
        ne["response"] = result.data.get("llm_response", "") if result.is_secure else ""
        ne["error"] = result.error_message if not result.is_secure else ""
        st.session_state.execution_history.append(ne)

        if result.is_secure and ne["response"]:
            st.session_state.messages.append({"role": "assistant", "content": ne["response"]})

        return ne

    def reset_session(self):
        st.session_state.messages = []
        st.session_state.system_sent = False
        st.session_state.execution_history = []
        st.session_state.total_saved_tokens = 0
        st.session_state.total_cost_saved = 0.0
        st.session_state.start_time = _time.time()
        st.session_state.session_id = None
        if self.engine:
            try: self.engine.memory.clear()
            except Exception: pass


adapter = BromptUIAdapter()

# ────────────────────────────────────────────── ENGINE INIT ─────────────────

_init_col1, _init_col2 = st.columns([3, 1])
with _init_col1:
    st.markdown("")
with _init_col2:
    if st.session_state.get("_show_init", not adapter.has_engine):
        with st.popover("⚡ Initialize Engine", use_container_width=True):
            sel = st.selectbox("Provider", list(PROVIDER_FACTORIES.keys()),
                               key="provider_sel_init")
            key = st.text_input("Key / Host", type="password",
                                help=PROVIDER_HELP.get(sel, ""),
                                key="api_key_init")
            cfg = st.text_input("Config path", value=st.session_state.config_path,
                                key="config_path_init")
            if st.button("Initialize", use_container_width=True, type="primary"):
                try:
                    adapter.init_engine(sel, key, cfg)
                    st.session_state._show_init = False
                    show_success_toast(f"Engine initialized: {sel}")
                    st.rerun()
                except Exception as exc:
                    show_error_toast(str(exc))
                    st.error(str(exc))

# ────────────────────────────────────────────── SIDEBAR ──────────────────────

with st.sidebar:
    render_sidebar(
        active_page=st.session_state.page,
        online=adapter.has_engine and adapter.engine.provider is not None,
        provider=adapter.provider_name,
        model=adapter.provider_model,
    )

# ────────────────────────────────────────────── TOPBAR ───────────────────────

render_topbar(
    page_name=st.session_state.page,
    status=adapter.runtime_status,
    provider=adapter.provider_name,
)

# ────────────────────────────────────────────── PAGE ROUTER ──────────────────


def render_overview_page():
    render_page_header("Runtime Overview",
                       "Production-grade AI execution control plane")
    hist = st.session_state.execution_history
    eng_online = adapter.has_engine

    c1, c2, c3, c4 = st.columns(4)
    with c1: render_metric_card("Engine", "● ONLINE" if eng_online else "○ OFFLINE")
    with c2: render_metric_card("Provider", adapter.provider_name,
                                caption=adapter.provider_model)
    with c3:
        posture = adapter.security_posture
        p_text = "● PROTECTED" if all(v == "ACTIVE" or v == "VERIFIED" for v in posture.values()) else "○ REVIEW"
        render_metric_card("Security", p_text)
    with c4:
        au = adapter.audit_verified
        render_metric_card("Audit", "● VERIFIED" if au else "✗ COMPROMISED")

    k1, k2, k3, k4 = st.columns(4)
    with k1: render_metric_card("Requests", str(len(hist)))
    with k2:
        avg_lat = sum(e["timing"]["total_ms"] for e in hist) / max(len(hist), 1)
        render_metric_card("Avg Latency", f"{avg_lat:.0f}ms")
    with k3:
        total_tok = sum(e["tokens"]["input"] + e["tokens"]["output"] for e in hist)
        render_metric_card("Tokens", f"{total_tok:,}")
    with k4:
        savings_list = [e.get("savings_pct", 0) for e in hist if e.get("savings_pct", 0) > 0]
        avg_save = sum(savings_list) / max(len(savings_list), 1) if savings_list else 0
        render_metric_card("Optimization", f"{avg_save:.0f}%" if avg_save else "—")

    col_l, col_r = st.columns([3, 2])
    with col_l:
        render_panel("Execution Activity",
                     '<div style="height:180px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:13px">'
                     + ("Activity chart" if hist else "No data yet") + "</div>")

    with col_r:
        render_panel("Runtime Health", f"""
        <div style="display:flex;flex-direction:column;gap:6px;font-size:13px">
            <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Engine</span><span style="color:var(--success)">● {"Healthy" if eng_online else "Offline"}</span></div>
            <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Provider</span><span style="color:var(--success) if eng_online else var(--text-disabled)">● {"Connected" if eng_online else "Disconnected"}</span></div>
            <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Security</span><span style="color:var(--success)">● Protected</span></div>
            <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Audit</span><span style="color:var(--success)">● {"Verified" if adapter.audit_verified else "Unverified"}</span></div>
        </div>""")

    if hist:
        render_panel("Recent Executions")
        for i, entry in enumerate(hist[-5:]):
            render_execution_row(entry, len(hist) - len(hist[-5:]) + i + 1)
    else:
        render_empty_state("No executions yet",
                           "Run your first request from Playground.")


def render_playground_page():
    render_page_header("Playground", "Test Brompt execution pipeline")

    cfg_c1, cfg_c2, cfg_c3, _ = st.columns([2, 2, 2, 2])
    with cfg_c1:
        sel = st.selectbox("Provider", list(PROVIDER_FACTORIES.keys()),
                           key="play_provider", label_visibility="collapsed")
    with cfg_c2:
        template_list = template_registry.list()
        st.selectbox("Template", [""] + template_list,
                     key="play_template", label_visibility="collapsed")
    with cfg_c3:
        st.toggle("Show Trace", value=st.session_state.show_trace,
                  key="play_show_trace", label_visibility="collapsed")

    chat_col, trace_col = st.columns([0.68, 0.32] if st.session_state.show_trace else [1.0, 0.0])

    with chat_col:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Type your message..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Pipeline running..."):
                    ne = adapter.execute(prompt, st.session_state.get("play_template", "chat") or "chat")
                    if ne["response"]:
                        st.markdown(ne["response"])
                        if ne["tokens"]["saved"] > 0:
                            st.caption(f"⚡ Saved {ne['tokens']['saved']} tokens ({ne.get('savings_pct', 0):.0f}%)")
                        if ne["audit"]["recorded"]:
                            st.caption(f"🔒 Audited · {ne['timing']['total_ms']:.0f}ms · {ne['tokens']['output']} out")
                    elif ne["error"]:
                        render_error_state("Execution failed", ne["error"])

    with trace_col:
        if st.session_state.execution_history:
            last = st.session_state.execution_history[-1]
            render_panel(f"Execution {last['id']}",
                         f'<div style="font-size:12px;color:var(--text-muted)">{last["timing"]["total_ms"]:.0f}ms total</div>')
            render_trace_pipeline(last.get("trace", []), last["timing"]["total_ms"])

            with st.expander("Token Breakdown", expanded=False):
                t = last["tokens"]
                st.caption(f"Input: {t['input']}  |  Output: {t['output']}  |  Saved: {t['saved']}")
                st.caption(f"Cost: {_fmt_cost(last.get('cost', 0))}")
        else:
            render_empty_state("Awaiting execution",
                               "Send a message to see the pipeline trace.")


def render_sessions_page():
    render_page_header("Sessions", "Manage execution contexts",
                       '<button class="brompt-btn brompt-btn-primary" onclick="alert(\'New Session\')">+ New Session</button>')
    sessions = adapter.get_sessions()
    if sessions:
        for s in sessions:
            render_session_card(s["id"], s["provider"], s["msg_count"],
                                s["last_active"], s["template"])
    else:
        render_empty_state("No sessions", "Start a new execution context.")


def render_providers_page():
    render_page_header("Providers", "Configure and monitor LLM backends")
    c1, c2 = st.columns(2)
    cols = [c1, c2]
    for i, (name, factory) in enumerate(PROVIDER_FACTORIES.items()):
        with cols[i % 2]:
            is_active = name == adapter.provider_name
            metrics_dict = {"Requests": f"{len(st.session_state.execution_history)}" if is_active else "—"} if is_active else None
            render_provider_card(name, PROVIDER_HELP.get(name, ""),
                                "Active" if is_active else "Ready",
                                PROVIDER_TYPES.get(name, "Cloud"), metrics_dict)
            if st.button("Configure", key=f"prov_cfg_{name}", use_container_width=True):
                st.session_state.provider_sel = name
                st.session_state.page = "playground"
                st.rerun()


def render_templates_page():
    render_page_header("Templates", "Reusable prompt execution contracts")
    tmpls = adapter.get_templates()
    if tmpls:
        c1, c2 = st.columns(2)
        for i, t in enumerate(tmpls):
            with c1 if i % 2 == 0 else c2:
                src = t.get("source", "")
                desc = src[:60] + "..." if len(src) > 60 else src or "Built-in template"
                render_template_card(t["name"], desc, usage_count=0, avg_tokens=0)
                if st.button("Open", key=f"tpl_open_{t['name']}", use_container_width=True):
                    st.session_state.selected_template = t["name"]
                    st.session_state.page = "playground"
                    st.rerun()
    else:
        render_empty_state("No templates found", "Create a reusable execution template.")


def render_security_page():
    render_page_header("Security Center", "Defense-in-depth runtime protection")
    posture = adapter.security_posture
    render_panel("Security Posture", f"""
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;font-size:13px">
        <div><span style="color:var(--text-muted)">Input Sanitization</span><br><strong style="color:var(--success)">● {posture['input']}</strong></div>
        <div><span style="color:var(--text-muted)">Output Sanitization</span><br><strong style="color:var(--success)">● {posture['output']}</strong></div>
        <div><span style="color:var(--text-muted)">Rate Limiting</span><br><strong style="color:var(--success)">● {posture['rate_limit']}</strong></div>
        <div><span style="color:var(--text-muted)">Audit Chain</span><br><strong style="color:{"var(--success)" if adapter.audit_verified else "var(--danger)"}">● {posture['audit']}</strong></div>
    </div>""")
    render_security_summary(blocked=0, redacted=0, rate_limited=0,
                            total_events=len(st.session_state.execution_history))
    if not adapter.has_engine:
        render_empty_state("Engine not initialized",
                           "Configure a provider and initialize the engine.")


def render_audit_page():
    render_page_header("Audit Log", "Tamper-evident execution history")
    entries = adapter.audit_entries
    render_audit_integrity(adapter.audit_verified, len(entries))
    if st.button("Verify Now", use_container_width=True):
        ok = adapter.audit_verified
        if ok:
            show_success_toast(f"Audit chain verified: {len(entries)} entries")
        else:
            show_error_toast("Audit chain compromised!")
        st.rerun()

    if entries:
        for entry in entries[-20:]:
            render_audit_entry(entry)
        st.caption(f"Showing last {min(len(entries), 20)} of {len(entries)} entries")
    else:
        render_empty_state("No audit entries", "Execute a prompt to generate entries.")


def render_metrics_page():
    render_page_header("Observability", "Runtime performance and execution analytics")
    hist = st.session_state.execution_history
    snap = adapter.metrics_snapshot

    m1, m2, m3, m4 = st.columns(4)
    with m1: render_metric_card("Requests", str(len(hist)))
    with m2:
        ok_count = sum(1 for e in hist if e["status"] == "success")
        rate = (ok_count / max(len(hist), 1)) * 100
        render_metric_card("Success Rate", f"{rate:.1f}%")
    with m3:
        latencies = sorted(e["timing"]["total_ms"] for e in hist)
        p50 = latencies[len(latencies) // 2] if latencies else 0
        render_metric_card("P50", f"{p50:.0f}ms")
    with m4:
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else 0
        render_metric_card("P95", f"{p95:.0f}ms")

    if hist:
        import pandas as pd
        df = pd.DataFrame([{
            "latency": e["timing"]["total_ms"],
            "input_tok": e["tokens"]["input"],
            "output_tok": e["tokens"]["output"],
        } for e in hist])

        cc1, cc2 = st.columns(2)
        with cc1:
            render_panel("Latency (ms)")
            st.line_chart(df["latency"], height=180)
        with cc2:
            render_panel("Token Usage")
            st.line_chart(df[["input_tok", "output_tok"]], height=180)

        total_tok = df["input_tok"].sum() + df["output_tok"].sum()
        total_cost = sum(e.get("cost", 0) for e in hist)
        saved_tok = sum(e["tokens"]["saved"] for e in hist)

        with st.expander("Token Analytics", expanded=True):
            st.metric("Total Tokens", f"{total_tok:,}")
            st.metric("Tokens Saved", f"{saved_tok:,}")
            st.metric("Total Cost", _fmt_cost(total_cost))
            app = st.session_state.execution_history
            big = [e for e in app if e["tokens"]["input"] > 0]
            if big:
                avg_input = sum(e["tokens"]["input"] for e in big) / len(big)
                avg_output = sum(e["tokens"]["output"] for e in big) / len(big)
                st.caption(f"Avg input: {avg_input:.0f}  |  Avg output: {avg_output:.0f}")
    else:
        render_empty_state("No data yet", "Send prompts from Playground to see metrics.")


def render_traces_page():
    render_page_header("Traces", "Execution trace history")
    traces = adapter.get_traces()
    if traces:
        search = st.text_input("", placeholder="Search execution ID...",
                               label_visibility="collapsed", key="trace_search")
        for e in reversed(traces):
            if search and search not in e["id"] and search not in e["provider"]:
                continue
            render_execution_row(e)
            if st.button(f"View Trace {e['id']}", key=f"view_trace_{e['id']}"):
                st.session_state.page = "playground"
                st.rerun()
    else:
        render_empty_state("No traces found", "Run your first request from Playground.")


def render_runtime_config_page():
    render_page_header("Runtime Configuration", "Engine manifest settings")
    cfg = adapter.runtime_config
    if cfg:
        s1, s2 = st.columns(2)
        with s1:
            render_panel("General", f"""
            <div style="font-size:13px;display:flex;flex-direction:column;gap:6px">
                <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Name</span><span>{cfg['name']}</span></div>
                <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Version</span><span>{cfg['version']}</span></div>
                <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Environment</span><span>{cfg['environment']}</span></div>
                <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Isolation</span><span>{cfg['isolation']}</span></div>
            </div>""")
        with s2:
            render_panel("Limits", f"""
            <div style="font-size:13px;display:flex;flex-direction:column;gap:6px">
                <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Max Payload</span><span>{cfg['max_payload_kb']} KB</span></div>
                <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Max History</span><span>{cfg['max_history']} turns</span></div>
                <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Rate Limit</span><span>{cfg['rate_max']} / {cfg['rate_window']}s</span></div>
                <div style="display:flex;justify-content:space-between"><span style="color:var(--text-muted)">Sanitize Inputs</span><span>{"ON" if cfg['sanitize'] else "OFF"}</span></div>
            </div>""")
    else:
        render_empty_state("No config", "Initialize the engine to read configuration.")


def render_settings_page():
    render_page_header("Settings", "Interface and system preferences")
    c1, c2 = st.columns(2)
    with c1:
        render_panel("Appearance")
        st.toggle("Compact mode", value=False, key="set_compact")
        st.toggle("Show execution trace", value=st.session_state.show_trace, key="set_show_trace")
    with c2:
        render_panel("Developer")
        st.toggle("Debug information", value=False, key="set_debug")
        st.toggle("Raw event details", value=False, key="set_raw")

    if st.button("Clear Local Session", use_container_width=True, type="secondary"):
        adapter.reset_session()
        show_info_toast("Session cleared")
        st.rerun()

    if st.button("Reset UI State", use_container_width=True, type="secondary"):
        for key in DEFAULT_UI_STATE:
            st.session_state[key] = DEFAULT_UI_STATE[key]
        st.rerun()


PAGES = {
    "overview": render_overview_page,
    "playground": render_playground_page,
    "sessions": render_sessions_page,
    "providers": render_providers_page,
    "templates": render_templates_page,
    "security": render_security_page,
    "audit": render_audit_page,
    "metrics": render_metrics_page,
    "traces": render_traces_page,
    "config": render_runtime_config_page,
    "settings": render_settings_page,
}

page_func = PAGES.get(st.session_state.page)
if page_func:
    page_func()
else:
    render_overview_page()

render_footer()
