"""
Brompt GUI V2 — Runtime Control Plane Design System.
Developer console aesthetic. Infrastructure-grade, not chatbot-grade.
"""

import streamlit as st
from typing import Optional

# ────────────────────────────────────────────── CSS SECTIONS ──────────────────

BASE_CSS = """
:root {
    --bg-root: #080B12;
    --bg-sidebar: #0A0E16;
    --bg-surface: #0D111A;
    --bg-surface-2: #111827;
    --bg-surface-3: #151D2B;
    --border: #1F2937;
    --border-soft: #172033;
    --border-active: #303B52;
    --text-primary: #F8FAFC;
    --text-secondary: #CBD5E1;
    --text-muted: #94A3B8;
    --text-disabled: #64748B;
    --accent: #6366F1;
    --accent-hover: #818CF8;
    --accent-soft: rgba(99, 102, 241, .12);
    --success: #10B981;
    --success-soft: rgba(16, 185, 129, .10);
    --warning: #F59E0B;
    --warning-soft: rgba(245, 158, 11, .10);
    --danger: #EF4444;
    --danger-soft: rgba(239, 68, 68, .10);
    --info: #38BDF8;
    --info-soft: rgba(56, 189, 248, .10);
    --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
    --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-10: 40px;
    --space-12: 48px; --space-16: 64px;
    --radius-sm: 6px; --radius-md: 8px; --radius-lg: 12px;
    --radius-xl: 16px; --radius-pill: 999px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,.25);
    --shadow-md: 0 8px 24px rgba(0,0,0,.20);
    --shadow-lg: 0 16px 48px rgba(0,0,0,.28);
    --transition: .15s ease;
}
* { font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif; }
code, pre, .mono, kbd { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Consolas, monospace; }
.stApp, .stApp > div:first-child, [data-testid="stAppViewContainer"] {
    background: var(--bg-root) !important;
}
.stApp > div:first-child > div:first-child {
    background: var(--bg-root) !important;
}
a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-hover); }
::selection { background: var(--accent-soft); color: var(--text-primary); }
"""

STREAMLIT_CSS = """
#root > div:first-child > div:first-child > div:first-child { overflow: hidden; }
[data-testid="stAppViewContainer"] > section:first-child { padding: 0 !important; }
.main > div:first-child > div:first-child { max-width: 100% !important; padding: 0 !important; }
.stMainBlockContainer, .stAppViewBlockContainer, .block-container {
    max-width: 100% !important; padding: 0 !important;
}
.appview-container .main .block-container { padding: 0 !important; max-width: 100% !important; }
header[data-testid="stHeader"] { display: none !important; }
#MainMenu { visibility: hidden !important; height: 0 !important; }
footer { display: none !important; }
.stAppDeployButton { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
.stApp > div:first-child > div:first-child > div:first-child > div:first-child { padding: 0 !important; }
section[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }
[data-testid="stSidebarContent"] { padding: 0 !important; }
[data-testid="column"] { gap: 0 !important; }
.st-emotion-cache-1r4qj8v, .st-emotion-cache-keje6m { padding: 0 !important; gap: 0 !important; }
div[data-testid="stVerticalBlock"] { gap: 8px !important; }
"""

LAYOUT_CSS = """
.brompt-appshell { display: flex; min-height: 100vh; }
.brompt-main { flex: 1; max-width: 1440px; padding: 0 28px 32px; margin: 0 auto; width: 100%; }
.brompt-main-top { padding-top: 16px; }
"""

SIDEBAR_CSS = """
[data-testid="stSidebar"] {
    background: var(--bg-sidebar) !important;
    border-right: 1px solid var(--border) !important;
    width: 248px !important; min-width: 248px !important;
}
[data-testid="stSidebar"] .stButton button {
    background: transparent; border: none; color: var(--text-secondary);
    text-align: left; font-size: 13px; padding: 6px 12px; border-radius: var(--radius-sm);
    transition: var(--transition); font-weight: 400;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: var(--bg-surface-2); color: var(--text-primary);
}
[data-testid="stSidebar"] .stButton button[data-active="true"],
[data-testid="stSidebar"] .stButton button:active {
    background: var(--accent-soft); color: var(--accent);
}
.sidebar-brand { color: var(--text-primary); font-size: 16px; font-weight: 700; padding: 16px 12px 2px; letter-spacing: -.3px; }
.sidebar-subtitle { color: var(--text-muted); font-size: 11px; padding: 0 12px 16px; font-weight: 500; }
.sidebar-section { color: var(--text-disabled); font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .8px; padding: 12px 12px 4px; }
.sidebar-divider { border: none; border-top: 1px solid var(--border-soft); margin: 8px 12px; }
.sidebar-footer { position: absolute; bottom: 0; left: 0; right: 0; padding: 12px; border-top: 1px solid var(--border-soft); font-size: 12px; }
.sidebar-footer-status { display: flex; align-items: center; gap: 8px; color: var(--text-muted); }
.sidebar-footer-provider { color: var(--text-secondary); font-size: 11px; margin-top: 2px; }
"""

TOPBAR_CSS = """
.brompt-topbar {
    display: flex; align-items: center; justify-content: space-between;
    height: 60px; border-bottom: 1px solid var(--border-soft);
    margin-bottom: 20px;
}
.brompt-topbar-left { display: flex; align-items: center; gap: 8px; color: var(--text-muted); font-size: 13px; }
.brompt-topbar-left strong { color: var(--text-primary); font-weight: 600; }
.brompt-topbar-sep { color: var(--border); }
.brompt-topbar-right { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--text-muted); }
.brompt-topbar-kbd {
    background: var(--bg-surface-2); border: 1px solid var(--border); border-radius: 4px;
    padding: 2px 7px; font-size: 11px; color: var(--text-disabled);
}
"""

CARD_CSS = """
.brompt-card {
    background: var(--bg-surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: var(--space-5);
    transition: border-color var(--transition), background var(--transition);
}
.brompt-card:hover { border-color: var(--border-active); background: var(--bg-surface-2); }
.brompt-card-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
"""

METRIC_CARD_CSS = """
.brompt-metric {
    background: var(--bg-surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: var(--space-5);
    min-height: 112px; display: flex; flex-direction: column; justify-content: space-between;
}
.brompt-metric-label { color: var(--text-muted); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; }
.brompt-metric-value { color: var(--text-primary); font-size: 28px; line-height: 1; font-weight: 700; margin: 4px 0; }
.brompt-metric-delta { font-size: 12px; font-weight: 500; }
.brompt-metric-delta.pos { color: var(--success); }
.brompt-metric-delta.neg { color: var(--danger); }
.brompt-metric-caption { color: var(--text-muted); font-size: 12px; }
"""

BUTTON_CSS = """
.stButton button, .brompt-btn {
    min-height: 36px; padding: 0 14px; border-radius: var(--radius-md) !important;
    font-weight: 600 !important; font-size: 13px !important; transition: var(--transition) !important;
}
.brompt-btn-primary { background: var(--accent); color: #fff; border: none; }
.brompt-btn-primary:hover { background: var(--accent-hover); }
.brompt-btn-secondary { background: var(--bg-surface-2); color: var(--text-secondary); border: 1px solid var(--border); }
.brompt-btn-secondary:hover { border-color: var(--border-active); color: var(--text-primary); }
.brompt-btn-ghost { background: transparent; color: var(--text-muted); border: none; }
.brompt-btn-ghost:hover { color: var(--text-primary); }
.brompt-btn-danger { background: var(--danger-soft); color: var(--danger); border: 1px solid rgba(239,68,68,.2); }
.brompt-btn-danger:hover { background: rgba(239,68,68,.18); }
"""

FORM_CSS = """
[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 700 !important; color: var(--text-primary) !important; }
[data-testid="stMetricLabel"] { font-size: 12px !important; font-weight: 600 !important; color: var(--text-muted) !important; text-transform: uppercase !important; letter-spacing: .06em !important; }
[data-testid="stMetricDelta"] { font-size: 12px !important; }
[data-testid="stExpander"] { border: 1px solid var(--border) !important; border-radius: var(--radius-lg) !important; background: var(--bg-surface) !important; }
[data-testid="stExpander"] summary { font-weight: 600 !important; font-size: 13px !important; }
[data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: var(--radius-lg) !important; }
.st-bp, .st-bq, .st-br, .st-cf { color: var(--text-secondary) !important; }
.stTextInput, .stSelectbox, .stTextArea { margin-bottom: 4px; }
.brompt-input, input:not([type]), input[type="text"], input[type="password"], textarea, select, .stSelectbox div[data-baseweb="select"] > div {
    background: var(--bg-surface-2) !important; border: 1px solid var(--border) !important;
    color: var(--text-primary) !important; border-radius: var(--radius-md) !important;
    padding: 8px 12px !important; font-size: 13px !important;
}
.brompt-input:focus, input:focus, textarea:focus, select:focus {
    border-color: var(--accent) !important; box-shadow: 0 0 0 2px var(--accent-soft) !important;
}
label, .stSelectbox label, .stTextInput label { color: var(--text-muted) !important; font-size: 12px !important; font-weight: 500 !important; }
.stTextInput, .stSelectbox, .stTextArea { margin-bottom: 4px; }
"""

TABLE_CSS = """
.brompt-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.brompt-table th { text-align: left; padding: 8px 12px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
.brompt-table td { padding: 7px 12px; border-bottom: 1px solid var(--border-soft); color: var(--text-secondary); }
.brompt-table tr:hover td { background: var(--bg-surface-2); }
.brompt-table tr { cursor: pointer; }
"""

TRACE_CSS = """
.brompt-trace { margin: 0; }
.brompt-trace-node { display: flex; align-items: center; gap: 10px; padding: 6px 0; position: relative; }
.brompt-trace-dot {
    width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; font-size: 10px; font-weight: 700; flex-shrink: 0; z-index: 1;
}
.brompt-trace-dot.pass { background: var(--success); color: #000; }
.brompt-trace-dot.run { background: var(--accent); color: #fff; animation: trace-pulse 1.2s ease infinite; }
.brompt-trace-dot.fail { background: var(--danger); color: #fff; }
.brompt-trace-dot.wait { background: var(--bg-surface-3); border: 1px solid var(--border); color: var(--text-disabled); }
@keyframes trace-pulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }
.brompt-trace-connector {
    position: absolute; left: 9px; top: 28px; width: 2px; bottom: -8px;
    background: var(--border); z-index: 0;
}
.brompt-trace-node:last-child .brompt-trace-connector { display: none; }
.brompt-trace-name { font-size: 13px; color: var(--text-secondary); font-weight: 500; flex: 1; }
.brompt-trace-time { font-size: 12px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; min-width: 45px; text-align: right; }
.brompt-trace-detail { font-size: 12px; color: var(--text-muted); padding: 6px 0 6px 30px; border-left: 2px solid var(--border-soft); margin-left: 9px; }
.brompt-trace-arrow { text-align: center; color: var(--border); font-size: 10px; padding: 2px 0; }
"""

STATUS_CSS = """
.status-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.status-dot.online { background: var(--success); box-shadow: 0 0 6px var(--success); }
.status-dot.degraded { background: var(--warning); box-shadow: 0 0 6px var(--warning); }
.status-dot.offline { background: var(--text-disabled); }
.status-dot.init { background: var(--info); animation: trace-pulse 1.2s ease infinite; }
.status-dot.error { background: var(--danger); }
.brompt-badge {
    display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px;
    border-radius: var(--radius-pill); font-size: 12px; font-weight: 500;
}
.brompt-badge-protected { background: var(--success-soft); border: 1px solid rgba(16,185,129,.2); color: #34D399; }
.brompt-badge-exposed { background: var(--danger-soft); border: 1px solid rgba(239,68,68,.2); color: #F87171; }
.brompt-badge-init { background: var(--info-soft); border: 1px solid rgba(56,189,248,.2); color: #7DD3FC; }
.brompt-badge-online { background: var(--success-soft); border: 1px solid rgba(16,185,129,.2); color: #34D399; }
.brompt-badge-offline { background: transparent; border: 1px solid var(--border); color: var(--text-disabled); }
"""

DRAWER_CSS = """
.brompt-drawer-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,.5); z-index: 100; display: flex; justify-content: flex-end;
}
.brompt-drawer {
    width: 480px; max-width: 100vw; height: 100vh; overflow-y: auto;
    background: var(--bg-surface); border-left: 1px solid var(--border);
    padding: var(--space-6); animation: drawer-slide .2s ease;
}
@keyframes drawer-slide { from { transform: translateX(100%); } to { transform: translateX(0); } }
.brompt-drawer-close {
    float: right; background: transparent; border: none; color: var(--text-muted);
    font-size: 20px; cursor: pointer; padding: 4px 8px; border-radius: var(--radius-sm);
}
.brompt-drawer-close:hover { background: var(--bg-surface-2); color: var(--text-primary); }
.brompt-drawer-section { margin: var(--space-5) 0; }
.brompt-drawer-label { font-size: 11px; font-weight: 600; color: var(--text-disabled); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px; }
.brompt-drawer-value { font-size: 14px; color: var(--text-primary); }
.brompt-drawer-divider { border: none; border-top: 1px solid var(--border-soft); margin: var(--space-4) 0; }
"""

KEYBOARD_CSS = """
.brompt-shortcuts-hint {
    position: fixed; bottom: 16px; right: 16px; z-index: 50;
    background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
    padding: var(--space-4); font-size: 12px; color: var(--text-muted); min-width: 200px;
    box-shadow: var(--shadow-md); display: none;
}
.brompt-shortcuts-hint.visible { display: block; }
.brompt-shortcuts-item { display: flex; justify-content: space-between; padding: 3px 0; }
kbd { background: var(--bg-surface-2); border: 1px solid var(--border); border-radius: 4px; padding: 2px 7px; font-size: 11px; color: var(--text-disabled); font-family: 'JetBrains Mono', monospace; }
"""

RESPONSIVE_CSS = """
@media (max-width: 1200px) {
    .brompt-metric { min-height: 96px; }
    .brompt-metric-value { font-size: 24px; }
}
@media (max-width: 992px) {
    .brompt-main { padding: 0 16px 24px; }
    [data-testid="stSidebar"] { width: 248px !important; min-width: 248px !important; }
    .brompt-topbar { height: 48px; flex-wrap: wrap; gap: 4px; }
    .brompt-metric { min-height: 80px; }
    .brompt-metric-value { font-size: 20px; }
    .sidebar-footer { position: relative; }
}
@media (max-width: 768px) {
    .brompt-main { padding: 0 10px 16px; }
    [data-testid="stSidebar"] { width: 100% !important; min-width: 100% !important; }
    .brompt-topbar { height: auto; padding: 8px 0; }
    .brompt-metric { min-height: 72px; }
    .brompt-metric-value { font-size: 18px; }
}
"""

MISC_CSS = """
[data-testid="stTabs"] { border-bottom: 1px solid var(--border); margin-bottom: 16px; }
[data-testid="stTabs"] button { font-size: 13px !important; color: var(--text-muted) !important; }
[data-testid="stTabs"] button[aria-selected="true"] { color: var(--accent) !important; }
.stCodeBlock { background: var(--bg-surface-2) !important; border: 1px solid var(--border) !important; border-radius: var(--radius-md) !important; }
.stChatFloatingInputContainer { background: var(--bg-surface) !important; border-top: 1px solid var(--border) !important; }
[data-testid="chatInput"] { background: var(--bg-surface-2) !important; border: 1px solid var(--border) !important; border-radius: var(--radius-md) !important; color: var(--text-primary) !important; }
.stChatMessage { background: transparent !important; border: none !important; }
[data-testid="stChatMessageContent"] { background: var(--bg-surface) !important; border: 1px solid var(--border-soft) !important; border-radius: var(--radius-lg) !important; padding: 12px 14px !important; }
.stSpinner > div { border-color: var(--accent) transparent transparent transparent !important; }
"""

GLOBAL_CSS = "\n".join([
    BASE_CSS, STREAMLIT_CSS, LAYOUT_CSS, SIDEBAR_CSS, TOPBAR_CSS, CARD_CSS,
    METRIC_CARD_CSS, BUTTON_CSS, FORM_CSS, TABLE_CSS, TRACE_CSS,
    STATUS_CSS, DRAWER_CSS, KEYBOARD_CSS, MISC_CSS, RESPONSIVE_CSS,
])

# ────────────────────────────────────────────── DESIGN SYSTEM ────────────────


def inject_global_css(theme: str = "dark"):
    st.markdown(f"<style>{GLOBAL_CSS}</style>", unsafe_allow_html=True)
    if "Inter" not in st.session_state.get("_fonts_loaded", ""):
        st.markdown("""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
        """, unsafe_allow_html=True)
        st.session_state._fonts_loaded = "Inter"
    if "_kb_injected" not in st.session_state:
        st.markdown("""
        <script>
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey && e.key === 'k') {
                e.preventDefault();
                const inp = document.querySelector('[data-testid="stTextInput"] input');
                if (inp) inp.focus();
                return;
            }
            var actions = {
                'n': 'new_session',
                'l': 'clear_session',
                ',': 'open_settings',
            };
            var action = actions[e.key];
            if (e.ctrlKey && action) {
                e.preventDefault();
                var url = new URL(window.location);
                url.searchParams.set('kb_action', action);
                window.history.replaceState({}, '', url);
                window.dispatchEvent(new Event('popstate'));
            }
        });
        window.addEventListener('popstate', function() {
            var params = new URLSearchParams(window.location.search);
            var action = params.get('kb_action');
            if (action) {
                params.delete('kb_action');
                var url = new URL(window.location);
                url.search = params.toString();
                window.history.replaceState({}, '', url);
            }
        });
        </script>
        """, unsafe_allow_html=True)
        st.session_state._kb_injected = True


# ────────────────────────────────────────────── LAYOUT ───────────────────────

PAGE_ICONS = {
    "overview": "▣", "playground": "◉", "sessions": "◫",
    "providers": "◈", "templates": "◇", "config": "⚙",
    "security": "🛡", "audit": "⌁",
    "metrics": "◉", "traces": "⌁",
    "settings": "⚙",
}

PAGE_LABELS = {
    "overview": "Overview", "playground": "Playground", "sessions": "Sessions",
    "providers": "Providers", "templates": "Templates", "config": "Runtime Config",
    "security": "Security", "audit": "Audit Log",
    "metrics": "Metrics", "traces": "Traces",
    "settings": "Settings",
}

PAGE_SECTIONS = [
    ("WORKSPACE", ["overview", "playground", "sessions"]),
    ("RUNTIME", ["providers", "templates", "config"]),
    ("SECURITY", ["security", "audit"]),
    ("OBSERVABILITY", ["metrics", "traces"]),
    ("SYSTEM", ["settings"]),
]


def render_sidebar(active_page: str, online: bool = True,
                   provider: str = "Gemini", model: str = "gemini-2.5-flash"):
    status_cls = "online" if online else "offline"
    st.markdown(f'<div class="sidebar-brand">⚡ Brompt</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-subtitle">AI Runtime Control Plane</div>',
                unsafe_allow_html=True)

    for section_name, page_keys in PAGE_SECTIONS:
        st.markdown(f'<div class="sidebar-section">{section_name}</div>',
                    unsafe_allow_html=True)
        for key in page_keys:
            icon = PAGE_ICONS.get(key, "•")
            label = PAGE_LABELS.get(key, key)
            is_active = active_page == key
            btn = st.button(
                f"{icon} {label}",
                key=f"nav_{key}",
                use_container_width=True,
                type="secondary" if not is_active else "primary",
            )
            if btn:
                st.session_state.page = key
                st.rerun()

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="sidebar-footer">
        <div class="sidebar-footer-status">
            <span class="status-dot {status_cls}"></span> Runtime {status_cls.upper()}
        </div>
        <div class="sidebar-footer-provider">{provider} · {model}</div>
    </div>""", unsafe_allow_html=True)


def render_topbar(page_name: str, status: str = "ONLINE", provider: str = "Gemini"):
    label = PAGE_LABELS.get(page_name, page_name)
    status_cls = status.lower()
    st.markdown(f"""
    <div class="brompt-topbar">
        <div class="brompt-topbar-left">
            <strong>Brompt</strong>
            <span class="brompt-topbar-sep">/</span>
            <span>{label}</span>
        </div>
        <div class="brompt-topbar-right">
            <span class="status-dot {status_cls}"></span> {status}
            <span>{provider}</span>
            <span class="brompt-topbar-kbd">⌘K</span>
        </div>
    </div>""", unsafe_allow_html=True)


def render_page_header(title: str, subtitle: Optional[str] = None,
                       actions: Optional[str] = None):
    html = f'<div style="margin-bottom:20px"><h1 style="font-size:24px;font-weight:700;color:var(--text-primary);margin:0">{title}</h1>'
    if subtitle:
        html += f'<p style="font-size:14px;color:var(--text-muted);margin:2px 0 0">{subtitle}</p>'
    if actions:
        html += f'<div style="margin-top:8px">{actions}</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_footer(version: str = "2.0.0"):
    st.markdown(f"""
    <div style="margin-top:40px;padding-top:12px;border-top:1px solid var(--border-soft);
                display:flex;justify-content:space-between;font-size:12px;color:var(--text-disabled)">
        <span>Brompt v{version}</span>
        <span>Production-Ready</span>
    </div>""", unsafe_allow_html=True)


# ────────────────────────────────────────────── PRIMITIVES ───────────────────

def render_card(title: Optional[str] = None, content: str = ""):
    t = f'<div class="brompt-card-title">{title}</div>' if title else ""
    st.markdown(f'<div class="brompt-card">{t}{content}</div>', unsafe_allow_html=True)


def render_panel(title: Optional[str] = None, content: str = ""):
    t = f'<div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px">{title}</div>' if title else ""
    st.markdown(f'<div style="background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:var(--space-5);margin:8px 0">{t}{content}</div>',
                unsafe_allow_html=True)


def render_metric_card(label: str, value: str, delta: Optional[str] = None,
                       caption: Optional[str] = None, delta_pos: bool = True):
    d = f'<div class="brompt-metric-delta {"pos" if delta_pos else "neg"}">{delta}</div>' if delta else ""
    c = f'<div class="brompt-metric-caption">{caption}</div>' if caption else ""
    st.markdown(f"""
    <div class="brompt-metric">
        <div class="brompt-metric-label">{label}</div>
        <div class="brompt-metric-value">{value}</div>
        {d}{c}
    </div>""", unsafe_allow_html=True)


def render_status_badge(label: str, status: str = "neutral"):
    cls_map = {"protected": "brompt-badge-protected", "exposed": "brompt-badge-exposed",
               "online": "brompt-badge-online", "offline": "brompt-badge-offline",
               "init": "brompt-badge-init"}
    cls = cls_map.get(status, "brompt-badge-offline")
    st.markdown(f'<span class="brompt-badge {cls}">{label}</span>', unsafe_allow_html=True)


def render_status_dot(status: str = "online"):
    st.markdown(f'<span class="status-dot {status}"></span>', unsafe_allow_html=True)


# ────────────────────────────────────────────── DATA COMPONENTS ──────────────

def render_provider_card(name: str, model: str, status: str, provider_type: str = "Cloud",
                         metrics: Optional[dict] = None):
    dot_cls = "online" if status in ("connected", "active", "available") else "offline"
    m = ""
    if metrics:
        m = '<div style="display:flex;gap:16px;margin-top:8px;font-size:12px;color:var(--text-muted)">'
        for k, v in metrics.items():
            m += f"<span>{k}: <strong style='color:var(--text-secondary)'>{v}</strong></span>"
        m += "</div>"
    st.markdown(f"""
    <div class="brompt-card" style="display:flex;align-items:center;justify-content:space-between;cursor:pointer">
        <div>
            <div style="font-size:14px;font-weight:600;color:var(--text-primary)">{name}</div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:2px">{model} · {provider_type}</div>
            {m}
        </div>
        <div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted)">
            <span class="status-dot {dot_cls}"></span> {status.title()}
        </div>
    </div>""", unsafe_allow_html=True)


def render_session_card(session_id: str, provider: str, msg_count: int,
                        last_active: str, template: str = "chat"):
    st.markdown(f"""
    <div class="brompt-card" style="cursor:pointer">
        <div style="display:flex;justify-content:space-between;align-items:start">
            <div>
                <div style="font-size:14px;font-weight:600;color:var(--text-primary)">{session_id[:12]}...</div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:2px">
                    {provider} · {template} · {msg_count} messages
                </div>
            </div>
            <div style="font-size:11px;color:var(--text-disabled)">{last_active}</div>
        </div>
    </div>""", unsafe_allow_html=True)


def render_template_card(name: str, description: str, usage_count: int = 0,
                         avg_tokens: int = 0):
    st.markdown(f"""
    <div class="brompt-card" style="cursor:pointer">
        <div style="font-size:14px;font-weight:600;color:var(--text-primary)">{name}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:2px">{description}</div>
        <div style="display:flex;gap:16px;margin-top:6px;font-size:11px;color:var(--text-disabled)">
            <span>Used {usage_count} times</span>
            <span>Avg {avg_tokens} tokens</span>
        </div>
    </div>""", unsafe_allow_html=True)


def render_execution_row(execution: dict, idx: int = 0):
    eid = execution.get("id", f"#{idx}")
    prov = execution.get("provider", "—")
    lat = execution.get("timing", {}).get("total_ms", 0)
    inp = execution.get("tokens", {}).get("input", 0)
    out = execution.get("tokens", {}).get("output", 0)
    ok = execution.get("status") == "success"
    status_mark = "✓" if ok else "✗"
    st.markdown(f"""
    <div class="brompt-table-row" style="display:flex;align-items:center;gap:12px;padding:8px 12px;
                border-bottom:1px solid var(--border-soft);cursor:pointer;font-size:13px;
                transition:background var(--transition)">
        <span style="color:var(--text-disabled);font-family:'JetBrains Mono',monospace;font-size:12px">{eid}</span>
        <span style="color:var(--text-secondary);min-width:70px">{prov}</span>
        <span style="color:var(--text-muted);font-family:'JetBrains Mono',monospace">{lat:.0f}ms</span>
        <span style="color:var(--text-muted);font-size:12px">{inp} → {out} tok</span>
        <span style="margin-left:auto;color:{"var(--success)" if ok else "var(--danger)"}">{status_mark}</span>
    </div>""", unsafe_allow_html=True)


def render_trace_step(name: str, status: str, duration_ms: float,
                      detail: Optional[str] = None):
    dot_cls = {"completed": "pass", "running": "run", "error": "fail",
               "pending": "wait"}.get(status, "wait")
    check = "✓" if status == "completed" else "✗" if status == "error" else "→"
    time_str = f"{duration_ms:.0f}ms" if duration_ms > 0 else "<1ms"
    html = f"""
    <div class="brompt-trace-node">
        <div class="brompt-trace-dot {dot_cls}">{check}</div>
        <span class="brompt-trace-name">{name}</span>
        <span class="brompt-trace-time">{time_str}</span>
        <div class="brompt-trace-connector"></div>
    </div>"""
    if detail:
        html += f'<div class="brompt-trace-detail">{detail}</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_trace_pipeline(stages: list[dict], total_ms: float = 0):
    html = '<div class="brompt-trace">'
    for s in stages:
        html += f"""
        <div class="brompt-trace-node">
            <div class="brompt-trace-dot {"pass" if s.get("status")=="completed" else "run" if s.get("status")=="running" else "fail" if s.get("status")=="error" else "wait"}">
                {"✓" if s.get("status")=="completed" else "✗" if s.get("status")=="error" else "→"}
            </div>
            <span class="brompt-trace-name">{s.get("name","")}</span>
            <span class="brompt-trace-time">{s.get("time_ms",0):.0f}ms</span>
            <div class="brompt-trace-connector"></div>
        </div>"""
    html += f"""
    <div style="text-align:right;font-size:12px;color:var(--text-muted);margin-top:4px;padding-top:4px;border-top:1px solid var(--border-soft);font-family:'JetBrains Mono',monospace">
        Total: {total_ms:.0f}ms
    </div>""" if total_ms > 0 else ""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_security_summary(blocked: int = 0, redacted: int = 0,
                            rate_limited: int = 0, total_events: int = 0):
    st.markdown("""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0">
        <div class="brompt-metric">
            <div class="brompt-metric-label">Blocked</div>
            <div class="brompt-metric-value" style="color:var(--danger);font-size:24px">{}</div>
        </div>
        <div class="brompt-metric">
            <div class="brompt-metric-label">Redacted</div>
            <div class="brompt-metric-value" style="color:var(--warning);font-size:24px">{}</div>
        </div>
        <div class="brompt-metric">
            <div class="brompt-metric-label">Rate Limited</div>
            <div class="brompt-metric-value" style="color:var(--warning);font-size:24px">{}</div>
        </div>
        <div class="brompt-metric">
            <div class="brompt-metric-label">Events</div>
            <div class="brompt-metric-value" style="color:var(--text-primary);font-size:24px">{}</div>
        </div>
    </div>""".format(blocked, redacted, rate_limited, total_events), unsafe_allow_html=True)


def render_audit_entry(entry: dict):
    ts = entry.get("timestamp", "")
    if isinstance(ts, (int, float)):
        import time as tm
        ts = tm.strftime("%H:%M:%S", tm.localtime(ts))
    else:
        ts = str(ts)[:8]
    event = entry.get("event", "—")
    secure = entry.get("is_secure", False)
    h = entry.get("entry_hash", entry.get("hash", ""))[:8]
    status_icon = "✓" if secure else "✗"
    status_cls = "var(--success)" if secure else "var(--danger)"
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;padding:7px 12px;border-bottom:1px solid var(--border-soft);font-size:13px;cursor:pointer;transition:background var(--transition)">
        <span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-muted);min-width:60px">{ts}</span>
        <span style="color:var(--text-secondary);flex:1">{event}</span>
        <span style="color:{status_cls}">{status_icon}</span>
        <span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-disabled)">{h}...</span>
    </div>""", unsafe_allow_html=True)


def render_audit_integrity(verified: bool, count: int):
    status_icon = "●" if verified else "✗"
    status_text = "VERIFIED" if verified else "COMPROMISED"
    status_cls = "var(--success)" if verified else "var(--danger)"
    st.markdown(f"""
    <div class="brompt-card" style="display:flex;align-items:center;justify-content:space-between">
        <div>
            <div style="font-size:14px;font-weight:600;color:var(--text-primary)">Audit Chain</div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:2px">{count} entries · SHA-256</div>
        </div>
        <div style="text-align:right">
            <div style="font-size:16px;font-weight:700;color:{status_cls}">{status_icon} {status_text}</div>
        </div>
    </div>""", unsafe_allow_html=True)


# ────────────────────────────────────────────── EXECUTION DRAWER ─────────────

def render_execution_drawer(execution: dict, on_close_key: str = "close_drawer"):
    if not execution:
        return
    eid = execution.get("id", "#?")
    status = execution.get("status", "?")
    ok = status == "success"
    status_cls = "var(--success)" if ok else "var(--danger)"
    status_text = "SUCCESS" if ok else "FAILED"

    st.markdown(f"""
    <div class="brompt-drawer-overlay">
    <div class="brompt-drawer">
        <button class="brompt-drawer-close" onclick="document.querySelector('.brompt-drawer-overlay').style.display='none'">✕</button>
        <div style="font-size:18px;font-weight:700;color:var(--text-primary);margin-bottom:4px">Execution {eid}</div>
        <div style="font-size:13px;color:{status_cls};margin-bottom:var(--space-5)">{status_text} · {execution.get('timing',{}).get('total_ms',0):.0f}ms</div>

        <hr class="brompt-drawer-divider">
        <div class="brompt-drawer-section">
            <div class="brompt-drawer-label">Provider</div>
            <div class="brompt-drawer-value">{execution.get('provider','—')} · {execution.get('model','—')}</div>
        </div>
        <div class="brompt-drawer-section">
            <div class="brompt-drawer-label">Timing</div>
            <div class="brompt-drawer-value">Total: {execution.get('timing',{}).get('total_ms',0):.0f}ms · Provider: {execution.get('timing',{}).get('provider_ms',0):.0f}ms</div>
        </div>
        <div class="brompt-drawer-section">
            <div class="brompt-drawer-label">Tokens</div>
            <div class="brompt-drawer-value">Input: {execution.get('tokens',{}).get('input',0):,} · Output: {execution.get('tokens',{}).get('output',0):,} · Saved: {execution.get('tokens',{}).get('saved',0):,}</div>
        </div>
        <div class="brompt-drawer-section">
            <div class="brompt-drawer-label">Security</div>
            <div class="brompt-drawer-value">Input: {execution.get('security',{}).get('input','—')} · Output: {execution.get('security',{}).get('output','—')}</div>
        </div>
        <div class="brompt-drawer-section">
            <div class="brompt-drawer-label">Audit</div>
            <div class="brompt-drawer-value">Recorded: {'✓' if execution.get('audit',{}).get('recorded') else '✗'} · Verified: {'✓' if execution.get('audit',{}).get('verified') else '✗'}</div>
        </div>

        <hr class="brompt-drawer-divider">
        <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px">Pipeline Trace</div>
    """)
    stages = execution.get("trace", [])
    for s in stages:
        render_trace_step(s.get("name",""), s.get("status","completed"), s.get("time_ms",0))
    st.markdown("</div></div>", unsafe_allow_html=True)

    if st.button("Close", key=on_close_key):
        st.session_state.execution_detail = None
        st.rerun()


def render_time_range_selector(key_suffix: str = ""):
    sel = st.segmented_control(
        "Time range", ["5m", "1h", "24h", "7d"],
        default="1h", key=f"time_range_{key_suffix}",
        label_visibility="collapsed",
    )
    return sel


def render_session_search(key_suffix: str = ""):
    search = st.text_input("Search sessions", placeholder="Search sessions...",
                           key=f"sess_search_{key_suffix}",
                           label_visibility="collapsed")
    return search or ""


def render_shortcuts_hint(visible: bool = False):
    cls = "brompt-shortcuts-hint visible" if visible else "brompt-shortcuts-hint"
    st.markdown(f"""
    <div class="{cls}">
        <div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:6px">Keyboard Shortcuts</div>
        <div class="brompt-shortcuts-item"><span>Command Palette</span><kbd>⌘K</kbd></div>
        <div class="brompt-shortcuts-item"><span>New Session</span><kbd>Ctrl+N</kbd></div>
        <div class="brompt-shortcuts-item"><span>Clear</span><kbd>Ctrl+L</kbd></div>
        <div class="brompt-shortcuts-item"><span>Settings</span><kbd>Ctrl+,</kbd></div>
    </div>""", unsafe_allow_html=True)


# ────────────────────────────────────────────── FEEDBACK ─────────────────────

def render_empty_state(title: str, description: str, action_label: Optional[str] = None):
    html = f"""
    <div style="text-align:center;padding:48px 24px;color:var(--text-muted)">
        <div style="font-size:15px;font-weight:600;color:var(--text-secondary)">{title}</div>
        <p style="font-size:13px;margin-top:4px">{description}</p>
    </div>"""
    st.markdown(html, unsafe_allow_html=True)
    if action_label:
        st.button(action_label, key=f"empty_action_{title[:8]}")


def render_error_state(title: str, description: str, action_label: Optional[str] = None,
                       detail: Optional[str] = None):
    html = f"""
    <div style="padding:24px;background:var(--danger-soft);border:1px solid rgba(239,68,68,.2);border-radius:var(--radius-lg);margin:12px 0">
        <div style="font-size:15px;font-weight:600;color:var(--danger)">{title}</div>
        <p style="font-size:13px;color:var(--text-secondary);margin-top:4px">{description}</p>
    </div>"""
    st.markdown(html, unsafe_allow_html=True)
    if detail:
        with st.expander("Technical Details"):
            st.code(detail, language="text")
    if action_label:
        st.button(action_label, key=f"error_action_{title[:8]}")


def render_loading_state(pipeline_steps: list[str]):
    lines = '<div class="brompt-trace" style="padding:16px">'
    for i, step in enumerate(pipeline_steps):
        status = "running" if i == 0 else "pending"
        dot_cls = "run" if status == "running" else "wait"
        check = "→" if status == "running" else "○"
        lines += f"""
        <div class="brompt-trace-node">
            <div class="brompt-trace-dot {dot_cls}">{check}</div>
            <span class="brompt-trace-name">{step}</span>
            <div class="brompt-trace-connector"></div>
        </div>"""
    lines += "</div>"
    st.markdown(lines, unsafe_allow_html=True)


# ────────────────────────────────────────────── COMMAND PALETTE ──────────────

COMMANDS = [
    ("Go to Overview", "overview"), ("Go to Playground", "playground"),
    ("New Session", "sessions"), ("Open Providers", "providers"),
    ("Open Security", "security"), ("Open Audit", "audit"),
    ("View Metrics", "metrics"), ("View Traces", "traces"),
    ("Runtime Config", "config"), ("Settings", "settings"),
    ("Verify Audit", "audit"), ("Refresh Runtime", "overview"),
]


def render_command_palette():
    import re as _re
    search = st.text_input("Command search", placeholder="Search commands...",
                           key="_cmd_palette_search", label_visibility="collapsed")
    query = (search or "").lower()
    for label, page_key in COMMANDS:
        if query and query not in label.lower():
            continue
        if st.button(label, key=f"cmd_{page_key}", use_container_width=True):
            st.session_state.page = page_key
            st.session_state._cmd_palette_search = ""
            st.rerun()


# ────────────────────────────────────────────── TOAST HELPERS ────────────────

def show_success_toast(message: str): st.toast(message, icon="✅")
def show_error_toast(message: str): st.toast(message, icon="❌")
def show_info_toast(message: str): st.toast(message, icon="ℹ️")
