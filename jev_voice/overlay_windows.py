"""Windows Native High-DPI Floating Voice Pill & Antigravity Round Box Overlay.
Matches user UI specification:
- Solid dark pill (#0f172a) with 1px border (#6366f1) and 2.8s pulse animation
- Left round box (44x44px, #4f46e5 background, 2px solid #818cf8 border, white bold text)
- Dot-pop entry animation (0.3s cubic bezier overshoot)
- Dynamic task stacking on the left (gap 8px, pill gap 10px)
- Transparent background using native Windows colorkey
"""
from __future__ import annotations

import ctypes
import math
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

# Enable Per-Monitor V2 DPI awareness
if user32:
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

TRANS_COLOR = "#010101"

# Solid color palette
PILL_BG = "#0f172a"
PILL_BORDER_BASE = (99, 102, 241)     # #6366f1
PILL_TEXT_COLOR = "#e2e8f0"

ROUND_BG = "#4f46e5"
ROUND_BORDER = "#818cf8"
ROUND_TEXT_COLOR = "#ffffff"


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> str:
    r = int(c1[0] + (c2[0] - c1[0]) * t)
    g = int(c1[1] + (c2[1] - c1[1]) * t)
    b = int(c1[2] + (c2[2] - c1[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _cubic_bezier_pop(t: float) -> float:
    """Approximation of cubic-bezier(0.34, 1.56, 0.64, 1) for 0 <= t <= 1."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    # Overshoot peak around t=0.7 at 1.18, settling to 1.0
    if t < 0.7:
        progress = t / 0.7
        return 1.18 * math.sin(progress * math.pi / 2)
    else:
        progress = (t - 0.7) / 0.3
        return 1.18 - 0.18 * math.sin(progress * math.pi / 2)


@dataclass
class AgyTask:
    task_id: str
    label: str
    created_at: float


class WindowsOverlay:
    """Floating Voice Pill with Antigravity Task Round Boxes."""

    def __init__(self) -> None:
        self.root = None
        self.canvas = None
        self.q: queue.Queue[tuple[str, ...]] = queue.Queue()
        self._revert_job = None
        self.scale = 1.0

        # Current UI State
        self.state = "idle"
        self.text = "音声入力中"
        self.tasks: list[AgyTask] = []
        self._task_counter = 1

        self.font_family = "Segoe UI Variable Text"
        self.start_time = time.time()

    # Public API called from any thread
    def set(self, state: str, text: str = "", revert_after: float | None = None) -> None:
        self.q.put(("set", state, text, revert_after))

    def add_task(self, label: str = "AGY") -> str:
        tid = f"task_{self._task_counter}"
        self._task_counter += 1
        self.q.put(("add_task", tid, label))
        return tid

    def remove_task(self, task_id: str) -> None:
        self.q.put(("remove_task", task_id))

    def clear_tasks(self) -> None:
        self.q.put(("clear_tasks",))

    def _poll_queue(self) -> None:
        redraw_needed = False
        now = time.time()

        try:
            while not self.q.empty():
                cmd = self.q.get_nowait()
                action = cmd[0]
                if action == "set":
                    _, state, text, revert_after = cmd
                    self.state = state
                    if text:
                        self.text = text
                    elif state == "listening":
                        self.text = "音声入力中"
                    elif state == "thinking":
                        self.text = "解析中…"
                    elif state == "done":
                        self.text = "完了"

                    if self._revert_job and self.root:
                        try:
                            self.root.after_cancel(self._revert_job)
                        except Exception:
                            pass
                        self._revert_job = None

                    if revert_after and self.root:
                        self._revert_job = self.root.after(int(revert_after * 1000), self._auto_hide)

                    redraw_needed = True

                elif action == "add_task":
                    _, tid, label = cmd
                    self.tasks.append(AgyTask(tid, label, now))
                    redraw_needed = True

                elif action == "remove_task":
                    _, tid = cmd
                    self.tasks = [t for t in self.tasks if t.task_id != tid]
                    redraw_needed = True

                elif action == "clear_tasks":
                    self.tasks.clear()
                    redraw_needed = True

        except Exception:
            pass

        # Also animate pulse if listening or popping if recent task
        has_animating_task = any((now - t.created_at) < 0.4 for t in self.tasks)
        if self.state in ("listening", "thinking") or has_animating_task or redraw_needed:
            self._redraw()

        if self.root:
            self.root.after(35, self._poll_queue)

    def _auto_hide(self) -> None:
        self.state = "idle"
        self._redraw()

    def _draw_pill(self, x0: float, y0: float, x1: float, y1: float, border_color: str, glow: bool = False) -> None:
        h = y1 - y0
        r = h / 2.0

        if glow:
            # Subtle glow ring for audio-pill-pulse
            glow_color = _lerp_color((15, 23, 42), (99, 102, 241), 0.35)
            self.canvas.create_oval(x0 - 2, y0 - 2, x0 + 2 * r + 2, y1 + 2, fill="", outline=glow_color, width=2, tags="pill")
            self.canvas.create_oval(x1 - 2 * r - 2, y0 - 2, x1 + 2, y1 + 2, fill="", outline=glow_color, width=2, tags="pill")
            self.canvas.create_line(x0 + r, y0 - 2, x1 - r, y0 - 2, fill=glow_color, width=2, tags="pill")
            self.canvas.create_line(x0 + r, y1 + 2, x1 - r, y1 + 2, fill=glow_color, width=2, tags="pill")

        # Solid body
        self.canvas.create_oval(x0, y0, x0 + 2 * r, y1, fill=PILL_BG, outline="", tags="pill")
        self.canvas.create_oval(x1 - 2 * r, y0, x1, y1, fill=PILL_BG, outline="", tags="pill")
        self.canvas.create_rectangle(x0 + r, y0, x1 - r, y1, fill=PILL_BG, outline="", tags="pill")

        # 1px border
        self.canvas.create_arc(x0, y0, x0 + 2 * r, y1, start=90, extent=180, style="arc", outline=border_color, width=1, tags="pill")
        self.canvas.create_arc(x1 - 2 * r, y0, x1, y1, start=270, extent=180, style="arc", outline=border_color, width=1, tags="pill")
        self.canvas.create_line(x0 + r, y0, x1 - r, y0, fill=border_color, width=1, tags="pill")
        self.canvas.create_line(x0 + r, y1, x1 - r, y1, fill=border_color, width=1, tags="pill")

    def _draw_round_box(self, cx: float, cy: float, size: float, scale_factor: float, text: str) -> None:
        r = (size / 2.0) * scale_factor
        if r <= 1:
            return

        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ROUND_BG, outline=ROUND_BORDER, width=max(1, int(2 * self.scale)), tags="round_box")

        font_size = max(8, int(11 * self.scale * scale_factor))
        self.canvas.create_text(
            cx, cy,
            text=text,
            fill=ROUND_TEXT_COLOR,
            font=(self.font_family, font_size, "bold"),
            tags="round_box"
        )

    def _redraw(self) -> None:
        if not self.root or not self.canvas:
            return

        # If idle and no tasks, withdraw
        if self.state == "idle" and not self.tasks:
            self.root.withdraw()
            return

        self.canvas.delete("all")
        now = time.time()

        box_size = 44.0 * self.scale
        box_gap = 8.0 * self.scale
        pill_gap = 10.0 * self.scale
        pad_x = 20.0 * self.scale
        pill_h = 44.0 * self.scale
        outer_pad = 6.0 * self.scale  # Padding to prevent glow cutoff

        # Calculate text width
        font_size = max(9, int(11 * self.scale))
        font_spec = (self.font_family, font_size, "normal")

        # Truncate text if very long
        display_text = self.text
        if len(display_text) > 30:
            display_text = display_text[:28] + "…"

        # Measure text using canvas temporary text item
        temp_id = self.canvas.create_text(-1000, -1000, text=display_text, font=font_spec)
        bbox = self.canvas.bbox(temp_id)
        self.canvas.delete(temp_id)
        text_w = (bbox[2] - bbox[0]) if bbox else int(70 * self.scale)

        pill_w = max(pill_h, text_w + pad_x * 2)

        # Pulse animation calculation: 2.8s period
        # 0%, 100% -> rgba(99, 102, 241, 0.35)
        # 50% -> rgba(99, 102, 241, 0.70)
        pulse_phase = (now % 2.8) / 2.8
        pulse_intensity = 0.5 - 0.5 * math.cos(pulse_phase * 2 * math.pi)  # 0.0 to 1.0

        if self.state == "listening":
            c_dim = (67, 56, 202)    # #4338ca
            c_bright = (129, 140, 248) # #818cf8
            border_color = _lerp_color(c_dim, c_bright, pulse_intensity)
            show_glow = pulse_intensity > 0.4
        elif self.state == "done":
            border_color = "#34d399"  # green-400
            show_glow = False
        elif self.state == "error":
            border_color = "#f87171"  # red-400
            show_glow = False
        else:
            border_color = "#6366f1"
            show_glow = False

        # Compute total dimensions
        num_tasks = len(self.tasks)
        tasks_total_w = (num_tasks * box_size + max(0, num_tasks - 1) * box_gap) if num_tasks > 0 else 0.0
        total_w = outer_pad * 2 + tasks_total_w + (pill_gap if num_tasks > 0 else 0) + pill_w
        total_h = outer_pad * 2 + pill_h

        # Position elements from left to right
        curr_x = outer_pad
        cy = outer_pad + pill_h / 2.0

        # Draw left round boxes (Antigravity tasks)
        for t in self.tasks:
            elapsed = now - t.created_at
            if elapsed < 0.3:
                pop_scale = _cubic_bezier_pop(elapsed / 0.3)
            else:
                pop_scale = 1.0

            cx = curr_x + box_size / 2.0
            self._draw_round_box(cx, cy, box_size, pop_scale, t.label)
            curr_x += box_size + box_gap

        if num_tasks > 0:
            curr_x += pill_gap - box_gap

        # Draw pill
        pill_x0 = curr_x
        pill_y0 = outer_pad
        pill_x1 = pill_x0 + pill_w
        pill_y1 = pill_y0 + pill_h

        self._draw_pill(pill_x0, pill_y0, pill_x1, pill_y1, border_color, glow=show_glow)

        # Draw pill text
        self.canvas.create_text(
            (pill_x0 + pill_x1) / 2.0,
            cy,
            text=display_text,
            fill=PILL_TEXT_COLOR,
            font=font_spec,
            tags="pill"
        )

        # Position window on screen (top-right margin 24px)
        w_int = int(math.ceil(total_w))
        h_int = int(math.ceil(total_h))

        sw = user32.GetSystemMetrics(0) if user32 else 1920
        margin_x = int(24 * self.scale)
        margin_y = int(24 * self.scale)
        win_x = sw - w_int - margin_x
        win_y = margin_y

        self.root.geometry(f"{w_int}x{h_int}+{win_x}+{win_y}")
        self.canvas.config(width=w_int, height=h_int)
        self.root.deiconify()
        self.root.attributes("-topmost", True)

    def run(self, worker: Callable[[], None]) -> None:
        import tkinter as tk
        import tkinter.font as tkfont

        self.root = tk.Tk()
        self.root.title("Jev Voice Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # Transparent background via Windows colorkey
        self.root.wm_attributes("-transparentcolor", TRANS_COLOR)
        self.root.config(bg=TRANS_COLOR)

        try:
            dpi = user32.GetDpiForSystem()
            self.scale = max(1.0, dpi / 96.0)
        except Exception:
            self.scale = 1.0

        try:
            families = tkfont.families(self.root)
            if "Segoe UI Variable Text" in families:
                self.font_family = "Segoe UI Variable Text"
            elif "Segoe UI" in families:
                self.font_family = "Segoe UI"
            elif "Yu Gothic UI" in families:
                self.font_family = "Yu Gothic UI"
            else:
                self.font_family = "Helvetica"
        except Exception:
            self.font_family = "Segoe UI"

        self.canvas = tk.Canvas(
            self.root,
            bg=TRANS_COLOR,
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill="both", expand=True)

        self.root.withdraw()
        self.root.after(35, self._poll_queue)

        def _th() -> None:
            try:
                worker()
            finally:
                if self.root:
                    self.root.after(0, self.root.destroy)

        threading.Thread(target=_th, daemon=True, name="jev-worker").start()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass


class NullOverlay:
    def set(self, state: str, text: str = "", revert_after: float | None = None) -> None:
        pass

    def add_task(self, label: str = "AGY") -> str:
        return "noop"

    def remove_task(self, task_id: str) -> None:
        pass

    def clear_tasks(self) -> None:
        pass

    def run(self, worker: Callable[[], None]) -> None:
        worker()


Overlay = WindowsOverlay
