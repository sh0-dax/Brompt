"""Brompt Engine — Floating Widget (package entry point).

Always-on-top dark-themed panel with Docs, Live, Chart, Chat, and Settings tabs.
Usage:  python -m brompt.guiapp [--live]
"""

import asyncio
import json
import os
import sys
import threading
import time
import tkinter as tk
import tkinter.filedialog as tkfiledialog
import tkinter.messagebox as tkmessagebox
from pathlib import Path

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

from .badge import Badge
from .chart import ChartEngine
from .theme import (
    BG, BG_CARD, BG_HEADER, BORDER, CYAN, WIDTH, HEIGHT,
    GREEN, MUTED, RED, REFRESH_MS, YELLOW, ACCENT, SAVINGS_GREEN, TEXT,
)
from .ui import (
    ToolTip,
    build_title_bar,
    build_tab_bar,
    build_chart_toolbar,
    build_content_area,
    build_resize_grip,
    bind_keyboard,
    PROVIDER_NAMES,
    DOCS_TEXT,
)

from brompt.widget import PromptClient as BackendPromptWidget
from brompt.providers_core import (
    AnthropicProvider,
    OpenAIProvider,
    GeminiProvider,
    MistralProvider,
    AzureOpenAIProvider,
    OllamaProvider,
    LMStudioProvider,
)

try:
    from templates import list_templates as _list_tpls
except ImportError:
    _list_tpls = lambda: []


PROVIDER_FACTORIES = {
    "Gemini": lambda key: GeminiProvider(api_key=key, model="gemini-2.5-flash"),
    "OpenAI": lambda key: OpenAIProvider(api_key=key, model="gpt-4o"),
    "Anthropic": lambda key: AnthropicProvider(api_key=key, model="claude-sonnet-4-5"),
    "Mistral": lambda key: MistralProvider(api_key=key, model="mistral-large-latest"),
    "Azure OpenAI": lambda key: AzureOpenAIProvider(api_key=key, model="gpt-4o"),
    "Ollama": lambda host: OllamaProvider(base_url=host or "http://localhost:11434", model="llama3.2"),
    "LM Studio": lambda host: LMStudioProvider(base_url=host or "http://localhost:1234", model="default"),
}


def _fmt_short_cost(c: float) -> str:
    if c >= 0.01:
        return f"${c:.4f}"
    if c >= 0.001:
        return f"${c:.5f}"
    if c > 0:
        return f"${c:.6f}"
    return "$0.00"


def _resolve_config_path() -> Path:
    """Search cwd and repo root for ``agent.brompt.yaml``.

    Returns the first existing file found, or a default path under
    ``Path.cwd()`` if none exists yet.
    """
    candidates = [Path.cwd(), Path(__file__).resolve().parent.parent.parent.parent]
    for base in candidates:
        p = base / "agent.brompt.yaml"
        if p.exists():
            return p
    return Path.cwd() / "agent.brompt.yaml"


class BromptWidget:
    """Floating always-on-top widget monitoring Brompt Engine."""

    def __init__(self, live_mode: bool = False):
        self.root = tk.Tk()
        self.root.title("Brompt Engine")
        self.root.geometry(f"{WIDTH}x{HEIGHT}")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)
        self.root.minsize(280, 300)
        self._icon_img = self._make_icon()
        self.root.iconphoto(True, self._icon_img)

        sx = self.root.winfo_screenwidth()
        sy = self.root.winfo_screenheight()
        self.root.geometry(f"+{sx - WIDTH - 15}+{sy - HEIGHT - 50}")

        self.is_mini = False
        self.normal_geometry = None
        self.live_mode = live_mode
        self.engine = None
        self._stop = False
        self._active_tab = "docs"
        self._refresh_started = False
        self._hb = 0

        # Phase 2-4: Provider, Backend, Savings, Templates
        self._backend = None
        self._backend_lock = threading.RLock()
        self._provider_type = PROVIDER_NAMES[0]
        self._api_key = ""
        self._selected_template = ""
        self._total_saved_tokens = 0
        self._total_cost_saved = 0.0
        self._chat_messages = []
        self._template_names = []
        self._loading = False
        self._geom_file = Path.home() / ".brompt_geometry.json"

        self._restore_geometry()

        # Chart engine
        self.chart_engine = ChartEngine()

        # Badge manager
        self.badge = Badge(self.root, on_restore=self._restore, on_quit=self._quit)

        # Build UI pieces
        self._build_ui()
        self._register_keyboard()

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        if live_mode:
            self._connect_engine()
            self._start_live_refresh()

    # ------------------------------------------------------------------
    # Icon, hover helpers
    # ------------------------------------------------------------------

    def _make_icon(self) -> tk.PhotoImage:
        size = 32
        img = tk.PhotoImage(width=size, height=size)
        cx = cy = size / 2
        r = size / 2 - 2
        for y in range(size):
            row_colors = []
            for x in range(size):
                dx = x - cx + 0.5
                dy = y - cy + 0.5
                row_colors.append(CYAN if dx * dx + dy * dy <= r * r else BG)
            img.put("{" + " ".join(row_colors) + "}", to=(0, y))
        return img

    def _add_hover(self, widget, idle_bg, hover_bg):
        widget.bind("<Enter>", lambda _e: widget.configure(bg=hover_bg))
        widget.bind("<Leave>", lambda _e: widget.configure(bg=idle_bg))

    def _add_tab_hover(self, button, tab_name, hover_bg="#21262d"):
        def on_enter(_e):
            if self._active_tab != tab_name:
                button.configure(bg=hover_bg)

        def on_leave(_e):
            if self._active_tab != tab_name:
                button.configure(bg=BG_CARD)

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.title_frame, _, self.mini_btn, self.close_btn = build_title_bar(
            self.root,
            on_mini=self._toggle_mini,
            on_hide=self._quit,
        )
        self._add_hover(self.mini_btn, BG_HEADER, BORDER)
        self._add_hover(self.close_btn, BG_HEADER, RED)

        self.tab_buttons, self.status_label, _ = build_tab_bar(
            self.root,
            on_switch=self._switch_tab,
            get_active=lambda: self._active_tab,
        )
        for name, btn in self.tab_buttons.items():
            self._add_tab_hover(btn, name)

        card_outer = tk.Frame(self.root, bg=BORDER)
        card_outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        content_inner = tk.Frame(card_outer, bg=BG)
        content_inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.content = build_content_area(content_inner)

        # Wire chat send
        c = self.content
        c["chat_send_btn"].configure(command=self._send_chat)
        c["chat_input"].bind("<Control-Return>", self._on_ctrl_enter)

        # Wire settings
        c["save_btn"].configure(command=self._save_config)
        c["browse_btn"].configure(command=self._browse_config)
        c["provider_menu"].bind("<<ComboboxSelected>>", self._on_provider_change)
        c["template_menu"].bind("<<ComboboxSelected>>", self._on_template_change)

        # Phase 3-4: Load template list
        self._refresh_template_list()

        # Load DOCS.md if available
        self._load_docs_from_file()

        # Tooltips
        ToolTip(self.mini_btn, "Minimize to system tray (Ctrl+M)")
        ToolTip(self.close_btn, "Quit (Ctrl+Q)")
        ToolTip(c["chat_send_btn"], "Send message (Ctrl+Enter)")
        ToolTip(c["save_btn"], "Save configuration to agent.brompt.yaml")
        ToolTip(c["browse_btn"], "Browse for a YAML config file")
        tab_help = {"docs": "Quick reference (Ctrl+D)", "live": "Engine status (Ctrl+L)",
                     "chart": "Analytics charts (Ctrl+C)", "chat": "Chat with engine (Ctrl+H)",
                     "settings": "Configuration (Ctrl+S)"}
        for name, btn in self.tab_buttons.items():
            ToolTip(btn, tab_help.get(name, name))

        # Chart toolbar (hidden until chart tab is active)
        self.chart_bar, self._chart_type_btns, self._chart_series_btns = build_chart_toolbar(
            self.content["frame"], self.chart_engine,
            on_redraw=lambda: self._refresh_live(),
        )
        self.chart_bar.pack_forget()

        chart_tips = {"bar": "Bar chart", "line": "Line chart", "area": "Area chart",
                      "stacked": "Stacked area", "donut": "Donut chart"}
        for ct, btn in self._chart_type_btns.items():
            ToolTip(btn, chart_tips.get(ct, ct))
        series_tips = {"activity": "Activity (Secure vs Rejected)", "latency": "Latency trend",
                       "tokens": "Token count trend"}
        for ds, btn in self._chart_series_btns.items():
            ToolTip(btn, series_tips.get(ds, ds))

        # Resize grip
        self.grip = build_resize_grip(
            self.root, self.root,
            on_drag_start=self._start_resize,
            on_drag=self._on_resize,
        )

        # Drag support on title
        self._drag_x = 0
        self._drag_y = 0
        for w in (self.title_frame,):
            for child in w.winfo_children():
                child.bind("<Button-1>", self._start_drag)
                child.bind("<B1-Motion>", self._on_drag)

        self._show_tab("docs")

    def _register_keyboard(self):
        def switch(tab):
            return lambda: self._switch_tab(tab)

        bind_keyboard(self.root, {
            ("Control", "d"): switch("docs"),
            ("Control", "l"): switch("live"),
            ("Control", "c"): switch("chart"),
            ("Control", "h"): switch("chat"),
            ("Control", "s"): switch("settings"),
            ("Control", "m"): self._toggle_mini,
            ("Control", "q"): self._quit,
        })

    # ------------------------------------------------------------------
    # Phase 1: Tab switching
    # ------------------------------------------------------------------

    def _switch_tab(self, tab):
        self._show_tab(tab)
        if tab in ("live", "chart") and self.engine is None:
            self._connect_engine()
        if tab in ("live", "chart") and not self._refresh_started:
            self._start_live_refresh()

    def _show_tab(self, tab):
        c = self.content

        # Hide all content widgets
        for key in ("docs_text", "docs_scroll", "live_text", "live_scroll",
                    "chart_canvas", "chat_frame", "settings_frame"):
            if key in c:
                c[key].pack_forget()
        self.chart_bar.pack_forget()

        self._active_tab = tab
        self._update_tab_style(tab)

        if tab == "docs":
            c["docs_text"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            c["docs_scroll"].pack(side=tk.RIGHT, fill=tk.Y)

        elif tab == "chart":
            self.chart_bar.pack(fill=tk.X)
            c["chart_canvas"].pack(fill=tk.BOTH, expand=True)
            self._refresh_live()

        elif tab == "live":
            c["live_text"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            c["live_scroll"].pack(side=tk.RIGHT, fill=tk.Y)
            self._refresh_live()

        elif tab == "chat":
            c["chat_frame"].pack(fill=tk.BOTH, expand=True)
            c["chat_text"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            c["chat_scroll"].pack(side=tk.RIGHT, fill=tk.Y)
            c["chat_bottom"].pack(fill=tk.X)
            c["chat_input"].focus_set()

        elif tab == "settings":
            c["settings_frame"].pack(fill=tk.BOTH, expand=True)
            c["settings_canvas"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            c["settings_scrollbar"].pack(side=tk.RIGHT, fill=tk.Y)
            self._load_config_into_editor()
            self.content["provider_var"].set(self._provider_type)
            self.content["api_var"].set(self._api_key)

    def _update_tab_style(self, active):
        for name, btn in self.tab_buttons.items():
            is_active = name == active
            btn.configure(
                bg=CYAN if is_active else BG_CARD,
                fg="#000000" if is_active else MUTED,
            )

    # ------------------------------------------------------------------
    # Drag / Resize
    # ------------------------------------------------------------------

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        self.root.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _start_resize(self, event):
        self._resize_x = event.x_root
        self._resize_y = event.y_root
        self._resize_w = self.root.winfo_width()
        self._resize_h = self.root.winfo_height()

    def _on_resize(self, event):
        dw = event.x_root - self._resize_x
        dh = event.y_root - self._resize_y
        self.root.geometry(f"{max(280, self._resize_w + dw)}x{max(300, self._resize_h + dh)}")

    def _on_ctrl_enter(self, event=None):
        self._send_chat()
        return "break"

    # ------------------------------------------------------------------
    # Minimize / Badge (Phase 6: system tray)
    # ------------------------------------------------------------------

    def _toggle_mini(self):
        if self.is_mini:
            self._restore()
        else:
            self._hide_to_badge()

    def _hide_to_badge(self):
        self.normal_geometry = self.root.geometry()
        self.root.withdraw()
        self.badge.show()
        self.is_mini = True

    def _restore(self):
        self.badge.hide()
        self.root.deiconify()
        if self.normal_geometry:
            self.root.geometry(self.normal_geometry)
        self.is_mini = False

    def _quit(self):
        self._save_geometry()
        self._stop = True
        self.badge.hide()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Phase 2: Provider config
    # ------------------------------------------------------------------

    def _on_provider_change(self, event=None):
        self._provider_type = self.content["provider_var"].get()
        self._api_key = self.content["api_var"].get()
        self._backend = None
        self.status_label.configure(text="● configured", fg=YELLOW)

    def _on_template_change(self, event=None):
        self._selected_template = self.content["template_var"].get()

    def _refresh_template_list(self):
        self._template_names = _list_tpls()
        self.content["template_menu"].configure(values=[""] + self._template_names)

    # ------------------------------------------------------------------
    # Phase 2: Engine connection
    # ------------------------------------------------------------------

    def _connect_engine(self):
        try:
            from brompt.core.engine import BromptEngine

            config_path = _resolve_config_path()
            if not config_path.exists():
                config_path.write_text(
                    "metadata:\n"
                    "  name: DefaultAgent\n"
                    "  version: 0.1.0-alpha\n"
                    "  environment: production\n"
                    "security_policy:\n"
                    "  isolation_level: ZERO_TRUST\n"
                    "  sanitize_inputs: true\n"
                    "  max_payload_size_kb: 64\n"
                    "memory_strategy:\n"
                    "  paging_mode: VIRTUAL_STATE_O1\n"
                    "  max_history_turns: 10\n"
                    "rate_limit:\n"
                    "  max_requests: 30\n"
                    "  window_seconds: 60\n",
                    encoding="utf-8",
                )
            self.engine = BromptEngine(str(config_path), provider=None)
            self.status_label.configure(text="● connected", fg=GREEN)
        except Exception:
            self.status_label.configure(text="● error", fg=RED)

    # ------------------------------------------------------------------
    # Phase 1-3: Chat send with auto-detect + savings
    # ------------------------------------------------------------------

    def _ensure_backend(self) -> bool:
        """Create BackendPromptWidget if not yet created."""
        with self._backend_lock:
            if self._backend is not None:
                return True
            self._api_key = self.content["api_var"].get()
            factory = PROVIDER_FACTORIES.get(self._provider_type)
            if not factory:
                self._append_chat("  ❌ Unknown provider\n")
                return False
            # Validation: cloud providers need a non-empty API key
            is_local = self._provider_type in ("Ollama", "LM Studio")
            if not is_local and not self._api_key.strip():
                self._append_chat("  ❌ API key required for this provider\n")
                return False
            try:
                provider = factory(self._api_key)
                self._backend = BackendPromptWidget(
                    provider=provider,
                    enable_token_optimization=True,
                    enable_cache=True,
                    enable_auto_detect=True,
                    enable_streaming=False,
                )
                self.status_label.configure(text="● connected", fg=GREEN)
                return True
            except Exception as exc:
                self._append_chat(f"  ❌ Init error: {exc}\n")
                self.status_label.configure(text="● error", fg=RED)
                return False

    def _send_chat(self):
        if self._loading:
            return
        text = self.content["chat_input"].get("1.0", "end-1c").strip()
        if not text:
            return

        self.content["chat_input"].delete("1.0", tk.END)
        self._loading = True
        self.status_label.configure(text="● sending...", fg=YELLOW)

        # Setup (reads config, creates the backend) stays on the Tk thread;
        # only the provider call moves to a worker thread so the UI is not
        # blocked and no provider runs directly on the main loop.
        with self._backend_lock:
            if self._backend is None and not self._ensure_backend():
                self._loading = False
                self.status_label.configure(text="● error", fg=RED)
                return

        self._append_chat(f"  You: {text}\n")

        def worker():
            try:
                result = asyncio.run(self._backend.prompt(text))
                self.root.after(0, lambda: self._finish_chat(True, result, text))
            except Exception as exc:
                self.root.after(0, lambda: self._finish_chat(False, exc, text))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_chat(self, ok: bool, payload, text: str):
        """Apply a completed (or failed) chat reply on the Tk thread."""
        self._loading = False
        if not ok:
            err = payload if isinstance(payload, Exception) else "Unknown error"
            self._append_chat(f"  Error: {err}\n")
            self.status_label.configure(text="● error", fg=RED)
            return

        result = payload
        response = result.response or "(no response)"
        self._append_chat(f"  Bot: {response}\n")

        if result.auto_detected and result.detected_task:
            conf = result.detection_confidence or 0
            self._append_chat(f"  🧠 {result.detected_task} ({conf:.0%})\n")

        saved_tok = result.tokens_saved or 0
        saved_cost = result.cost_saved or 0
        if saved_tok > 0:
            self._total_saved_tokens += saved_tok
            self._total_cost_saved += saved_cost
            pct = result.savings_percent or 0
            self._append_chat(f"  💰 Saved {saved_tok} tok (${saved_cost:.4f}) — {pct:.0%} saved\n")

        self._chat_messages.append({"role": "user", "content": text})
        self._chat_messages.append({"role": "assistant", "content": response})
        self.status_label.configure(text="● connected", fg=GREEN)

    def _append_chat(self, msg: str):
        chat = self.content["chat_text"]
        chat.configure(state=tk.NORMAL)
        chat.insert(tk.END, msg)
        chat.configure(state=tk.DISABLED)
        chat.see(tk.END)

    # ------------------------------------------------------------------
    # Phase 3: Live refresh with savings + templates
    # ------------------------------------------------------------------

    def _start_live_refresh(self):
        self._refresh_started = True

        def loop():
            while not self._stop:
                try:
                    self.root.after(0, self._refresh_live)
                except Exception:
                    break
                time.sleep(REFRESH_MS / 1000)

        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def _refresh_live(self):
        analytics = {}
        with self._backend_lock:
            is_chat_active = self._backend is not None
            if is_chat_active:
                try:
                    analytics = self._backend.get_analytics()
                except Exception:
                    analytics = {}

        if self.engine is None and not is_chat_active:
            content = (
                "  LIVE ENGINE STATUS\n"
                "  ═══════════════════\n\n"
                "  Status:  DISCONNECTED\n\n"
                "  Configure provider in Settings\n"
                "  tab, then open Chat to send.\n\n"
                "  Start the CLI to connect engine:\n"
                "  > python -m brompt.cli\n"
            )
        else:
            lines = []
            lines.append("  LIVE ENGINE STATUS")
            lines.append("  ═══════════════════\n")
            lines.append(f"  Status:     {'CONNECTED' if self.engine else 'CHAT-ONLY'}")
            lines.append(f"  Provider:   {self._provider_type}")
            if is_chat_active:
                lines.append(f"  Cache:      {analytics.get('cache_hit_rate', 0):.0f}% hit rate")

            # Phase 3: Savings
            if self._total_saved_tokens > 0:
                lines.append("")
                lines.append("  ── Savings ────────────")
                lines.append(f"  Tokens:     {self._total_saved_tokens:,}")
                lines.append(f"  Cost:       {_fmt_short_cost(self._total_cost_saved)}")

            # Phase 4: Templates
            if self._template_names:
                lines.append("")
                lines.append("  ── Templates ──────────")
                lines.append(f"  Active:     {self._selected_template or '(none)'}")
                lines.append(f"  Available:  {len(self._template_names)}")

            if self.engine:
                try:
                    history = self.engine.memory.get_history()
                    entries = self.engine.audit.read_all()
                    chain_ok = self.engine.audit.verify()
                    max_h = self.engine.memory.max_turns
                    h_count = len(history)
                    e_count = len(entries)
                    sec_count = sum(1 for e in entries if e.get("is_secure"))
                    rej_count = e_count - sec_count

                    latencies = [e.get("latency_ms") or 0 for e in entries if e.get("latency_ms") is not None]
                    tokens = [e.get("tokens_used") or 0 for e in entries if e.get("tokens_used") is not None]
                    avg_lat = sum(latencies) / len(latencies) if latencies else 0
                    avg_tok = sum(tokens) / len(tokens) if tokens else 0

                    lines.append("")
                    lines.append("  ── Memory ────────────")
                    lines.append(f"  Turns:      {h_count} / {max_h}")
                    lines.append("")
                    lines.append("  ── Audit Log ─────────")
                    lines.append(f"  Entries:    {e_count}")
                    lines.append(f"  Secure:     {sec_count}")
                    lines.append(f"  Rejected:   {rej_count}")
                    lines.append(f"  Chain:      {'VALID' if chain_ok else 'TAMPERED'}")
                    lines.append("")
                    lines.append("  ── Performance ───────")
                    lines.append(f"  Avg Latency: {avg_lat:.0f}ms")
                    lines.append(f"  Avg Tokens:  {avg_tok:.0f}")
                    lines.append("")
                    lines.append("  ── History ───────────")
                    if history:
                        for i, t in enumerate(history[-3:], 1):
                            msg = t["content"][:40]
                            if len(t["content"]) > 40:
                                msg += "..."
                            lines.append(f"  [{i}] {t['role']}: {msg}")
                    else:
                        lines.append("  (empty)")

                    # Feed chart
                    sample = (sec_count, rej_count, avg_lat, avg_tok)
                    if not self.chart_engine.samples or self.chart_engine.samples[-1] != sample:
                        self.chart_engine.add_sample(sec_count, rej_count, avg_lat, avg_tok)

                except Exception as exc:
                    lines.append("")
                    lines.append(f"  Engine error: {exc}")

            lines.append("")
            lines.append(f"  Updated: {time.strftime('%H:%M:%S')}")
            content = "\n".join(lines)

            if self._active_tab == "chart":
                try:
                    self.chart_engine.draw(self.content["chart_canvas"])
                except Exception:
                    pass

        lt = self.content["live_text"]
        lt.configure(state=tk.NORMAL)
        lt.delete("1.0", tk.END)
        lt.insert("1.0", content)
        lt.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Phase 5: Settings — load/save config
    # ------------------------------------------------------------------

    def _load_config_into_editor(self):
        config_path = _resolve_config_path()
        try:
            text = config_path.read_text(encoding="utf-8")
            c = self.content
            c["config_text"].delete("1.0", tk.END)
            c["config_text"].insert("1.0", text)
        except Exception:
            pass

    def _save_config(self):
        new_text = self.content["config_text"].get("1.0", tk.END).strip()
        config_path = _resolve_config_path()

        # Validate YAML before overwriting
        if _YAML_AVAILABLE:
            try:
                yaml.safe_load(new_text)
            except Exception as exc:
                self.status_label.configure(text=f"● invalid YAML: {exc}", fg=RED)
                return

        try:
            config_path.write_text(new_text, encoding="utf-8")
            self.status_label.configure(text="● saved", fg=GREEN)
        except Exception as exc:
            self.status_label.configure(text=f"● save error: {exc}", fg=RED)

    # ------------------------------------------------------------------
    # DOCS.md extraction
    # ------------------------------------------------------------------

    def _load_docs_from_file(self):
        for base in (Path(__file__).parent, Path.cwd()):
            p = base / "DOCS.md"
            if p.exists():
                try:
                    text = p.read_text(encoding="utf-8")
                    c = self.content
                    c["docs_text"].configure(state=tk.NORMAL)
                    c["docs_text"].delete("1.0", tk.END)
                    c["docs_text"].insert("1.0", text.strip())
                    c["docs_text"].configure(state=tk.DISABLED)
                except Exception:
                    pass
                break

    # ------------------------------------------------------------------
    # Config file picker
    # ------------------------------------------------------------------

    def _browse_config(self):
        path = tkfiledialog.askopenfilename(
            title="Select Config File",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            c = self.content
            c["config_text"].delete("1.0", tk.END)
            c["config_text"].insert("1.0", text)
            self.status_label.configure(text=f"● loaded {Path(path).name}", fg=GREEN)
        except Exception as exc:
            tkmessagebox.showerror("Load Error", f"Could not read file:\n{exc}")

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def _save_geometry(self):
        try:
            geo = self.root.geometry()
            data = {"geometry": geo}
            self._geom_file.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def _restore_geometry(self):
        try:
            if self._geom_file.exists():
                data = json.loads(self._geom_file.read_text(encoding="utf-8"))
                if "geometry" in data:
                    self.root.geometry(data["geometry"])
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self):
        self.root.mainloop()

    def destroy(self):
        self._stop = True
        self.badge.hide()
        self.root.destroy()


def main():
    live = "--live" in sys.argv
    widget = BromptWidget(live_mode=live)
    widget.run()


if __name__ == "__main__":
    main()
