"""Brompt Engine — Floating Widget (package entry point).

Always-on-top dark-themed panel with Docs, Live, and Chart tabs.
Usage:  python -m brompt.widget [--live]
"""

import sys
import threading
import time
import tkinter as tk

from .badge import Badge
from .chart import ChartEngine
from .theme import BG, CYAN, WIDTH, HEIGHT, GREEN, MUTED, RED, REFRESH_MS, YELLOW
from .ui import (
    build_title_bar,
    build_tab_bar,
    build_chart_toolbar,
    build_content_area,
    build_resize_grip,
    bind_keyboard,
)


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
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.title_frame, _ = build_title_bar(
            self.root,
            on_mini=self._toggle_mini,
            on_hide=self._quit,
        )
        self.tab_buttons, self.status_label, _ = build_tab_bar(
            self.root,
            on_switch=self._switch_tab,
            get_active=lambda: self._active_tab,
        )

        self.content = build_content_area(self.root)

        # Chart toolbar (hidden until chart tab is active)
        self.chart_bar, self._chart_type_btns, self._chart_series_btns = build_chart_toolbar(
            self.content["frame"], self.chart_engine,
            on_redraw=lambda: self._refresh_live(),
        )
        self.chart_bar.pack_forget()

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
            ("Control", "m"): self._toggle_mini,
            ("Control", "q"): self._quit,
        })

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------
    def _switch_tab(self, tab):
        self._show_tab(tab)
        if tab in ("live", "chart") and self.engine is None:
            self._connect_engine()
        if tab in ("live", "chart") and not self._refresh_started:
            self._start_live_refresh()

    def _show_tab(self, tab):
        c = self.content

        # Hide all
        c["docs_text"].pack_forget()
        c["docs_scroll"].pack_forget()
        c["live_text"].pack_forget()
        c["live_scroll"].pack_forget()
        c["chart_canvas"].pack_forget()
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
        else:
            c["live_text"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            c["live_scroll"].pack(side=tk.RIGHT, fill=tk.Y)
            self._refresh_live()

    def _update_tab_style(self, active):
        for name, btn in self.tab_buttons.items():
            is_active = name == active
            btn.configure(
                bg=CYAN if is_active else "#161b22",
                fg="#000000" if is_active else "#8b949e",
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

    # ------------------------------------------------------------------
    # Minimize / Badge
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
        self._stop = True
        self.badge.hide()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Engine connection + live refresh
    # ------------------------------------------------------------------
    def _connect_engine(self):
        try:
            from pathlib import Path
            from brompt.core import BromptEngine

            candidates = [Path.cwd(), Path(__file__).resolve().parent.parent.parent.parent]
            config_path = None
            for base in candidates:
                p = base / "agent.brompt.yaml"
                if p.exists():
                    config_path = str(p)
                    break
            if not config_path:
                default = Path.cwd() / "agent.brompt.yaml"
                default.write_text(
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
                config_path = str(default)
            self.engine = BromptEngine(config_path, provider=None)
            self.status_label.configure(text="● connected", fg=GREEN)
        except Exception:
            self.status_label.configure(text="● error", fg=RED)

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
        if self.engine is None:
            content = (
                "  LIVE ENGINE STATUS\n"
                "  ═══════════════════\n\n"
                "  Status:  DISCONNECTED\n\n"
                "  Start the CLI to connect:\n"
                "  > python -m brompt.cli\n"
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
                sec_count = sum(1 for e in entries if e.get("is_secure"))
                rej_count = e_count - sec_count

                # Latency and tokens from audit log
                latencies = [e.get("latency_ms") or 0 for e in entries if e.get("latency_ms") is not None]
                tokens = [e.get("tokens_used") or 0 for e in entries if e.get("tokens_used") is not None]
                avg_lat = sum(latencies) / len(latencies) if latencies else 0
                avg_tok = sum(tokens) / len(tokens) if tokens else 0

                content = (
                    f"  LIVE ENGINE STATUS\n"
                    f"  ═══════════════════\n\n"
                    f"  Status:     CONNECTED\n"
                    f"  Provider:   {provider_name}\n\n"
                    f"  ── Memory ────────────\n"
                    f"  Turns:      {h_count} / {max_h}\n\n"
                    f"  ── Audit Log ────────\n"
                    f"  Entries:    {e_count}\n"
                    f"  Secure:     {sec_count}\n"
                    f"  Rejected:   {rej_count}\n"
                    f"  Chain:      {'VALID' if chain_ok else 'TAMPERED'}\n\n"
                    f"  ── Performance ──────\n"
                    f"  Avg Latency: {avg_lat:.0f}ms\n"
                    f"  Avg Tokens:  {avg_tok:.0f}\n"
                    f"  ── History ──────────\n"
                )
                if history:
                    for i, t in enumerate(history[-3:], 1):
                        msg = t["content"][:40]
                        if len(t["content"]) > 40:
                            msg += "..."
                        content += f"  [{i}] {t['role']}: {msg}\n"
                else:
                    content += "  (empty)\n"

                content += f"\n  Updated: {time.strftime('%H:%M:%S')}\n"

                # Feed chart samples — heartbeat animation when idle
                self._hb = (self._hb + 1) % 20
                hb_sec = sec_count + max(0, 4 - self._hb)
                hb_rej = rej_count + max(0, min(self._hb, 2))
                hb_lat = avg_lat or self._hb * 5
                hb_tok = avg_tok or self._hb * 2
                sample = (hb_sec, hb_rej, hb_lat, hb_tok)
                if not self.chart_engine.samples or self.chart_engine.samples[-1] != sample:
                    self.chart_engine.add_sample(hb_sec, hb_rej, hb_lat, hb_tok)

                if self._active_tab == "chart":
                    self.chart_engine.draw(self.content["chart_canvas"])

            except Exception as exc:
                content = f"  ERROR: {exc}\n"

        lt = self.content["live_text"]
        lt.configure(state=tk.NORMAL)
        lt.delete("1.0", tk.END)
        lt.insert("1.0", content)
        lt.configure(state=tk.DISABLED)

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
