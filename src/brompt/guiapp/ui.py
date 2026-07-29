"""UI construction helpers — tabs, toolbar, title bar, resize grip, keyboard bindings."""

import tkinter as tk
from tkinter import ttk

from .theme import BG, BG_CARD, BG_HEADER, BORDER, CYAN, GREEN, MUTED, RED, TEXT, INPUT_BG

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
  Docs      This reference
  Live      Engine + savings + templates
  Chart     Secure/Rejected bars + trend
  Chat      Send prompts to the engine
  Settings  Provider, API key, config

  7-STAGE PIPELINE
  ─────────────────────────────────────
  1. Rate Limiter       (per-caller)
  2. Security Ingress   (regex filter)
  3. Bounded History    (deque max N)
  4. Schema Validator   (Pydantic v2)
  5. Provider Call      (7 providers)
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

TAB_NAMES = ["docs", "live", "chart", "chat", "settings"]
CHART_TYPES = ["bar", "line", "area", "stacked", "donut"]
DATA_SERIES = ["activity", "latency", "tokens"]
PROVIDER_NAMES = [
    "Gemini", "OpenAI", "Anthropic", "Mistral",
    "Azure OpenAI", "Ollama", "LM Studio",
]


def build_title_bar(parent, on_mini, on_hide):
    """Returns (title_frame, status_label)."""
    frame = tk.Frame(parent, bg=BG_HEADER, height=36)
    frame.pack(fill=tk.X)
    frame.pack_propagate(False)

    label = tk.Label(
        frame, text="  Brompt Engine",
        bg=BG_HEADER, fg=CYAN,
        font=("Consolas", 11, "bold"), anchor="w",
    )
    label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    btn_frame = tk.Frame(frame, bg=BG_HEADER)
    btn_frame.pack(side=tk.RIGHT)

    mini_btn = tk.Button(
        btn_frame, text="—", bg=BG_HEADER, fg=MUTED,
        bd=0, activebackground=BORDER, activeforeground=TEXT,
        font=("Consolas", 12), width=3, command=on_mini,
    )
    mini_btn.pack(side=tk.LEFT)

    close_btn = tk.Button(
        btn_frame, text="✕", bg=BG_HEADER, fg=MUTED,
        bd=0, activebackground=RED, activeforeground=TEXT,
        font=("Consolas", 12), width=3, command=on_hide,
    )
    close_btn.pack(side=tk.LEFT)

    return frame, label, mini_btn, close_btn


def build_tab_bar(parent, on_switch, get_active):
    """Returns dict of tab buttons keyed by tab name."""
    frame = tk.Frame(parent, bg=BG, height=32)
    frame.pack(fill=tk.X)
    frame.pack_propagate(False)

    sep = tk.Frame(parent, bg=BORDER, height=1)
    sep.pack(fill=tk.X)

    buttons = {}
    for i, name in enumerate(TAB_NAMES):
        short = {"docs": "Docs", "live": "Live", "chart": "Chart",
                 "chat": "Chat", "settings": "Set"}[name]
        btn = tk.Button(
            frame, text=f" {short} ",
            bg=BG_CARD, fg=MUTED, bd=0,
            font=("Consolas", 9, "bold"),
            command=lambda n=name: on_switch(n),
        )
        btn.pack(side=tk.LEFT, padx=(10 if i == 0 else 2, 2), pady=6)
        buttons[name] = btn

    status = tk.Label(
        frame, text="● dry-run", bg=BG, fg=MUTED,
        font=("Consolas", 9), anchor="e",
    )
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
        btn = tk.Button(
            bar, text=sym, bg=BG_CARD, fg=MUTED, bd=0,
            font=("Consolas", 10), width=3,
            command=lambda t=ct: _set_chart_type(t, chart_engine, type_buttons, on_redraw),
        )
        btn.pack(side=tk.LEFT, padx=1, pady=2)
        type_buttons[ct] = btn

    tk.Frame(bar, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=3)

    series_buttons = {}
    for ds in DATA_SERIES:
        btn = tk.Button(
            bar, text=ds[0].upper(), bg=BG_CARD, fg=MUTED, bd=0,
            font=("Consolas", 8), width=4,
            command=lambda s=ds: _set_data_series(s, chart_engine, series_buttons, on_redraw),
        )
        btn.pack(side=tk.LEFT, padx=1, pady=2)
        series_buttons[ds] = btn

    type_buttons[chart_engine.chart_type].configure(bg=CYAN, fg="#000000")
    series_buttons[chart_engine.data_series].configure(bg=CYAN, fg="#000000")

    return bar, type_buttons, series_buttons


def _set_chart_type(t, chart_engine, type_buttons, on_redraw):
    chart_engine.set_type(t)
    for ct, btn in type_buttons.items():
        btn.configure(
            bg=CYAN if ct == t else BG_CARD,
            fg="#000000" if ct == t else MUTED,
        )
    on_redraw()


def _set_data_series(s, chart_engine, series_buttons, on_redraw):
    chart_engine.set_series(s)
    for ds, btn in series_buttons.items():
        btn.configure(
            bg=CYAN if ds == s else BG_CARD,
            fg="#000000" if ds == s else MUTED,
        )
    on_redraw()


def build_content_area(parent):
    """Returns dict of content widgets for all tabs."""
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill=tk.BOTH, expand=True)

    # --- Docs ---
    docs_text = tk.Text(
        frame, bg=BG, fg=TEXT, insertbackground=TEXT,
        selectbackground=CYAN, selectforeground="#000000",
        font=("Consolas", 10), bd=0, wrap=tk.WORD,
        padx=12, pady=10, spacing1=1, spacing3=1,
    )
    docs_scroll = tk.Scrollbar(frame, command=docs_text.yview)
    docs_text.configure(yscrollcommand=docs_scroll.set)
    docs_text.insert("1.0", DOCS_TEXT.strip())
    docs_text.configure(state=tk.DISABLED)

    # --- Live ---
    live_text = tk.Text(
        frame, bg=BG, fg=TEXT, insertbackground=TEXT,
        selectbackground=CYAN, selectforeground="#000000",
        font=("Consolas", 10), bd=0, wrap=tk.WORD,
        padx=12, pady=10, spacing1=1, spacing3=1,
    )
    live_scroll = tk.Scrollbar(frame, command=live_text.yview)
    live_text.configure(yscrollcommand=live_scroll.set)
    live_text.configure(state=tk.DISABLED)

    # --- Chart ---
    chart_canvas = tk.Canvas(frame, bg=BG, bd=0, highlightthickness=0)

    # --- Chat ---
    chat_frame = tk.Frame(frame, bg=BG)
    chat_text = tk.Text(
        chat_frame, bg=BG, fg=TEXT, insertbackground=TEXT,
        selectbackground=CYAN, selectforeground="#000000",
        font=("Consolas", 10), bd=0, wrap=tk.WORD,
        padx=8, pady=6, spacing1=1, spacing3=1,
    )
    chat_scroll = tk.Scrollbar(chat_frame, command=chat_text.yview)
    chat_text.configure(yscrollcommand=chat_scroll.set)
    chat_text.configure(state=tk.DISABLED)

    chat_bottom = tk.Frame(chat_frame, bg=BG, height=34)
    chat_entry = tk.Entry(
        chat_bottom, bg=BG_CARD, fg=TEXT, insertbackground=TEXT,
        font=("Consolas", 10), bd=1, relief=tk.FLAT,
        disabledbackground=BG, disabledforeground=MUTED,
    )
    chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4), pady=4)
    chat_send_btn = tk.Button(
        chat_bottom, text="Send", bg=CYAN, fg="#000000",
        font=("Consolas", 9, "bold"), bd=0, padx=8, cursor="hand2",
        activebackground="#4a90e0",
    )
    chat_send_btn.pack(side=tk.RIGHT, pady=4)

    # --- Settings ---
    settings_frame = tk.Frame(frame, bg=BG)
    settings_canvas = tk.Canvas(settings_frame, bg=BG, bd=0, highlightthickness=0)
    settings_scrollbar = tk.Scrollbar(settings_frame, orient=tk.VERTICAL, command=settings_canvas.yview)
    settings_inner = tk.Frame(settings_canvas, bg=BG)
    settings_canvas.configure(yscrollcommand=settings_scrollbar.set)

    settings_inner.bind(
        "<Configure>",
        lambda e: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")),
    )
    settings_canvas.create_window((0, 0), window=settings_inner, anchor="nw", tags="inner")
    settings_canvas.bind("<Configure>", lambda e: settings_canvas.itemconfig("inner", width=e.width))

    row = 0

    # Provider
    tk.Label(
        settings_inner, text="Provider", bg=BG, fg=MUTED,
        font=("Consolas", 9), anchor="w",
    ).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
    row += 1
    provider_var = tk.StringVar(value=PROVIDER_NAMES[0])
    provider_menu = ttk.Combobox(
        settings_inner, textvariable=provider_var,
        values=PROVIDER_NAMES, state="readonly",
        font=("Consolas", 9),
    )
    provider_menu.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
    row += 1

    # API Key
    tk.Label(
        settings_inner, text="API Key / Host", bg=BG, fg=MUTED,
        font=("Consolas", 9), anchor="w",
    ).grid(row=row, column=0, sticky="w", padx=8, pady=(6, 0))
    row += 1
    api_var = tk.StringVar()
    api_entry = tk.Entry(
        settings_inner, textvariable=api_var, show="*",
        bg=BG_CARD, fg=TEXT, insertbackground=TEXT,
        font=("Consolas", 10), bd=1, relief=tk.FLAT,
    )
    api_entry.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
    row += 1

    # Template
    tk.Label(
        settings_inner, text="Template", bg=BG, fg=MUTED,
        font=("Consolas", 9), anchor="w",
    ).grid(row=row, column=0, sticky="w", padx=8, pady=(6, 0))
    row += 1
    template_var = tk.StringVar()
    template_menu = ttk.Combobox(
        settings_inner, textvariable=template_var, state="readonly",
        font=("Consolas", 9),
    )
    template_menu.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
    row += 1

    # Config section
    tk.Label(
        settings_inner, text="Config (agent.brompt.yaml)", bg=BG, fg=MUTED,
        font=("Consolas", 9), anchor="w",
    ).grid(row=row, column=0, sticky="w", padx=8, pady=(12, 2))
    row += 1

    config_text = tk.Text(
        settings_inner, bg=BG_CARD, fg=TEXT, insertbackground=TEXT,
        selectbackground=CYAN, selectforeground="#000000",
        font=("Consolas", 9), bd=1, relief=tk.FLAT,
        padx=6, pady=6, height=12,
    )
    config_text.grid(row=row, column=0, sticky="nsew", padx=8, pady=2)
    settings_inner.grid_rowconfigure(row, weight=1)
    settings_inner.grid_columnconfigure(0, weight=1)
    row += 1

    save_btn = tk.Button(
        settings_inner, text=" Save Config ", bg=CYAN, fg="#000000",
        font=("Consolas", 9, "bold"), bd=0, padx=8, pady=3, cursor="hand2",
        activebackground="#4a90e0",
    )
    save_btn.grid(row=row, column=0, sticky="e", padx=8, pady=(4, 8))

    return {
        "frame": frame,
        "docs_text": docs_text,
        "docs_scroll": docs_scroll,
        "live_text": live_text,
        "live_scroll": live_scroll,
        "chart_canvas": chart_canvas,
        "chat_frame": chat_frame,
        "chat_text": chat_text,
        "chat_scroll": chat_scroll,
        "chat_bottom": chat_bottom,
        "chat_entry": chat_entry,
        "chat_send_btn": chat_send_btn,
        "settings_frame": settings_frame,
        "settings_canvas": settings_canvas,
        "settings_scrollbar": settings_scrollbar,
        "settings_inner": settings_inner,
        "provider_var": provider_var,
        "provider_menu": provider_menu,
        "api_var": api_var,
        "api_entry": api_entry,
        "template_var": template_var,
        "template_menu": template_menu,
        "config_text": config_text,
        "save_btn": save_btn,
    }


def build_resize_grip(parent, root, on_drag_start, on_drag):
    grip = tk.Label(
        parent, text="▟", bg=BG, fg=BORDER,
        font=("Consolas", 10), cursor="size_nw_se",
    )
    grip.place(relx=1.0, rely=1.0, anchor="se")
    grip.bind("<Button-1>", on_drag_start)
    grip.bind("<B1-Motion>", on_drag)
    return grip


def bind_keyboard(root, bindings: dict):
    """bindings: {(modifiers, key): callback}"""
    for (mod, key), cb in bindings.items():
        seq = f"<{mod}-{key}>" if mod else f"<{key}>"
        root.bind_all(seq, lambda e, c=cb: c())
