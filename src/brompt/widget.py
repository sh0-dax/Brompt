"""Brompt Engine — Floating Widget

Always-on-top dark-themed panel with documentation and live engine status.
Usage:  python -m brompt.widget [--live]
"""

import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

# ---------------------------------------------------------------------------
# Theme colours (matches Brompt dark palette)
# ---------------------------------------------------------------------------
BG = "#0d1117"
BG_CARD = "#161b22"
BG_HEADER = "#1c2128"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
CYAN = "#58a6ff"
GREEN = "#3fb950"
RED = "#f85149"
YELLOW = "#d29922"
PURPLE = "#bc8cff"

WIDTH = 380
HEIGHT = 520
MINI_SIZE = 44
REFRESH_MS = 2000

# ---------------------------------------------------------------------------
# Documentation content (static)
# ---------------------------------------------------------------------------
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


class BromptWidget:
    """Floating always-on-top widget for Brompt Engine."""

    def __init__(self, live_mode: bool = False):
        self.root = tk.Tk()
        self.root.title("Brompt Engine")
        self.root.geometry(f"{WIDTH}x{HEIGHT}")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)
        self.root.minsize(280, 300)

        # Position bottom-right corner
        sx = self.root.winfo_screenwidth()
        sy = self.root.winfo_screenheight()
        self.root.geometry(f"+{sx - WIDTH - 15}+{sy - HEIGHT - 50}")

        self.is_mini = False
        self.normal_geometry = None
        self.live_mode = live_mode
        self.engine = None
        self._stop = False
        self.badge = None

        self._build_ui()
        self._bind_drag()

        # X button hides to badge instead of destroying
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_badge)

        if live_mode:
            self._connect_engine()
            self._start_live_refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        # --- Title bar ---
        self.title_frame = tk.Frame(self.root, bg=BG_HEADER, height=36)
        self.title_frame.pack(fill=tk.X)
        self.title_frame.pack_propagate(False)

        self.title_label = tk.Label(
            self.title_frame, text="  Brompt Engine",
            bg=BG_HEADER, fg=CYAN, font=("Consolas", 11, "bold"),
            anchor="w",
        )
        self.title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_frame = tk.Frame(self.title_frame, bg=BG_HEADER)
        btn_frame.pack(side=tk.RIGHT)

        self.mini_btn = tk.Button(
            btn_frame, text="—", bg=BG_HEADER, fg=MUTED,
            bd=0, activebackground=BORDER, activeforeground=TEXT,
            font=("Consolas", 12), width=3, command=self._toggle_mini,
        )
        self.mini_btn.pack(side=tk.LEFT)

        self.close_btn = tk.Button(
            btn_frame, text="✕", bg=BG_HEADER, fg=MUTED,
            bd=0, activebackground=RED, activeforeground=TEXT,
            font=("Consolas", 12), width=3, command=self._hide_to_badge,
        )
        self.close_btn.pack(side=tk.LEFT)

        # --- Tab bar ---
        self.tab_frame = tk.Frame(self.root, bg=BG, height=32)
        self.tab_frame.pack(fill=tk.X)
        self.tab_frame.pack_propagate(False)

        self.tab_docs = tk.Button(
            self.tab_frame, text=" Docs ", bg=CYAN, fg="#000000",
            bd=0, font=("Consolas", 10, "bold"), command=lambda: self._switch_tab("docs"),
        )
        self.tab_docs.pack(side=tk.LEFT, padx=(10, 2), pady=6)

        self.tab_live = tk.Button(
            self.tab_frame, text=" Live ", bg=BG_CARD, fg=MUTED,
            bd=0, font=("Consolas", 10, "bold"), command=lambda: self._switch_tab("live"),
        )
        self.tab_live.pack(side=tk.LEFT, padx=2, pady=6)

        self.status_label = tk.Label(
            self.tab_frame, text="● dry-run",
            bg=BG, fg=MUTED, font=("Consolas", 9), anchor="e",
        )
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # --- Separator ---
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        # --- Content area ---
        self.content_frame = tk.Frame(self.root, bg=BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Docs text widget
        self.docs_text = tk.Text(
            self.content_frame, bg=BG, fg=TEXT, insertbackground=TEXT,
            selectbackground=CYAN, selectforeground="#000000",
            font=("Consolas", 10), bd=0, wrap=tk.WORD,
            padx=12, pady=10, spacing1=1, spacing3=1,
        )
        self.docs_scroll = tk.Scrollbar(self.content_frame, command=self.docs_text.yview)
        self.docs_text.configure(yscrollcommand=self.docs_scroll.set)
        self.docs_text.insert("1.0", DOCS_TEXT.strip())
        self.docs_text.configure(state=tk.DISABLED)

        # Live text widget
        self.live_text = tk.Text(
            self.content_frame, bg=BG, fg=TEXT, insertbackground=TEXT,
            selectbackground=CYAN, selectforeground="#000000",
            font=("Consolas", 10), bd=0, wrap=tk.WORD,
            padx=12, pady=10, spacing1=1, spacing3=1,
        )
        self.live_scroll = tk.Scrollbar(self.content_frame, command=self.live_text.yview)
        self.live_text.configure(yscrollcommand=self.live_scroll.set)
        self.live_text.configure(state=tk.DISABLED)

        # Show docs by default
        self._show_tab("docs")

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------
    def _switch_tab(self, tab):
        self._show_tab(tab)
        if tab == "live" and self.engine is None:
            self._connect_engine()

    def _show_tab(self, tab):
        # Hide both
        self.docs_text.pack_forget()
        self.docs_scroll.pack_forget()
        self.live_text.pack_forget()
        self.live_scroll.pack_forget()

        if tab == "docs":
            self.tab_docs.configure(bg=CYAN, fg="#000000")
            self.tab_live.configure(bg=BG_CARD, fg=MUTED)
            self.docs_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.docs_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self.tab_docs.configure(bg=BG_CARD, fg=MUTED)
            self.tab_live.configure(bg=CYAN, fg="#000000")
            self.live_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.live_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            self._refresh_live()

    # ------------------------------------------------------------------
    # Dragging
    # ------------------------------------------------------------------
    def _bind_drag(self):
        self._drag_x = 0
        self._drag_y = 0
        for widget in (self.title_frame, self.title_label):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # Minimize to floating badge / restore
    # ------------------------------------------------------------------
    def _toggle_mini(self):
        if self.is_mini:
            self._restore()
        else:
            self._hide_to_badge()

    def _hide_to_badge(self):
        """Withdraw main window, show a small floating 'B' badge."""
        self.normal_geometry = self.root.geometry()
        self.root.withdraw()

        # Floating badge window
        self.badge = tk.Toplevel(self.root)
        self.badge.overrideredirect(True)
        self.badge.attributes("-topmost", True)
        self.badge.configure(bg=CYAN)
        self.badge.geometry(f"{MINI_SIZE}x{MINI_SIZE}")

        # Position bottom-right
        sx = self.badge.winfo_screenwidth()
        sy = self.badge.winfo_screenheight()
        self.badge.geometry(f"+{sx - MINI_SIZE - 15}+{sy - MINI_SIZE - 50}")

        # Badge label
        self.badge_label = tk.Label(
            self.badge, text="B", bg=CYAN, fg="#000000",
            font=("Consolas", 18, "bold"), cursor="hand2",
        )
        self.badge_label.pack(expand=True, fill=tk.BOTH)

        # Left-click → restore
        self.badge.bind("<Button-1>", self._restore_from_badge)
        self.badge_label.bind("<Button-1>", self._restore_from_badge)

        # Right-click → context menu
        self.badge_menu = tk.Menu(self.badge, tearoff=0, bg=BG_CARD, fg=TEXT,
                                  activebackground=CYAN, activeforeground="#000000",
                                  font=("Consolas", 10))
        self.badge_menu.add_command(label="Restore", command=self._restore)
        self.badge_menu.add_separator()
        self.badge_menu.add_command(label="Quit", command=self._quit)

        self.badge.bind("<Button-3>", self._show_badge_menu)
        self.badge_label.bind("<Button-3>", self._show_badge_menu)

        # Drag badge
        self.badge.bind("<B1-Motion>", self._drag_badge)
        self.badge_label.bind("<B1-Motion>", self._drag_badge)

        self.is_mini = True

    def _show_badge_menu(self, event):
        self.badge_menu.tk_popup(event.x_root, event.y_root)

    def _restore_from_badge(self, event=None):
        self._restore()

    def _restore(self):
        """Destroy badge, show main window."""
        if hasattr(self, "badge") and self.badge:
            self.badge.destroy()
            self.badge = None
        self.root.deiconify()
        if self.normal_geometry:
            self.root.geometry(self.normal_geometry)
        self.is_mini = False

    def _quit(self):
        self._stop = True
        if hasattr(self, "badge") and self.badge:
            self.badge.destroy()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Engine connection + live refresh
    # ------------------------------------------------------------------
    def _connect_engine(self):
        try:
            from brompt.core import BromptEngine
            from pathlib import Path
            # Find config
            candidates = [Path.cwd(), Path(__file__).resolve().parent.parent.parent]
            config = None
            for base in candidates:
                p = base / "agent.brompt.yaml"
                if p.exists():
                    config = str(p)
                    break
            if config:
                self.engine = BromptEngine(config, provider=None)
                self.status_label.configure(text="● connected", fg=GREEN)
            else:
                self.status_label.configure(text="● no config", fg=YELLOW)
        except Exception:
            self.status_label.configure(text="● error", fg=RED)

    def _start_live_refresh(self):
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
        if self.engine is None:
            content = (
                "  LIVE ENGINE STATUS\n"
                "  ═══════════════════\n\n"
                "  Status:  DISCONNECTED\n\n"
                "  Start the CLI to connect:\n"
                "  > python -m brompt.cli\n\n"
                "  Or run the engine:\n"
                "  > from brompt.core import BromptEngine\n"
                "  > e = BromptEngine('agent.brompt.yaml')\n"
            )
        else:
            try:
                history = self.engine.memory.get_history()
                entries = self.engine.audit.read_all()
                chain_ok = self.engine.audit.verify()
                provider_name = type(self.engine.provider).__name__ if self.engine.provider else "None"
                max_h = self.engine.memory.max_turns
                h_count = len(history)
                e_count = len(entries)
                chain_str = "VALID" if chain_ok else "TAMPERED"
                chain_clr = GREEN if chain_ok else RED
                sec_count = sum(1 for e in entries if e.get("is_secure"))
                rej_count = e_count - sec_count

                content = (
                    f"  LIVE ENGINE STATUS\n"
                    f"  ═══════════════════\n\n"
                    f"  Status:     CONNECTED\n"
                    f"  Provider:   {provider_name}\n\n"
                    f"  ── Memory ────────────\n"
                    f"  Turns:      {h_count} / {max_h}\n"
                    f"  Bounded:    {'YES' if h_count <= max_h else 'OVER'}\n\n"
                    f"  ── Audit Log ────────\n"
                    f"  Entries:    {e_count}\n"
                    f"  Secure:     {sec_count}\n"
                    f"  Rejected:   {rej_count}\n"
                    f"  Chain:      {chain_str}\n\n"
                    f"  ── Security ─────────\n"
                    f"  Pipeline:   7-stage\n"
                    f"  Isolation:  ZERO_TRUST\n"
                    f"  Payload:    64KB max\n\n"
                    f"  ── History ──────────\n"
                )
                if history:
                    for i, t in enumerate(history[-3:], 1):
                        role = t["role"]
                        msg = t["content"][:40]
                        if len(t["content"]) > 40:
                            msg += "..."
                        content += f"  [{i}] {role}: {msg}\n"
                else:
                    content += "  (empty)\n"

                content += f"\n  Updated: {time.strftime('%H:%M:%S')}\n"
            except Exception as exc:
                content = f"  ERROR: {exc}\n"

        self.live_text.configure(state=tk.NORMAL)
        self.live_text.delete("1.0", tk.END)
        self.live_text.insert("1.0", content)
        self.live_text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self):
        self.root.mainloop()

    def destroy(self):
        self._stop = True
        self.root.destroy()


def main():
    live = "--live" in sys.argv
    widget = BromptWidget(live_mode=live)
    widget.run()


if __name__ == "__main__":
    main()
