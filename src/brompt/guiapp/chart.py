"""Chart engine — draws 5 chart types on a tkinter Canvas.

Supported chart types:
  - bar       vertical bars for Secure / Rejected
  - line      two smoothed lines
  - area      filled region under each line
  - stacked   stacked filled areas
  - donut     proportion ring (latest snapshot only)

Data series:
  - activity  (secure_count, rejected_count) per sample
  - latency   rolling average latency per sample
  - tokens    rolling average token count per sample
"""

import math
from collections import deque
from tkinter import Canvas

from .theme import BG, BORDER, CYAN, GREEN, MUTED, RED, TEXT, YELLOW, CHART_HISTORY_LEN

CHART_TYPES = ("bar", "line", "area", "stacked", "donut")
DATA_SERIES = ("activity", "latency", "tokens")


class ChartEngine:
    def __init__(self):
        self.chart_type = "bar"
        self.data_series = "activity"
        self.samples: deque = deque(maxlen=CHART_HISTORY_LEN)

    def set_type(self, t: str):
        if t in CHART_TYPES:
            self.chart_type = t

    def set_series(self, s: str):
        if s in DATA_SERIES:
            self.data_series = s

    def add_sample(self, sec: int, rej: int, lat: float, tok: int):
        self.samples.append((sec, rej, lat, tok))

    def draw(self, c: Canvas):
        c.delete("all")
        c.update_idletasks()
        w = max(c.winfo_width(), 200)
        h = max(c.winfo_height(), 200)
        pad = 14

        if not self.samples:
            c.create_text(w // 2, h // 2, fill=MUTED,
                          font=("Consolas", 10), text="No data yet")
            return

        c.create_text(pad, 12, anchor="w", fill=TEXT,
                      font=("Consolas", 10, "bold"),
                      text=f"{self.data_series.title()} — {self.chart_type.title()}")

        if self.chart_type == "donut":
            self._draw_donut(c, w, h, pad)
        else:
            self._draw_cartesian(c, w, h, pad)

    # ---- Cartesian (bar, line, area, stacked) ----

    def _draw_cartesian(self, c: Canvas, w: int, h: int, pad: int):
        top = 34
        chart_h = h - top - 20
        if chart_h < 30:
            return

        vals = self._series_values()
        if not vals:
            return

        if self.chart_type == "bar":
            self._draw_bar(c, w, h, pad, top, chart_h, vals)
        else:
            self._draw_line_area_stacked(c, w, h, pad, top, chart_h, vals)

    def _series_values(self):
        """Return list of (y1, y2) per sample depending on data_series."""
        if self.data_series == "activity":
            return [(s[0], s[1]) for s in self.samples]  # (sec, rej)
        elif self.data_series == "latency":
            return [(s[2], 0) for s in self.samples]  # latency only
        else:
            return [(s[3], 0) for s in self.samples]  # tokens

    def _series_label(self, idx: int = 0) -> str:
        """Label for the primary (idx=0) or secondary (idx=1) series."""
        if self.data_series == "latency":
            return "Latency" if idx == 0 else ""
        if self.data_series == "tokens":
            return "Tokens" if idx == 0 else ""
        return "Activity" if idx == 0 else "Rejected"

    def _draw_bar(self, c, w, h, pad, top, chart_h, vals):
        max_bar_h = chart_h - 24
        total_sec = sum(a for a, _ in vals)
        total_rej = sum(b for _, b in vals)
        grand = max(total_sec + total_rej, 1)

        if self.data_series == "activity":
            items = [("Secure", total_sec, GREEN), ("Rejected", total_rej, RED)]
        else:
            label = "Latency (ms)" if self.data_series == "latency" else "Tokens"
            items = [(label, total_sec, GREEN)]

        bar_w = 46
        gap = 30
        n_bars = len(items)
        pair_w = n_bars * bar_w + (n_bars - 1) * gap
        start_x = max(pad, (w - pair_w) / 2)

        y1 = top + max_bar_h
        for frac in (0.25, 0.5, 0.75, 1.0):
            gy = y1 - frac * max_bar_h
            c.create_line(pad, gy, w - pad, gy, fill=BORDER, width=1)

        for i, (label, count, color) in enumerate(items):
            x0 = start_x + i * (bar_w + gap)
            x1 = x0 + bar_w
            bar_h = int((count / grand) * max_bar_h) if grand else 0
            y0 = y1 - bar_h
            pct = round(100 * count / grand) if grand else 0

            c.create_rectangle(x0, top, x1, y1, outline=BORDER, fill=BG_CARD)
            if bar_h > 0:
                c.create_rectangle(x0, y0, x1, y1, outline="", fill=color)
                cap_h = min(4, bar_h)
                c.create_rectangle(x0, y0, x1, y0 + cap_h, outline="",
                                   fill=TEXT, stipple="gray25")
            c.create_text((x0 + x1) / 2, y1 + 10, fill=MUTED,
                          font=("Consolas", 8), text=label)
            c.create_text((x0 + x1) / 2, top - 8, fill=TEXT,
                          font=("Consolas", 9, "bold"),
                          text=f"{count} ({pct}%)")

    def _draw_line_area_stacked(self, c, w, h, pad, top, chart_h, vals):
        n = len(vals)
        if n < 2:
            c.create_text(w // 2, top + chart_h // 2, fill=MUTED,
                          font=("Consolas", 9), text="Need ≥ 2 samples")
            return

        usable_w = w - 2 * pad - 10
        step = usable_w / max(n - 1, 1)
        max_val = max(max(a + b for a, b in vals), 1)

        label1 = self._series_label(0)
        label2 = self._series_label(1)
        is_single = self.data_series != "activity"

        # Build point lists
        pts_sec = []
        pts_rej = []
        for i, (a, b) in enumerate(vals):
            x = pad + 10 + i * step
            y_sec = top + chart_h - (a / max_val) * chart_h
            y_rej = top + chart_h - (b / max_val) * chart_h
            pts_sec.append((x, y_sec))
            pts_rej.append((x, y_rej))

        if self.chart_type == "line":
            self._draw_line(c, pts_sec, GREEN, label1)
            if not is_single:
                self._draw_line(c, pts_rej, RED, label2)

        elif self.chart_type == "area":
            self._draw_area(c, pts_sec, GREEN, chart_h, top, label1)
            if not is_single:
                self._draw_area(c, pts_rej, RED, chart_h, top, label2)

        elif self.chart_type == "stacked":
            if is_single:
                # Single band
                bot = [(x, top + chart_h) for x, _ in pts_sec]
                c.create_polygon(*[v for p in pts_sec + bot for v in p],
                                 fill=GREEN, outline=BORDER, width=1)
                c.create_text(pad + 10, top - 6, anchor="w", fill=GREEN,
                              font=("Consolas", 8), text=label1)
            else:
                pts_stacked = []
                for i, ((x_s, y_s), (x_r, y_r)) in enumerate(zip(pts_sec, pts_rej)):
                    sec_h = (vals[i][0] / max_val) * chart_h
                    rej_h = (vals[i][1] / max_val) * chart_h
                    y_cum = top + chart_h - (sec_h + rej_h)
                    pts_stacked.append((x_s, y_cum))

                bot = [(x, top + chart_h) for x, _ in pts_rej]
                c.create_polygon(*[v for p in pts_rej + bot for v in p],
                                 fill=RED, outline=BORDER, width=1)
                c.create_polygon(*[v for p in pts_stacked + pts_rej[::-1] for v in p],
                                 fill=GREEN, outline=BORDER, width=1)

                c.create_text(pad + 10, top - 6, anchor="w", fill=GREEN,
                              font=("Consolas", 8), text=label1)
                c.create_text(pad + 10 + 70, top - 6, anchor="w", fill=RED,
                              font=("Consolas", 8), text=label2)

    def _draw_line(self, c, pts, color, label):
        points = [v for p in pts for v in p]
        if len(points) >= 4:
            c.create_line(*points, fill=color, width=2, smooth=True)
        if pts:
            c.create_oval(pts[0][0] - 2, pts[0][1] - 2,
                          pts[0][0] + 2, pts[0][1] + 2,
                          fill=color, outline="")
            c.create_oval(pts[-1][0] - 2, pts[-1][1] - 2,
                          pts[-1][0] + 2, pts[-1][1] + 2,
                          fill=color, outline="")
        # Legend
        c.create_text(14, -4, anchor="w", fill=color,
                      font=("Consolas", 8), text=label)

    def _draw_area(self, c, pts, color, chart_h, top, label=""):
        if not pts:
            return
        bottom = [(pts[-1][0], top + chart_h), (pts[0][0], top + chart_h)]
        poly = pts + bottom
        flat = [v for p in poly for v in p]
        c.create_polygon(*flat, fill=color, stipple="gray25", outline=color, width=1)
        line_pts = [v for p in pts for v in p]
        if len(line_pts) >= 4:
            c.create_line(*line_pts, fill=color, width=2, smooth=True)
        if label:
            c.create_text(14, -4, anchor="w", fill=color,
                          font=("Consolas", 8), text=label)

    # ---- Donut ----

    def _draw_donut(self, c, w, h, pad):
        if not self.samples:
            return

        cx = w // 2
        cy = h // 2 - 10
        r = min(w, h) // 2 - 30
        inner_r = r - 20

        if self.data_series == "activity":
            total_sec = sum(s[0] for s in self.samples)
            total_rej = sum(s[1] for s in self.samples)
            grand = total_sec + total_rej
            if grand == 0:
                return
            segments = [("Secure", total_sec, GREEN), ("Rejected", total_rej, RED)]
            center_label = "secure"
        elif self.data_series == "latency":
            vals = [s[2] for s in self.samples]
            fast = sum(1 for v in vals if v < 30)
            mod = sum(1 for v in vals if 30 <= v < 60)
            slow = sum(1 for v in vals if v >= 60)
            grand = max(len(vals), 1)
            segments = [("Fast", fast, GREEN), ("Moderate", mod, YELLOW), ("Slow", slow, RED)]
            center_label = "latency"
        else:
            vals = [s[3] for s in self.samples]
            small = sum(1 for v in vals if v < 10)
            med = sum(1 for v in vals if 10 <= v < 20)
            lrg = sum(1 for v in vals if v >= 20)
            grand = max(len(vals), 1)
            segments = [("Small", small, GREEN), ("Medium", med, YELLOW), ("Large", lrg, RED)]
            center_label = "tokens"

        segments = [(l, c, col) for l, c, col in segments if c > 0]

        start = 90.0
        for label, count, color in segments:
            extent = 360.0 * (count / grand)
            c.create_arc(cx - r, cy - r, cx + r, cy + r,
                         start=start, extent=-extent,
                         fill=color, outline=BORDER, width=1)
            start -= extent

        # Inner circle (hollow)
        c.create_oval(cx - inner_r, cy - inner_r,
                      cx + inner_r, cy + inner_r,
                      fill=BG, outline="")

        # Center text
        total_val = sum(c for _, c, _ in segments)
        c.create_text(cx, cy - 8, fill=TEXT,
                      font=("Consolas", 9, "bold"),
                      text=f"{total_val}")
        c.create_text(cx, cy + 8, fill=MUTED,
                      font=("Consolas", 7),
                      text=center_label)

        # Legend
        leg_x = cx - 60
        for i, (label, count, color) in enumerate(segments):
            c.create_text(leg_x, h - 14 + i * 14, anchor="w", fill=color,
                          font=("Consolas", 8), text=f"● {label} {count}")
