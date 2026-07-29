"""
Modern UI Design System for Brompt Widget
Complete visual styling with animations and responsive design
"""

import streamlit as st
from typing import Optional


def inject_design_system():
    """Inject complete design system CSS"""
    st.markdown("""
    <style>
    /* ============================================================
       DESIGN TOKENS
       ============================================================ */
    :root {
        --color-primary: #6366f1;
        --color-primary-hover: #4f46e5;
        --color-primary-light: rgba(99, 102, 241, 0.1);
        --color-secondary: #8b5cf6;
        --color-success: #10b981;
        --color-success-light: rgba(16, 185, 129, 0.1);
        --color-warning: #f59e0b;
        --color-danger: #ef4444;
        --color-dark: #0f172a;
        --color-surface: rgba(255, 255, 255, 0.03);
        --color-border: rgba(255, 255, 255, 0.06);
        --radius-lg: 20px;
        --radius-md: 14px;
        --radius-sm: 10px;
        --radius-xs: 8px;
        --shadow-sm: 0 2px 8px rgba(0,0,0,0.06);
        --shadow-md: 0 8px 24px rgba(0,0,0,0.08);
        --shadow-lg: 0 16px 48px rgba(0,0,0,0.12);
        --transition-fast: 0.15s ease;
        --transition-normal: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* ============================================================
       TYPOGRAPHY
       ============================================================ */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

    * { font-family: 'Inter', -apple-system, sans-serif; }
    code, pre, .mono { font-family: 'JetBrains Mono', monospace; }

    /* ============================================================
       HERO SECTION - Gradient with animation
       ============================================================ */
    .brompt-hero {
        background: linear-gradient(135deg, #6366f1, #8b5cf6, #a855f7, #6366f1);
        background-size: 300% 300%;
        animation: heroGradient 6s ease infinite;
        border-radius: var(--radius-lg);
        padding: 2.5rem 2rem;
        text-align: center;
        position: relative;
        overflow: hidden;
        margin-bottom: 1.5rem;
        box-shadow: var(--shadow-lg);
    }

    @keyframes heroGradient {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }

    .brompt-hero::after {
        content: '';
        position: absolute;
        inset: 0;
        background: radial-gradient(ellipse at center, rgba(255,255,255,0.15) 0%, transparent 70%);
    }

    .brompt-hero-content {
        position: relative;
        z-index: 1;
    }

    .brompt-hero-title {
        font-size: 2.5rem;
        font-weight: 900;
        color: white;
        letter-spacing: -0.5px;
    }

    .brompt-hero-subtitle {
        font-size: 1rem;
        color: rgba(255,255,255,0.85);
        margin-top: 0.5rem;
    }

    /* ============================================================
       STAT CARDS - Hero metrics
       ============================================================ */
    .brompt-stats-row {
        display: flex;
        gap: 1rem;
        justify-content: center;
        margin-top: 1.5rem;
        flex-wrap: wrap;
    }

    .brompt-stat-card {
        background: rgba(255, 255, 255, 0.12);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: var(--radius-md);
        padding: 1rem 1.5rem;
        text-align: center;
        min-width: 110px;
        transition: var(--transition-normal);
        cursor: default;
    }

    .brompt-stat-card:hover {
        background: rgba(255, 255, 255, 0.2);
        transform: translateY(-3px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.2);
    }

    .brompt-stat-value {
        font-size: 1.8rem;
        font-weight: 800;
        color: white;
    }

    .brompt-stat-label {
        font-size: 0.75rem;
        color: rgba(255,255,255,0.75);
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 2px;
    }

    /* ============================================================
       CHAT MESSAGES
       ============================================================ */
    .brompt-chat-msg {
        animation: msgSlideIn 0.3s ease-out;
        margin-bottom: 0.5rem;
    }

    @keyframes msgSlideIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* ============================================================
       BADGES - Savings, Detection, Template
       ============================================================ */
    .brompt-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.84rem;
        font-weight: 500;
        backdrop-filter: blur(8px);
        transition: var(--transition-fast);
    }

    .brompt-badge-savings {
        background: var(--color-success-light);
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #34d399;
        animation: badgePulse 2s ease-in-out infinite;
    }

    @keyframes badgePulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.2); }
        50% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
    }

    .brompt-badge-detect {
        background: var(--color-primary-light);
        border: 1px solid rgba(99, 102, 241, 0.25);
        color: #818cf8;
    }

    .brompt-badge-template {
        background: rgba(139, 92, 246, 0.1);
        border: 1px solid rgba(139, 92, 246, 0.2);
        color: #a78bfa;
    }

    .brompt-badge-model {
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.2);
        color: #fbbf24;
    }

    .brompt-badge-cache {
        background: rgba(59, 130, 246, 0.1);
        border: 1px solid rgba(59, 130, 246, 0.2);
        color: #60a5fa;
    }

    /* ============================================================
       PROGRESS BAR - Token usage
       ============================================================ */
    .brompt-progress {
        height: 8px;
        background: rgba(255,255,255,0.06);
        border-radius: 4px;
        overflow: hidden;
    }

    .brompt-progress-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
        background: linear-gradient(90deg, #10b981, #34d399);
    }

    /* ============================================================
       TOAST NOTIFICATION
       ============================================================ */
    .brompt-toast {
        position: fixed;
        top: 24px;
        right: 24px;
        z-index: 9999;
        background: rgba(15, 23, 42, 0.95);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: var(--radius-sm);
        padding: 14px 20px;
        color: white;
        font-size: 0.9rem;
        animation: toastIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    }

    @keyframes toastIn {
        from { transform: translateX(120%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }

    /* ============================================================
       SIDEBAR STYLING
       ============================================================ */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.98));
        border-right: 1px solid rgba(255,255,255,0.06);
    }

    /* ============================================================
       BUTTONS
       ============================================================ */
    .stButton > button {
        border-radius: var(--radius-xs) !important;
        font-weight: 500 !important;
        transition: var(--transition-fast) !important;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: var(--shadow-sm);
    }

    /* ============================================================
       RESPONSIVE
       ============================================================ */
    @media (max-width: 768px) {
        .brompt-hero-title { font-size: 1.8rem; }
        .brompt-stats-row { gap: 0.5rem; }
        .brompt-stat-card { padding: 0.7rem 1rem; min-width: 80px; }
        .brompt-stat-value { font-size: 1.4rem; }
    }
    </style>
    """, unsafe_allow_html=True)


def render_hero_section(
    total_requests: int = 0,
    tokens_saved: int = 0,
    cost_saved: float = 0.0,
    active_template: str = "default",
):
    """Render animated hero section with live stats"""
    st.markdown(f"""
    <div class="brompt-hero">
        <div class="brompt-hero-content">
            <div class="brompt-hero-title">🚀 Brompt</div>
            <div class="brompt-hero-subtitle">Intelligent Prompt Engine</div>
            <div class="brompt-stats-row">
                <div class="brompt-stat-card">
                    <div class="brompt-stat-value">{total_requests}</div>
                    <div class="brompt-stat-label">Requests</div>
                </div>
                <div class="brompt-stat-card">
                    <div class="brompt-stat-value">{tokens_saved:,}</div>
                    <div class="brompt-stat-label">Tokens Saved</div>
                </div>
                <div class="brompt-stat-card">
                    <div class="brompt-stat-value">${cost_saved:.4f}</div>
                    <div class="brompt-stat-label">Cost Saved</div>
                </div>
                <div class="brompt-stat-card">
                    <div class="brompt-stat-value">{active_template}</div>
                    <div class="brompt-stat-label">Template</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_savings_badge(tokens: int, cost: float):
    """Render animated savings badge"""
    st.markdown(f"""
    <span class="brompt-badge brompt-badge-savings">
        💰 Saved {tokens:,} tokens (${cost:.4f})
    </span>
    """, unsafe_allow_html=True)


def render_cached_badge():
    """Render cached result badge"""
    st.markdown("""
    <span class="brompt-badge brompt-badge-cache">
        💾 Cached
    </span>
    """, unsafe_allow_html=True)


def render_detection_badge(task: str, model: str, template: str, confidence: float):
    """Render auto-detection result"""
    confidence_color = "#34d399" if confidence > 0.8 else "#f59e0b" if confidence > 0.5 else "#ef4444"
    st.markdown(f"""
    <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0;">
        <span class="brompt-badge brompt-badge-detect">
            🧠 {task} <span style="color:{confidence_color}">({confidence:.0%})</span>
        </span>
        <span class="brompt-badge brompt-badge-model">
            ⚡ {model}
        </span>
        <span class="brompt-badge brompt-badge-template">
            📋 {template}
        </span>
    </div>
    """, unsafe_allow_html=True)


def render_progress_bar(used: int, total: int, label: str = "Tokens"):
    """Render styled progress bar"""
    pct = min(used / total * 100, 100) if total > 0 else 0
    color = "#10b981" if pct < 50 else "#f59e0b" if pct < 80 else "#ef4444"

    st.markdown(f"""
    <div style="margin: 4px 0;">
        <div style="display: flex; justify-content: space-between; font-size: 0.78rem; color: #94a3b8; margin-bottom: 4px;">
            <span>{label}</span>
            <span>{used:,} / {total:,} ({pct:.0f}%)</span>
        </div>
        <div class="brompt-progress">
            <div class="brompt-progress-fill" style="width: {pct}%; background: {color};"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_card(content: str, title: str = None):
    """Render a glass-morphism card"""
    title_html = f'<div style="font-weight:600; margin-bottom:8px; color:#e2e8f0;">{title}</div>' if title else ''
    st.markdown(f"""
    <div style="
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin: 0.5rem 0;
    ">
        {title_html}
        {content}
    </div>
    """, unsafe_allow_html=True)


def show_success_toast(message: str):
    """Show success notification"""
    st.toast(message, icon="✅")


def show_savings_toast(tokens: int, percent: float):
    """Show savings notification"""
    st.toast(f"💰 Saved {tokens:,} tokens ({percent:.0f}%)", icon="💰")


def show_error_toast(message: str):
    """Show error notification"""
    st.toast(message, icon="❌")


def show_info_toast(message: str):
    """Show info notification"""
    st.toast(message, icon="ℹ️")
