"""Floating badge — shown when the widget is minimised."""

import tkinter as tk

from .theme import BG_CARD, CYAN, MINI_SIZE, MUTED, TEXT
from .theme import BG as WIDGET_BG


class Badge:
    """Small floating 'B' badge with left-click restore and right-click menu."""

    def __init__(self, parent, on_restore, on_quit):
        self.parent = parent
        self._on_restore = on_restore
        self._on_quit = on_quit
        self.window: tk.Toplevel | None = None

    def show(self):
        self.hide()
        w = tk.Toplevel(self.parent)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=CYAN)
        w.geometry(f"{MINI_SIZE}x{MINI_SIZE}")

        sx = w.winfo_screenwidth()
        sy = w.winfo_screenheight()
        w.geometry(f"+{sx - MINI_SIZE - 15}+{sy - MINI_SIZE - 50}")

        label = tk.Label(w, text="B", bg=CYAN, fg="#000000",
                         font=("Consolas", 18, "bold"), cursor="hand2")
        label.pack(expand=True, fill=tk.BOTH)

        w.bind("<Button-1>", lambda e: self._on_restore())
        label.bind("<Button-1>", lambda e: self._on_restore())
        w.bind("<Button-3>", self._show_menu)
        label.bind("<Button-3>", self._show_menu)

        w.bind("<B1-Motion>", self._drag)
        label.bind("<B1-Motion>", self._drag)

        self.window = w

    def hide(self):
        if self.window:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None

    def _show_menu(self, event):
        menu = tk.Menu(self.window, tearoff=0, bg=BG_CARD, fg=TEXT,
                       activebackground=CYAN, activeforeground="#000000",
                       font=("Consolas", 10))
        menu.add_command(label="Restore", command=self._on_restore)
        menu.add_separator()
        menu.add_command(label="Quit", command=self._on_quit)
        menu.tk_popup(event.x_root, event.y_root)

    def _drag(self, event):
        if self.window:
            x = self.window.winfo_x() + event.x
            y = self.window.winfo_y() + event.y
            self.window.geometry(f"+{x}+{y}")
