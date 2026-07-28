"""UI construction helpers — tabs, toolbar, title bar, resize grip, keyboard bindings."""

import tkinter as tk

from .theme import BG, BG_CARD, BG_HEADER, BORDER, CYAN, GREEN, MUTED, RED, TEXT

DOCS_TEXT = """
  BROMPT ENGINE — QUICK REFERENCE
  ═══════════════════════════════

  CLI COMMANDS
  ─────────────────────────────────────
  help       Show this help
  status     Engine status & provider
  history    Turn history
  audit      Audit log + chain check
  clear      Flush memory
  exit       Shut down

  QUICK START
  ─────────────────────────────────────
  > python -m brompt.cli
  > brompt > What is 2+2?
  > brompt > My name is Bob
  > brompt > What is my name?
  > brompt > exit

  TABS
  ─────────────────────────────────────
  Docs   This reference
  Live   Engine status, memory, audit
  Chart  Secure/Rejected bars + trend

  7-STAGE PIPELINE
  ─────────────────────────────────────
  1. Rate Limiter       (per-caller)
  2. Security Ingress   (regex filter)
  3. Bounded History    (deque max N)
  4. Schema Validator   (Pydantic v2)
  5. Provider Call      (6 providers)
  6. Output Sanitizer   (redact keys)
  7. Audit Log          (SHA-256 chain)

  PROVIDERS
  ─────────────────────────────────────
  Provider      Env Variable         Type
  ─────────     ──────────────       ────
  Anthropic     ANTHROPIC_API_KEY    Cloud
  OpenAI        OPENAI_API_KEY       Cloud
  Ollama        OLLAMA_HOST          Local
  Gemini        GEMINI_API_KEY       Cloud
  Mistral       MISTRAL_API_KEY      Cloud
  Azure OpenAI  AZURE_OPENAI_*       Cloud
  LM Studio     LM_STUDIO_HOST       Local

  CONFIGURATION (agent.brompt.yaml)
  ─────────────────────────────────────
  security_policy:
    isolation_level: ZERO_TRUST
    sanitize_inputs: true
    max_payload_size_kb: 64
  memory_strategy:
    paging_mode: VIRTUAL_STATE_O1
    max_history_turns: 3
  rate_limit:
    max_requests: 30
    window_seconds: 60

  GitHub: github.com/sh0-dax/Brompt
  Author: SH Azzouz
"""

TAB_NAMES = ["docs", "live", "chart"]
CHART_TYPES = ["bar", "line", "area", "stacked", "donut"]
DATA_SERIES = ["activity", "latency", "tokens"]


def build_title_bar(parent, on_mini, on_hide):
    """Returns (title_frame, status_label)."""
    frame = tk.Frame(parent, bg=BG_HEADER, height=36)
    frame.pack(fill=tk.X)
    frame.pack_propagate(False)

    label = tk.Label(frame, text="  Brompt Engine",
                     bg=BG_HEADER, fg=CYAN,
                     font=("Consolas", 11, "bold"), anchor="w")
    label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    btn_frame = tk.Frame(frame, bg=BG_HEADER)
    btn_frame.pack(side=tk.RIGHT)

    mini_btn = tk.Button(btn_frame, text="—", bg=BG_HEADER, fg=MUTED,
                         bd=0, activebackground=BORDER, activeforeground=TEXT,
                         font=("Consolas", 12), width=3, command=on_mini)
    mini_btn.pack(side=tk.LEFT)

    close_btn = tk.Button(btn_frame, text="✕", bg=BG_HEADER, fg=MUTED,
                          bd=0, activebackground=RED, activeforeground=TEXT,
                          font=("Consolas", 12), width=3, command=on_hide)
    close_btn.pack(side=tk.LEFT)

    return frame, label


def build_tab_bar(parent, on_switch, get_active):
    """Returns dict of tab buttons keyed by tab name."""
    frame = tk.Frame(parent, bg=BG, height=32)
    frame.pack(fill=tk.X)
    frame.pack_propagate(False)

    sep = tk.Frame(parent, bg=BORDER, height=1)
    sep.pack(fill=tk.X)

    buttons = {}
    for i, name in enumerate(TAB_NAMES):
        btn = tk.Button(frame, text=f" {name.title()} ",
                        bg=BG_CARD, fg=MUTED, bd=0,
                        font=("Consolas", 10, "bold"),
                        command=lambda n=name: on_switch(n))
        btn.pack(side=tk.LEFT, padx=(10 if i == 0 else 2, 2), pady=6)
        buttons[name] = btn

    status = tk.Label(frame, text="● dry-run", bg=BG, fg=MUTED,
                      font=("Consolas", 9), anchor="e")
    status.pack(side=tk.RIGHT, padx=10)

    return buttons, status, frame


def build_chart_toolbar(parent, chart_engine, on_redraw):
    """Returns the toolbar frame containing chart type + data series buttons."""
    bar = tk.Frame(parent, bg=BG, height=26)
    bar.pack(fill=tk.X)
    bar.pack_propagate(False)

    type_buttons = {}
    for ct in CHART_TYPES:
        sym = {"bar": "▇", "line": "╱", "area": "▨", "stacked": "▤", "donut": "◉"}[ct]
        btn = tk.Button(bar, text=sym, bg=BG_CARD, fg=MUTED, bd=0,
                        font=("Consolas", 10), width=3,
                        command=lambda t=ct: _set_chart_type(t, chart_engine, type_buttons, on_redraw))
        btn.pack(side=tk.LEFT, padx=1, pady=2)
        type_buttons[ct] = btn

    tk.Frame(bar, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=3)

    series_buttons = {}
    for ds in DATA_SERIES:
        btn = tk.Button(bar, text=ds[0].upper(), bg=BG_CARD, fg=MUTED, bd=0,
                        font=("Consolas", 8), width=4,
                        command=lambda s=ds: _set_data_series(s, chart_engine, series_buttons, on_redraw))
        btn.pack(side=tk.LEFT, padx=1, pady=2)
        series_buttons[ds] = btn

    type_buttons[chart_engine.chart_type].configure(bg=CYAN, fg="#000000")
    series_buttons[chart_engine.data_series].configure(bg=CYAN, fg="#000000")

    return bar, type_buttons, series_buttons


def _set_chart_type(t, chart_engine, type_buttons, on_redraw):
    chart_engine.set_type(t)
    for ct, btn in type_buttons.items():
        btn.configure(bg=CYAN if ct == t else BG_CARD,
                      fg="#000000" if ct == t else MUTED)
    on_redraw()


def _set_data_series(s, chart_engine, series_buttons, on_redraw):
    chart_engine.set_series(s)
    for ds, btn in series_buttons.items():
        btn.configure(bg=CYAN if ds == s else BG_CARD,
                      fg="#000000" if ds == s else MUTED)
    on_redraw()


def build_content_area(parent):
    """Returns dict with 'docs_text', 'docs_scroll', 'live_text',
    'live_scroll', 'chart_canvas' widgets."""
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    docs_text = tk.Text(frame, bg=BG, fg=TEXT, insertbackground=TEXT,
                        selectbackground=CYAN, selectforeground="#000000",
                        font=("Consolas", 10), bd=0, wrap=tk.WORD,
                        padx=12, pady=10, spacing1=1, spacing3=1)
    docs_scroll = tk.Scrollbar(frame, command=docs_text.yview)
    docs_text.configure(yscrollcommand=docs_scroll.set)
    docs_text.insert("1.0", DOCS_TEXT.strip())
    docs_text.configure(state=tk.DISABLED)

    live_text = tk.Text(frame, bg=BG, fg=TEXT, insertbackground=TEXT,
                        selectbackground=CYAN, selectforeground="#000000",
                        font=("Consolas", 10), bd=0, wrap=tk.WORD,
                        padx=12, pady=10, spacing1=1, spacing3=1)
    live_scroll = tk.Scrollbar(frame, command=live_text.yview)
    live_text.configure(yscrollcommand=live_scroll.set)
    live_text.configure(state=tk.DISABLED)

    chart_canvas = tk.Canvas(frame, bg=BG, bd=0, highlightthickness=0)

    return {
        "frame": frame,
        "docs_text": docs_text,
        "docs_scroll": docs_scroll,
        "live_text": live_text,
        "live_scroll": live_scroll,
        "chart_canvas": chart_canvas,
    }


def build_resize_grip(parent, root, on_drag_start, on_drag):
    grip = tk.Label(parent, text="▟", bg=BG, fg=BORDER,
                    font=("Consolas", 10), cursor="size_nw_se")
    grip.place(relx=1.0, rely=1.0, anchor="se")
    grip.bind("<Button-1>", on_drag_start)
    grip.bind("<B1-Motion>", on_drag)
    return grip


def bind_keyboard(root, bindings: dict):
    """bindings: {(modifiers, key): callback}"""
    for (mod, key), cb in bindings.items():
        seq = f"<{mod}-{key}>" if mod else f"<{key}>"
        root.bind_all(seq, lambda e, c=cb: c())
