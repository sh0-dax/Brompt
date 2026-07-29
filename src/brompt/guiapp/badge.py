"""Floating badge — shown when the widget is minimised.

Supports system tray via pystray (if available), falls back to Toplevel badge.
"""

import threading
import tkinter as tk

from .theme import BG_CARD, CYAN, MINI_SIZE, MUTED, TEXT

try:
    import pystray
    from PIL import Image, ImageDraw

    HAS_SYSTRAY = True
except ImportError:
    HAS_SYSTRAY = False


class Badge:
    """System tray or Toplevel badge depending on platform support."""

    def __init__(self, parent, on_restore, on_quit):
        self.parent = parent
        self._on_restore = on_restore
        self._on_quit = on_quit
        self._tray_icon = None
        self._tray_thread = None
        self._top = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self):
        self.hide()
        if HAS_SYSTRAY:
            self._show_tray()
        else:
            self._show_top()

    def hide(self):
        if HAS_SYSTRAY:
            self._hide_tray()
        self._hide_top()

    # ------------------------------------------------------------------
    # System tray (pystray)
    # ------------------------------------------------------------------

    def _show_tray(self):
        img = self._make_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Restore", self._safe_restore),
            pystray.MenuItem("Quit", self._safe_quit),
        )
        self._tray_icon = pystray.Icon("brompt", img, "Brompt Engine", menu)
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._tray_thread.start()

    def _hide_tray(self):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
            self._tray_thread = None

    def _safe_restore(self, icon=None, item=None):
        self.hide()
        self.parent.after(0, self._on_restore)

    def _safe_quit(self, icon=None, item=None):
        self.hide()
        self.parent.after(0, self._on_quit)

    @staticmethod
    def _make_icon_image():
        img = Image.new("RGB", (16, 16), (88, 166, 255))
        draw = ImageDraw.Draw(img)
        draw.text((2, -2), "B", fill=(0, 0, 0))
        return img

    # ------------------------------------------------------------------
    # Toplevel badge (fallback)
    # ------------------------------------------------------------------

    def _show_top(self):
        self._hide_top()
        w = tk.Toplevel(self.parent)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.geometry(f"{MINI_SIZE}x{MINI_SIZE}")

        sx = w.winfo_screenwidth()
        sy = w.winfo_screenheight()
        w.geometry(f"+{sx - MINI_SIZE - 15}+{sy - MINI_SIZE - 50}")

        key = "#000001"
        is_round = False
        try:
            w.attributes("-transparentcolor", key)
            is_round = True
        except tk.TclError:
            is_round = False

        badge_bg = key if is_round else CYAN
        w.configure(bg=badge_bg)

        if is_round:
            canvas = tk.Canvas(w, width=MINI_SIZE, height=MINI_SIZE,
                               bg=key, highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.create_oval(1, 1, MINI_SIZE - 1, MINI_SIZE - 1,
                               fill=CYAN, outline="")
            canvas.create_text(MINI_SIZE / 2, MINI_SIZE / 2,
                               text="B", fill="#000000",
                               font=("Consolas", 14, "bold"))
            widget = canvas
        else:
            widget = tk.Label(w, text="B", bg=CYAN, fg="#000000",
                              font=("Consolas", 14, "bold"), cursor="hand2")
            widget.pack(expand=True, fill=tk.BOTH)

        w.bind("<Button-1>", lambda e: self._on_restore())
        widget.bind("<Button-1>", lambda e: self._on_restore())
        w.bind("<Button-3>", self._show_menu)
        widget.bind("<Button-3>", self._show_menu)
        w.bind("<B1-Motion>", self._drag_badge)
        widget.bind("<B1-Motion>", self._drag_badge)

        self._top = w

    def _hide_top(self):
        if self._top:
            try:
                self._top.destroy()
            except tk.TclError:
                pass
            self._top = None

    def _show_menu(self, event):
        menu = tk.Menu(
            self._top, tearoff=0, bg=BG_CARD, fg=TEXT,
            activebackground=CYAN, activeforeground="#000000",
            font=("Consolas", 10),
        )
        menu.add_command(label="Restore", command=self._on_restore)
        menu.add_separator()
        menu.add_command(label="Quit", command=self._on_quit)
        menu.tk_popup(event.x_root, event.y_root)

    def _drag_badge(self, event):
        if self._top:
            x = event.x_root - MINI_SIZE // 2
            y = event.y_root - MINI_SIZE // 2
            self._top.geometry(f"+{x}+{y}")
