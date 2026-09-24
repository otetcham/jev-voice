"""Windows Native High-DPI Floating Voice Pill & Antigravity Round Box Overlay.
100% faithful reproduction of user design specification:
- Solid Voice Pill: height 44px, padding 0 20px, border-radius 9999px, background #0f172a, border 1px solid rgba(99, 102, 241, 0.6)
- audio-pill-pulse 2.8s: box-shadow: 0 0 10px rgba(99, 102, 241, 0.35) -> 0 0 24px rgba(99, 102, 241, 0.70)
- Left Round Box (.round-box): 44x44px, border-radius 50%, background #4f46e5, border 2px solid #818cf8, white bold 12px
- dot-pop animation: 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) scale 0 -> 1.18 -> 1
- High-fidelity 2x Super-Sampling Anti-Aliasing (SSAA)
- Beautiful Japanese font rendering (Yu Gothic UI / Meiryo)
"""
from __future__ import annotations

import ctypes
import math
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable

from PIL import Image, ImageDraw, ImageFont, ImageTk

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

# Set Process DPI Awareness
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
TRANS_RGB = (1, 1, 1)

# Find crisp Japanese font on Windows
FONT_PATH = None
candidates = [
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
]
for p in candidates:
    if os.path.exists(p):
        FONT_PATH = p
        break


def _cubic_bezier_pop(t: float) -> float:
    """Approximation of cubic-bezier(0.34, 1.56, 0.64, 1) for 0 <= t <= 1."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.7:
        progress = t / 0.7
        return 1.18 * math.sin(progress * math.pi / 2)
    else:
        progress = (t - 0.7) / 0.3
        return 1.18 - 0.18 * math.sin(progress * math.pi / 2)


def draw_capsule_solid(draw_target, x, y, width, height, fill=None, outline=None, outline_w=1):
    r = height / 2.0
    if fill:
        draw_target.ellipse([x, y, x + height, y + height], fill=fill, outline=None)
        draw_target.ellipse([x + width - height, y, x + width, y + height], fill=fill, outline=None)
        draw_target.rectangle([x + r, y, x + width - r, y + height], fill=fill, outline=None)
    if outline and outline_w > 0:
        draw_target.arc([x, y, x + height, y + height], start=90, end=270, fill=outline, width=outline_w)
        draw_target.arc([x + width - height, y, x + width, y + height], start=270, end=90, fill=outline, width=outline_w)
        draw_target.line([x + r, y, x + width - r, y], fill=outline, width=outline_w)
        draw_target.line([x + r, y + height, x + width - r, y + height], fill=outline, width=outline_w)


@dataclass
class AgyTask:
    task_id: str
    label: str
    created_at: float


class WindowsOverlay:
    """Pixel-perfect, high-DPI Floating Voice Pill & Antigravity Round Box Overlay."""

    def __init__(self) -> None:
        self.root = None
        self.label_widget = None
        self._current_photo = None
        self.q: queue.Queue[tuple[str, ...]] = queue.Queue()
        self._revert_timer = None
        self.scale = 1.0

        # State
        self.state = "idle"
        self.text = "音声入力中"
        self.tasks: list[AgyTask] = []
        self._task_counter = 1

        self.font_pill = None
        self.font_round = None

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

    def _render_frame(self, w: int, h: int, text: str, state: str, now: float) -> Image.Image:
        # 2x Super-Sampling Anti-Aliasing (SSAA)
        SSAA = 2
        W, H = w * SSAA, h * SSAA

        im = Image.new("RGB", (W, H), TRANS_RGB)
        draw = ImageDraw.Draw(im)

        # Pulse phase (2.8s period)
        pulse_phase = 0.5 - 0.5 * math.cos(((now % 2.8) / 2.8) * 2 * math.pi)

        # Truncate text if very long
        display_text = text
        if len(display_text) > 32:
            display_text = display_text[:30] + "…"

        bbox = draw.textbbox((0, 0), display_text, font=self.font_pill)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pill_pad_x = 20 * self.scale * SSAA
        pill_h = 44 * self.scale * SSAA
        pill_w = max(pill_h, text_w + pill_pad_x * 2)

        num_tasks = len(self.tasks)
        round_size = 44 * self.scale * SSAA
        gap_rounds = 8 * self.scale * SSAA
        gap_to_pill = 10 * self.scale * SSAA

        total_content_w = (num_tasks * round_size + max(0, num_tasks - 1) * gap_rounds + (gap_to_pill if num_tasks > 0 else 0)) + pill_w
        pad_box = 20 * self.scale * SSAA
        start_x = W - pad_box - total_content_w
        start_y = pad_box

        pill_x = start_x + (num_tasks * round_size + max(0, num_tasks - 1) * gap_rounds + (gap_to_pill if num_tasks > 0 else 0))
        pill_y = start_y

        # 1. Glow / Box-Shadow Rings matching @keyframes audio-pill-pulse
        # box-shadow: 0 0 10px rgba(99, 102, 241, 0.35) -> 0 0 24px rgba(99, 102, 241, 0.70)
        if state == "listening":
            glow_intensity = pulse_phase
            glow_steps = [
                (int((6 + 4 * glow_intensity) * self.scale * SSAA), (30, 27, 75)),
                (int((4 + 2 * glow_intensity) * self.scale * SSAA), (49, 46, 129)),
                (int(2 * self.scale * SSAA), (67, 56, 202)),
            ]
            pill_border = (99, 102, 241)
        elif state == "done":
            glow_steps = [
                (int(4 * self.scale * SSAA), (6, 78, 59)),
                (int(2 * self.scale * SSAA), (16, 185, 129)),
            ]
            pill_border = (52, 211, 153)
        elif state == "error":
            glow_steps = [
                (int(4 * self.scale * SSAA), (127, 29, 29)),
                (int(2 * self.scale * SSAA), (239, 68, 68)),
            ]
            pill_border = (248, 113, 113)
        else: # thinking / other
            glow_steps = [
                (int(3 * self.scale * SSAA), (49, 46, 129)),
                (int(1 * self.scale * SSAA), (67, 56, 202)),
            ]
            pill_border = (99, 102, 241)

        for glow_offset, glow_color in glow_steps:
            draw_capsule_solid(
                draw,
                pill_x - glow_offset, pill_y - glow_offset,
                pill_w + glow_offset * 2, pill_h + glow_offset * 2,
                fill=None,
                outline=glow_color,
                outline_w=int(2 * self.scale * SSAA)
            )

        # 2. Left Round Boxes (.round-box) with dot-pop animation
        # width: 44px; height: 44px; border-radius: 50%;
        # background: #4f46e5; border: 2px solid #818cf8; color: #ffffff;
        curr_x = start_x
        for t in self.tasks:
            elapsed = now - t.created_at
            scale_pop = _cubic_bezier_pop(elapsed / 0.3) if elapsed < 0.3 else 1.0

            cur_round_size = round_size * scale_pop
            cx = curr_x + round_size / 2.0
            cy = start_y + round_size / 2.0
            rx0 = cx - cur_round_size / 2.0
            ry0 = cy - cur_round_size / 2.0
            rx1 = cx + cur_round_size / 2.0
            ry1 = cy + cur_round_size / 2.0

            if cur_round_size > 2:
                # Outer subtle glow for round box
                draw.ellipse(
                    [rx0 - 2 * SSAA, ry0 - 2 * SSAA, rx1 + 2 * SSAA, ry1 + 2 * SSAA],
                    fill=None,
                    outline=(49, 46, 129),
                    width=int(2 * SSAA)
                )
                # Main round box
                draw.ellipse(
                    [rx0, ry0, rx1, ry1],
                    fill=(79, 70, 229), # #4f46e5
                    outline=(129, 140, 248), # #818cf8
                    width=int(2 * self.scale * SSAA)
                )
                t_bbox = draw.textbbox((0, 0), t.label, font=self.font_round)
                tw = t_bbox[2] - t_bbox[0]
                th = t_bbox[3] - t_bbox[1]
                draw.text(
                    (cx - tw / 2.0, cy - th / 2.0 - 2 * SSAA),
                    t.label,
                    fill=(255, 255, 255),
                    font=self.font_round
                )

            curr_x += round_size + gap_rounds

        # 3. Pill Body
        # height: 44px; padding: 0 20px; border-radius: 9999px;
        # background: #0f172a; border: 1px solid rgba(99, 102, 241, 0.6);
        draw_capsule_solid(
            draw,
            pill_x, pill_y, pill_w, pill_h,
            fill=(15, 23, 42), # #0f172a
            outline=pill_border,
            outline_w=int(1 * self.scale * SSAA)
        )

        # 4. Pill Text
        # color: #e2e8f0; font-size: 13px; font-weight: 500;
        tx = pill_x + (pill_w - text_w) / 2.0
        ty = pill_y + (pill_h - text_h) / 2.0 - 2 * SSAA
        draw.text((tx, ty), display_text, fill=(226, 232, 240), font=self.font_pill)

        # Downsample with 2x Lanczos anti-aliasing
        final_im = im.resize((w, h), Image.Resampling.LANCZOS)

        # Clean background pixels to pure (1, 1, 1) for crystal clear colorkey transparency
        pix = final_im.load()
        for ix in range(w):
            for iy in range(h):
                r, g, b = pix[ix, iy]
                if r <= 3 and g <= 3 and b <= 3:
                    pix[ix, iy] = TRANS_RGB

        return final_im

    def _poll_queue(self) -> None:
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

                    if self._revert_timer:
                        try:
                            self.root.after_cancel(self._revert_timer)
                        except Exception:
                            pass
                        self._revert_timer = None

                    if revert_after:
                        self._revert_timer = self.root.after(int(revert_after * 1000), self._auto_hide)

                elif action == "add_task":
                    _, tid, label = cmd
                    self.tasks.append(AgyTask(tid, label, now))

                elif action == "remove_task":
                    _, tid = cmd
                    self.tasks = [t for t in self.tasks if t.task_id != tid]

                elif action == "clear_tasks":
                    self.tasks.clear()

        except Exception:
            pass

        # Update visuals
        if self.state == "idle" and not self.tasks:
            self.root.withdraw()
        else:
            w = int(520 * self.scale)
            h = int(95 * self.scale)
            sw = user32.GetSystemMetrics(0) if user32 else 1920
            x = sw - w - int(12 * self.scale)
            y = int(12 * self.scale)

            img = self._render_frame(w, h, self.text, self.state, now)
            self._current_photo = ImageTk.PhotoImage(img)
            self.label_widget.config(image=self._current_photo)

            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.deiconify()
            self.root.attributes("-topmost", True)

        if self.root:
            self.root.after(35, self._poll_queue)

    def _auto_hide(self) -> None:
        self.state = "idle"
        if not self.tasks and self.root:
            self.root.withdraw()

    def run(self, worker: Callable[[], None]) -> None:
        import tkinter as tk

        self.root = tk.Tk()
        self.root.title("Jev Voice Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # Set transparent colorkey
        self.root.wm_attributes("-transparentcolor", TRANS_COLOR)
        self.root.config(bg=TRANS_COLOR)

        try:
            dpi = user32.GetDpiForSystem()
            self.scale = max(1.0, dpi / 96.0)
        except Exception:
            self.scale = 1.0

        # Load fonts
        SSAA = 2
        try:
            self.font_pill = ImageFont.truetype(FONT_PATH, int(13 * self.scale * SSAA))
            self.font_round = ImageFont.truetype(FONT_PATH, int(12 * self.scale * SSAA))
        except Exception:
            self.font_pill = ImageFont.load_default()
            self.font_round = ImageFont.load_default()

        self.label_widget = tk.Label(self.root, bg=TRANS_COLOR, bd=0)
        self.label_widget.pack(fill="both", expand=True)

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
