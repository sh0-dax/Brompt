"""
Brompt Runtime Design System — Dark, technical, minimal.
Developer console aesthetic. No external font dependencies.
"""

import streamlit as st
from typing import Optional


def inject_design_system():
    st.markdown("""
    <style>
    :root {
        --bg-primary: #080B12;
        --bg-surface: #0D111A;
        --bg-elevated: #111827;
        --bg-card: #0D111A;
        --border: #1F2937;
        --border-light: rgba(255,255,255,0.06);
        --primary: #6366F1;
        --primary-hover: #4F46E5;
        --primary-light: rgba(99,102,241,0.1);
        --success: #10B981;
        --success-light: rgba(16,185,129,0.1);
        --warning: #F59E0B;
        --warning-light: rgba(245,158,11,0.1);
        --danger: #EF4444;
        --danger-light: rgba(239,68,68,0.1);
        --text: #F8FAFC;
        --text-secondary: #CBD5E1;
        --muted: #94A3B8;
        --radius-card: 10px;
        --radius-btn: 8px;
        --radius-input: 8px;
        --radius-badge: 999px;
        --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
        --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
        --transition: 0.15s ease;
    }
    * { font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }
    code, pre, .mono { font-family: ui-monospace, 'SF Mono', Consolas, monospace; }
    .stApp { background: var(--bg-primary); }

    /* === STATUS BAR === */
    .brompt-statusbar {
        display: flex; align-items: center; justify-content: space-between;
        background: var(--bg-elevated); border: 1px solid var(--border);
        border-radius: var(--radius-card); padding: 8px 16px; margin-bottom: 16px;
    }
    .brompt-statusbar-left { display: flex; align-items: center; gap: 12px; }
    .brompt-statusbar-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .brompt-statusbar-dot.online { background: var(--success); box-shadow: 0 0 6px var(--success); }
    .brompt-statusbar-dot.offline { background: var(--muted); }
    .brompt-statusbar-label { font-size: 0.8rem; font-weight: 600; color: var(--text); }
    .brompt-statusbar-sep { color: var(--border); font-size: 0.75rem; }
    .brompt-statusbar-item { font-size: 0.78rem; color: var(--muted); }
    .brompt-statusbar-right { display: flex; align-items: center; gap: 10px; font-size: 0.75rem; color: var(--muted); }
    .brompt-statusbar-kbd {
        background: var(--bg-primary); border: 1px solid var(--border);
        border-radius: 4px; padding: 1px 6px; font-family: monospace; font-size: 0.7rem;
    }

    /* === STAT ROW === */
    .brompt-statrow { display: flex; gap: 12px; margin: 12px 0 16px 0; flex-wrap: wrap; }
    .brompt-statcard {
        flex: 1; min-width: 120px; background: var(--bg-card);
        border: 1px solid var(--border); border-radius: var(--radius-card);
        padding: 14px 16px; text-align: center;
    }
    .brompt-statcard-value { font-size: 1.6rem; font-weight: 700; color: var(--text); line-height: 1.2; }
    .brompt-statcard-label { font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }

    /* === COMPACT HERO === */
    .brompt-hero {
        background: linear-gradient(135deg, #0D111A, #111827);
        border: 1px solid var(--border); border-radius: var(--radius-card);
        padding: 16px 20px; margin-bottom: 16px;
    }
    .brompt-hero-title { font-size: 1.1rem; font-weight: 700; color: var(--text); }
    .brompt-hero-subtitle { font-size: 0.8rem; color: var(--muted); margin-top: 2px; }

    /* === BADGES === */
    .brompt-badge {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 4px 12px; border-radius: var(--radius-badge);
        font-size: 0.78rem; font-weight: 500;
    }
    .brompt-badge-savings { background: var(--success-light); border: 1px solid rgba(16,185,129,0.25); color: #34D399; }
    .brompt-badge-cache { background: var(--primary-light); border: 1px solid rgba(99,102,241,0.2); color: #818CF8; }
    .brompt-badge-detect { background: var(--primary-light); border: 1px solid rgba(99,102,241,0.2); color: #A5B4FC; }
    .brompt-badge-model { background: var(--warning-light); border: 1px solid rgba(245,158,11,0.2); color: #FCD34D; }
    .brompt-badge-template { background: rgba(139,92,246,0.1); border: 1px solid rgba(139,92,246,0.2); color: #C4B5FD; }

    /* === PROGRESS BAR === */
    .brompt-progress { height: 6px; background: rgba(255,255,255,0.05); border-radius: 3px; overflow: hidden; }
    .brompt-progress-fill { height: 100%; border-radius: 3px; transition: width 0.4s ease; }

    /* === EXECUTION TRACE === */
    .brompt-trace { margin: 8px 0; }
    .brompt-trace-step { display: flex; align-items: center; gap: 10px; padding: 5px 0; position: relative; }
    .brompt-trace-dot {
        width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
        font-size: 0.6rem; font-weight: 700; flex-shrink: 0; position: relative; z-index: 1;
    }
    .brompt-trace-dot.completed { background: var(--success); color: #000; }
    .brompt-trace-dot.running { background: var(--primary); color: #fff; animation: pulse 1.5s ease infinite; }
    .brompt-trace-dot.error { background: var(--danger); color: #fff; }
    .brompt-trace-dot.pending { background: var(--bg-elevated); border: 1px solid var(--border); color: var(--muted); }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .brompt-trace-line {
        position: absolute; left: 9px; top: 26px; width: 2px; bottom: -6px;
        background: var(--border); z-index: 0;
    }
    .brompt-trace-step:last-child .brompt-trace-line { display: none; }
    .brompt-trace-name { font-size: 0.8rem; color: var(--text-secondary); font-weight: 500; flex: 1; }
    .brompt-trace-time { font-size: 0.72rem; color: var(--muted); font-family: monospace; min-width: 40px; text-align: right; }
    .brompt-trace-total { text-align: right; font-size: 0.8rem; color: var(--muted); margin-top: 4px; padding-top: 4px; border-top: 1px solid var(--border); font-family: monospace; }

    /* === PROVIDER CARD === */
    .brompt-provider-card {
        background: var(--bg-card); border: 1px solid var(--border);
        border-radius: var(--radius-card); padding: 12px 14px; margin: 4px 0;
        display: flex; align-items: center; gap: 12px;
    }
    .brompt-provider-card.active { border-color: var(--primary); }
    .brompt-provider-icon {
        width: 32px; height: 32px; border-radius: 8px; display: flex;
        align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0;
    }
    .brompt-provider-info { flex: 1; }
    .brompt-provider-name { font-size: 0.85rem; font-weight: 600; color: var(--text); }
    .brompt-provider-model { font-size: 0.72rem; color: var(--muted); }
    .brompt-provider-status { font-size: 0.7rem; font-weight: 500; padding: 2px 8px; border-radius: var(--radius-badge); }
    .brompt-provider-status.connected { background: var(--success-light); color: #34D399; }
    .brompt-provider-status.disconnected { background: var(--danger-light); color: #F87171; }

    /* === AUDIT TABLE === */
    .brompt-audit { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
    .brompt-audit th { text-align: left; padding: 8px 10px; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--border); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .brompt-audit td { padding: 7px 10px; border-bottom: 1px solid rgba(255,255,255,0.03); color: var(--text-secondary); }
    .brompt-audit tr:hover td { background: rgba(255,255,255,0.02); }
    .brompt-audit-hash { font-family: monospace; font-size: 0.7rem; color: var(--muted); }
    .brompt-audit-status { display: inline-flex; align-items: center; gap: 4px; }
    .brompt-audit-status.valid { color: var(--success); }
    .brompt-audit-status.invalid { color: var(--danger); }

    /* === SECURITY STATUS === */
    .brompt-sec-status { display: flex; gap: 10px; flex-wrap: wrap; margin: 8px 0; }
    .brompt-sec-item {
        flex: 1; min-width: 100px; background: var(--bg-card);
        border: 1px solid var(--border); border-radius: var(--radius-card);
        padding: 12px 14px; text-align: center;
    }
    .brompt-sec-item .label { font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .brompt-sec-item .value { font-size: 0.85rem; font-weight: 600; margin-top: 4px; display: flex; align-items: center; justify-content: center; gap: 6px; }
    .brompt-sec-item .value.active { color: var(--success); }
    .brompt-sec-item .value.inactive { color: var(--muted); }
    .brompt-sec-item .value.danger { color: var(--danger); }
    .brompt-sec-event { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 0.78rem; }
    .brompt-sec-event:last-child { border-bottom: none; }
    .brompt-sec-event-time { color: var(--muted); font-family: monospace; font-size: 0.72rem; }
    .brompt-sec-event-type { color: var(--text-secondary); font-weight: 500; }
    .brompt-sec-event-tag { font-size: 0.65rem; padding: 1px 6px; border-radius: 4px; font-weight: 500; }
    .brompt-sec-event-tag.blocked { background: var(--danger-light); color: #F87171; }
    .brompt-sec-event-tag.sanitized { background: var(--warning-light); color: #FCD34D; }

    /* === CARD === */
    .brompt-card {
        background: var(--bg-card); border: 1px solid var(--border);
        border-radius: var(--radius-card); padding: 14px 16px; margin: 8px 0;
    }
    .brompt-card-title { font-size: 0.85rem; font-weight: 600; color: var(--text); margin-bottom: 8px; }

    /* === SIDEBAR === */
    [data-testid="stSidebar"] { background: var(--bg-surface); border-right: 1px solid var(--border); }

    /* === BUTTONS === */
    .stButton > button {
        border-radius: var(--radius-btn) !important;
        font-weight: 500 !important; transition: var(--transition) !important;
    }

    /* === RESPONSIVE === */
    @media (max-width: 768px) {
        .brompt-statrow { gap: 6px; }
        .brompt-statcard { min-width: 80px; padding: 10px; }
        .brompt-statcard-value { font-size: 1.2rem; }
        .brompt-statusbar { flex-wrap: wrap; gap: 6px; }
    }
    </style>
    """, unsafe_allow_html=True)


def render_runtime_status_bar(
    online: bool = True,
    provider: str = "Gemini",
    model: str = "gemini-2.5-flash",
    latency_ms: float = 0,
    secure: bool = True,
):
    dot_class = "online" if online else "offline"
    status_text = "ONLINE" if online else "OFFLINE"
    sec_text = "Protected" if secure else "Exposed"
    st.markdown(f"""
    <div class="brompt-statusbar">
        <div class="brompt-statusbar-left">
            <span class="brompt-statusbar-dot {dot_class}"></span>
            <span class="brompt-statusbar-label">{status_text}</span>
            <span class="brompt-statusbar-sep">|</span>
            <span class="brompt-statusbar-item">{provider}</span>
            <span class="brompt-statusbar-item" style="color:var(--text-secondary)">{model}</span>
            <span class="brompt-statusbar-sep">|</span>
            <span class="brompt-statusbar-item" style="color:var(--success)">● {sec_text}</span>
        </div>
        <div class="brompt-statusbar-right">
            <span>{latency_ms:.0f}ms avg</span>
            <span class="brompt-statusbar-kbd">Ctrl+K</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_stat_row(stats: list[tuple[str, str, Optional[str]]]):
    """stats: [(value, label, optional_color), ...]"""
    cards = ""
    for value, label, color in stats:
        style = f"color:{color};" if color else ""
        cards += f"""
        <div class="brompt-statcard">
            <div class="brompt-statcard-value" style="{style}">{value}</div>
            <div class="brompt-statcard-label">{label}</div>
        </div>"""
    st.markdown(f'<div class="brompt-statrow">{cards}</div>', unsafe_allow_html=True)


def render_hero_section(
    total_requests: int = 0,
    tokens_saved: int = 0,
    cost_saved: float = 0.0,
    active_template: str = "default",
):
    st.markdown(f"""
    <div class="brompt-hero">
        <div class="brompt-hero-title">⚡ Brompt Runtime</div>
        <div class="brompt-hero-subtitle">High-performance AI execution control plane</div>
    </div>
    """, unsafe_allow_html=True)
    render_stat_row([
        (str(total_requests), "Requests", None),
        (f"{tokens_saved:,}", "Tokens Saved", "var(--success)"),
        (f"${cost_saved:.4f}", "Cost Saved", None),
        (active_template, "Template", None),
    ])


def render_savings_badge(tokens: int, cost: float):
    st.markdown(f"""
    <span class="brompt-badge brompt-badge-savings">
        💰 Saved {tokens:,} tokens (${cost:.4f})
    </span>
    """, unsafe_allow_html=True)


def render_cached_badge():
    st.markdown("""<span class="brompt-badge brompt-badge-cache">💾 Cached</span>""", unsafe_allow_html=True)


def render_detection_badge(task: str, model: str, template: str, confidence: float):
    conf_color = "#34D399" if confidence > 0.8 else "#F59E0B" if confidence > 0.5 else "#EF4444"
    st.markdown(f"""
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0">
        <span class="brompt-badge brompt-badge-detect">🧠 {task} <span style="color:{conf_color}">({confidence:.0%})</span></span>
        <span class="brompt-badge brompt-badge-model">⚡ {model}</span>
        <span class="brompt-badge brompt-badge-template">📋 {template}</span>
    </div>""", unsafe_allow_html=True)


def render_progress_bar(used: int, total: int, label: str = "Tokens"):
    pct = min(used / total * 100, 100) if total > 0 else 0
    color = "var(--success)" if pct < 50 else "var(--warning)" if pct < 80 else "var(--danger)"
    st.markdown(f"""
    <div style="margin:4px 0">
        <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--muted);margin-bottom:3px">
            <span>{label}</span><span>{used:,} / {total:,} ({pct:.0f}%)</span>
        </div>
        <div class="brompt-progress"><div class="brompt-progress-fill" style="width:{pct}%;background:{color}"></div></div>
    </div>""", unsafe_allow_html=True)


def render_execution_trace(stages: list[dict], total_ms: float = 0):
    """stages: [{"name": str, "time_ms": float, "status": "completed"|"running"|"error"|"pending"}]"""
    lines = '<div class="brompt-trace">'
    for s in stages:
        dot_class = s.get("status", "pending")
        check = "✓" if dot_class == "completed" else "✗" if dot_class == "error" else "◉"
        name = s.get("name", "")
        t = s.get("time_ms", 0)
        time_str = f"{t:.0f}ms" if t > 0 else ""
        lines += f"""
        <div class="brompt-trace-step">
            <div class="brompt-trace-dot {dot_class}">{check}</div>
            <span class="brompt-trace-name">{name}</span>
            <span class="brompt-trace-time">{time_str}</span>
            <div class="brompt-trace-line"></div>
        </div>"""
    lines += f'<div class="brompt-trace-total">Total: {total_ms:.0f}ms</div>' if total_ms > 0 else ''
    lines += "</div>"
    st.markdown(lines, unsafe_allow_html=True)


def render_provider_card(name: str, model: str, status: str, active: bool = False, icon: str = "✦"):
    active_cls = "active" if active else ""
    status_cls = "connected" if status == "connected" else "disconnected"
    st.markdown(f"""
    <div class="brompt-provider-card {active_cls}">
        <div class="brompt-provider-icon" style="background:var(--primary-light);color:var(--primary)">{icon}</div>
        <div class="brompt-provider-info">
            <div class="brompt-provider-name">{name}</div>
            <div class="brompt-provider-model">{model}</div>
        </div>
        <div class="brompt-provider-status {status_cls}">{status.title()}</div>
    </div>""", unsafe_allow_html=True)


def render_audit_entries(entries: list[dict]):
    if not entries:
        st.markdown('<div style="color:var(--muted);font-size:0.8rem;padding:12px 0">No audit entries</div>', unsafe_allow_html=True)
        return
    rows = ""
    for e in entries[-20:]:
        ts = e.get("timestamp", "")[:19] if e.get("timestamp") else "--"
        event = e.get("event", e.get("action", "EXECUTION"))
        h = e.get("hash", "")[:10] if e.get("hash") else ""
        valid = e.get("is_secure", e.get("verified", True))
        status_icon = "✓" if valid else "✗"
        status_class = "valid" if valid else "invalid"
        rows += f"""
        <tr>
            <td style="font-family:monospace;font-size:0.72rem;color:var(--muted)">{ts}</td>
            <td>{event}</td>
            <td><span class="brompt-audit-status {status_class}">{status_icon} {"Valid" if valid else "Invalid"}</span></td>
            <td class="brompt-audit-hash">{h}...</td>
        </tr>"""
    st.markdown(f"""
    <table class="brompt-audit">
        <thead><tr><th>Time</th><th>Event</th><th>Status</th><th>Hash</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>""", unsafe_allow_html=True)


def render_security_status(
    blocked: int = 0,
    sanitized: int = 0,
    rate_limited: int = 0,
    events: Optional[list[dict]] = None,
):
    st.markdown("""
    <div style="font-size:0.85rem;font-weight:600;color:var(--text);margin-bottom:8px">Security Status</div>
    <div class="brompt-sec-status">
        <div class="brompt-sec-item">
            <div class="label">Input Protection</div>
            <div class="value active">● ACTIVE</div>
        </div>
        <div class="brompt-sec-item">
            <div class="label">Output Sanitizer</div>
            <div class="value active">● ACTIVE</div>
        </div>
        <div class="brompt-sec-item">
            <div class="label">Rate Limiter</div>
            <div class="value active">● ACTIVE</div>
        </div>
        <div class="brompt-sec-item">
            <div class="label">Audit Chain</div>
            <div class="value active">● VALID</div>
        </div>
    </div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin:8px 0;font-size:0.85rem">
        <span style="color:var(--muted)">Blocked: <strong style="color:var(--danger)">{blocked}</strong></span>
        <span style="color:var(--muted)">Sanitized: <strong style="color:var(--warning)">{sanitized}</strong></span>
        <span style="color:var(--muted)">Rate Limited: <strong style="color:var(--warning)">{rate_limited}</strong></span>
        <span style="color:var(--muted)">Events: <strong style="color:var(--text-secondary)}">{len(events) if events else 0}</strong></span>
    </div>""", unsafe_allow_html=True)
    if events:
        ev_lines = ""
        for ev in events[-6:]:
            tag_class = "blocked" if "BLOCKED" in ev.get("type", "") else "sanitized"
            ev_lines += f"""
            <div class="brompt-sec-event">
                <span class="brompt-sec-event-time">{ev.get("time", "")}</span>
                <span class="brompt-sec-event-type">{ev.get("type", "")}</span>
                <span class="brompt-sec-event-tag {tag_class}">{ev.get("tag", "")}</span>
            </div>"""
        st.markdown(f"""
        <div style="margin-top:8px">
            <div style="font-size:0.78rem;color:var(--muted);margin-bottom:4px">Recent Events</div>
            {ev_lines}
        </div>""", unsafe_allow_html=True)


def render_card(content: str, title: str = None):
    title_html = f'<div class="brompt-card-title">{title}</div>' if title else ""
    st.markdown(f'<div class="brompt-card">{title_html}{content}</div>', unsafe_allow_html=True)


def show_success_toast(message: str):
    st.toast(message, icon="✅")


def show_savings_toast(tokens: int, percent: float):
    st.toast(f"💰 Saved {tokens:,} tokens ({percent:.0f}%)", icon="💰")


def show_error_toast(message: str):
    st.toast(message, icon="❌")


def show_info_toast(message: str):
    st.toast(message, icon="ℹ️")
