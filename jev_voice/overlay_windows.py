"""Windows Native High-DPI Floating Voice Pill & Antigravity Round Box Overlay.
Full implementation:
1. True 32-bit Per-Pixel Alpha layered window (UpdateLayeredWindow) for genuine ambient glowing aura.
2. Animated real-time audio volume equalizer bars reacting to microphone input.
3. Interactive drag-and-drop to position the overlay anywhere on the screen.
4. Faithful reproduction of user design specification:
   - Solid Voice Pill: height 44px, padding 0 20px, border-radius 9999px, #0f172a, 1px solid rgba(99, 102, 241, 0.6)
   - Left Round Box: 44x44px, #4f46e5, 2px solid #818cf8, white bold 12px with dot-pop animation
   - High-fidelity 2x Super-Sampling Anti-Aliasing (SSAA)
   - Crisp Japanese typography (Yu Gothic UI / Meiryo)
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
gdi32 = ctypes.windll.gdi32 if sys.platform == "win32" else None

# Win32 Constants
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01

# Enable Per-Monitor DPI Awareness
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


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


if gdi32 and user32:
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]

    user32.ReleaseDC.restype = ctypes.c_int
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]

    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    gdi32.CreateDIBSection.restype = wintypes.HANDLE
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(BITMAPINFOHEADER),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]

    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]

    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]

    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND,
        wintypes.HDC,
        ctypes.POINTER(POINT),
        ctypes.POINTER(SIZE),
        wintypes.HDC,
        ctypes.POINTER(POINT),
        wintypes.COLORREF,
        ctypes.POINTER(BLENDFUNCTION),
        wintypes.DWORD,
    ]

    SetWindowLong = user32.SetWindowLongPtrW if hasattr(user32, "SetWindowLongPtrW") else user32.SetWindowLongW
    GetWindowLong = user32.GetWindowLongPtrW if hasattr(user32, "GetWindowLongPtrW") else user32.GetWindowLongW


# Find high quality Japanese font
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


def draw_capsule(draw_target, x, y, width, height, fill=None, outline=None, outline_w=1):
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
    label: str = "AGY"
    status: str = "running"  # "running", "done", "error"
    created_at: float = 0.0
    finished_at: float | None = None
    log_lines: list[str] = field(default_factory=list)
    rect: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # Screen coords


class ConsolePopup:
    """Floating terminal-like console popup displaying real-time task logs on mouse hover."""

    def __init__(self, root: Any, scale: float = 1.0) -> None:
        import tkinter as tk

        self.root = root
        self.scale = scale
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg="#090d16", padx=10, pady=8)

        # Highlight border
        self.top.configure(highlightbackground="#6366f1", highlightcolor="#6366f1", highlightthickness=1)

        # Header Frame
        hdr = tk.Frame(self.top, bg="#090d16")
        hdr.pack(fill="x", pady=(0, 6))

        self.lbl_title = tk.Label(
            hdr,
            text="⚡ Antigravity CLI · [AGY]",
            font=("Segoe UI", int(9.5 * scale), "bold"),
            fg="#c7d2fe",
            bg="#090d16",
        )
        self.lbl_title.pack(side="left")

        self.lbl_status = tk.Label(
            hdr,
            text="RUNNING ⏳",
            font=("Segoe UI", int(8.5 * scale), "bold"),
            fg="#38bdf8",
            bg="#090d16",
        )
        self.lbl_status.pack(side="right")

        # Text Console Log Area
        font_family = "Cascadia Code" if os.path.exists(r"C:\Windows\Fonts\cascadia.ttf") else "Consolas"
        self.txt = tk.Text(
            self.top,
            height=7,
            width=50,
            bg="#040711",
            fg="#94a3b8",
            font=(font_family, int(9 * scale)),
            bd=0,
            padx=8,
            pady=6,
            wrap="word",
        )
        self.txt.pack(fill="both", expand=True)
        self.txt.configure(state="disabled")

        self.visible = False
        self.current_task_id = None
        self.top.withdraw()

    def show_task(self, task: AgyTask, anchor_cx: float, anchor_cy: float, main_x: int, main_y: int, main_h: int) -> None:
        self.current_task_id = task.task_id

        # Title & Status styling
        self.lbl_title.config(text=f"⚡ Task · [{task.label}] #{task.task_id}")
        if task.status == "running":
            self.lbl_status.config(text="RUNNING ⏳", fg="#38bdf8")
        elif task.status == "done":
            self.lbl_status.config(text="COMPLETED ✓", fg="#34d399")
        elif task.status == "error":
            self.lbl_status.config(text="FAILED ✗", fg="#f87171")

        # Update log content
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        if task.log_lines:
            content = "\n".join(task.log_lines[-10:]) + "\n"
        else:
            content = f"Initializing task [{task.label}]...\nAwaiting console output...\n"
        self.txt.insert("end", content)
        self.txt.see("end")
        self.txt.configure(state="disabled")

        pop_w = int(430 * self.scale)
        pop_h = int(175 * self.scale)

        sw = user32.GetSystemMetrics(0) if user32 else 1920
        sh = user32.GetSystemMetrics(1) if user32 else 1080

        px = int(anchor_cx - pop_w / 2.0)
        px = max(10, min(px, sw - pop_w - 10))

        if main_y + main_h + pop_h + 20 < sh:
            py = int(main_y + main_h + 6)
        else:
            py = int(main_y - pop_h - 6)

        self.top.geometry(f"{pop_w}x{pop_h}+{px}+{py}")
        if not self.visible:
            self.top.deiconify()
            self.top.attributes("-topmost", True)
            self.visible = True

    def update_task_log(self, task: AgyTask) -> None:
        if self.visible and self.current_task_id == task.task_id:
            self.txt.configure(state="normal")
            self.txt.delete("1.0", "end")
            content = "\n".join(task.log_lines[-10:]) + "\n"
            self.txt.insert("end", content)
            self.txt.see("end")
            self.txt.configure(state="disabled")

    def hide(self) -> None:
        if self.visible:
            self.top.withdraw()
            self.visible = False
            self.current_task_id = None


class WindowsOverlay:
    """True 32-bit ARGB layered floating overlay with genuine Gaussian aura, audio meter, and drag-and-drop."""

    def __init__(self) -> None:
        self.root = None
        self.hwnd = None
        self.console_popup: ConsolePopup | None = None
        self.q: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._revert_timer = None
        self.scale = 1.0

        # State
        self.state = "idle"
        self.text = "音声入力中"
        self.tasks: list[AgyTask] = []
        self._task_counter = 1

        # Audio volume visualization & dynamic bar expansion
        self.target_audio_level = 0.0
        self.smoothed_audio_level = 0.0
        self.bar_expansion = 0.0

        # Positioning & Dragging
        self.win_x = None
        self.win_y = None
        self.win_w = 540
        self.win_h = 110
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False

        self.font_pill = None
        self.font_round = None

    def set(self, state: str, text: str = "", revert_after: float | None = None) -> None:
        clean_text = text
        for pfx in ("Antigravity:", "Antigravity CLI:", "Antigravity CLIで", "Antigravity"):
            if clean_text.startswith(pfx):
                clean_text = clean_text[len(pfx):].lstrip(" :で")
                break
        self.q.put(("set", state, clean_text, revert_after))

    def set_audio_level(self, level: float) -> None:
        """Set current microphone volume level (RMS ~ 0.0 to 1.0)."""
        self.target_audio_level = max(0.0, min(1.0, float(level)))

    def add_task(self, label: str = "AGY", status: str = "running") -> str:
        tid = f"task_{self._task_counter}"
        self._task_counter += 1
        self.q.put(("add_task", tid, label, status))
        return tid

    def update_task_log(self, task_id: str, line: str) -> None:
        self.q.put(("update_task_log", task_id, line))

    def complete_task(self, task_id: str, status: str = "done") -> None:
        self.q.put(("complete_task", task_id, status))

    def remove_task(self, task_id: str) -> None:
        self.q.put(("remove_task", task_id))

    def clear_tasks(self) -> None:
        self.q.put(("clear_tasks",))

    def _render_frame(self, w: int, h: int, text: str, state: str, now: float) -> Image.Image:
        SCALE = 2
        W, H = w * SCALE, h * SCALE

        # True 32-bit RGBA image
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        # Pulse phase (2.8s period)
        pulse_phase = 0.5 - 0.5 * math.cos(((now % 2.8) / 2.8) * 2 * math.pi)

        # Smooth audio meter level
        self.smoothed_audio_level += (self.target_audio_level - self.smoothed_audio_level) * 0.35

        # Truncate text if needed
        display_text = text
        if len(display_text) > 30:
            display_text = display_text[:28] + "…"

        draw = ImageDraw.Draw(im)
        bbox = draw.textbbox((0, 0), display_text, font=self.font_pill)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Voice Activity Detection (VAD) & Dynamic Waveform Expansion
        VAD_THRESHOLD = 0.015
        is_speaking = (state == "listening" and self.smoothed_audio_level > VAD_THRESHOLD)
        target_expansion = 1.0 if is_speaking else 0.0
        self.bar_expansion += (target_expansion - self.bar_expansion) * 0.25

        # 5 Dynamic / Stationary Equalizer Bars (Always Visible)
        num_bars = 5
        cur_bar_w = (3.0 + 1.2 * self.bar_expansion) * self.scale * SCALE
        cur_bar_gap = (2.5 + 2.0 * self.bar_expansion) * self.scale * SCALE
        meter_w = num_bars * cur_bar_w + (num_bars - 1) * cur_bar_gap
        meter_gap = 10 * self.scale * SCALE

        pill_pad_x = 20 * self.scale * SCALE
        pill_h = 44 * self.scale * SCALE
        pill_w = max(pill_h, text_w + meter_w + meter_gap + pill_pad_x * 2)

        num_tasks = len(self.tasks)
        round_size = 44 * self.scale * SCALE
        gap_rounds = 8 * self.scale * SCALE
        gap_to_pill = 10 * self.scale * SCALE

        total_content_w = (num_tasks * round_size + max(0, num_tasks - 1) * gap_rounds + (gap_to_pill if num_tasks > 0 else 0)) + pill_w
        pad_box = 28 * self.scale * SCALE
        start_x = W - pad_box - total_content_w
        start_y = pad_box

        pill_x = start_x + (num_tasks * round_size + max(0, num_tasks - 1) * gap_rounds + (gap_to_pill if num_tasks > 0 else 0))
        pill_y = start_y

        # 1. Genuine Ambient Soft Gaussian Aura (box-shadow)
        if state == "listening":
            aura_blur = (10 + 14 * pulse_phase) * self.scale * SCALE
            aura_alpha = int(255 * (0.35 + 0.35 * pulse_phase))
            aura_color = (99, 102, 241, aura_alpha)
            pill_border = (99, 102, 241, 153)
        elif state == "done":
            aura_blur = 18 * self.scale * SCALE
            aura_color = (52, 211, 153, int(255 * 0.65))
            pill_border = (52, 211, 153, 200)
        elif state == "error":
            aura_blur = 18 * self.scale * SCALE
            aura_color = (248, 113, 113, int(255 * 0.65))
            pill_border = (248, 113, 113, 200)
        else:  # thinking / other
            aura_blur = 14 * self.scale * SCALE
            aura_color = (99, 102, 241, int(255 * 0.45))
            pill_border = (99, 102, 241, 153)

        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        draw_capsule(glow_draw, pill_x, pill_y, pill_w, pill_h, fill=aura_color)
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=aura_blur / 2.0))
        im.paste(glow_layer, (0, 0), glow_layer)

        draw = ImageDraw.Draw(im)

        # 2. Left Round Boxes (.round-box) with Status Dynamics & Hover Detection
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

            # Store hit-test rect in screen coordinates for hover popup
            if self.win_x is not None and self.win_y is not None:
                screen_rx0 = self.win_x + (rx0 / SCALE)
                screen_ry0 = self.win_y + (ry0 / SCALE)
                screen_rx1 = self.win_x + (rx1 / SCALE)
                screen_ry1 = self.win_y + (ry1 / SCALE)
                t.rect = (screen_rx0, screen_ry0, screen_rx1, screen_ry1)

            if cur_round_size > 2:
                if t.status == "done":
                    # Status Done: Emerald Green + Vector Checkmark (✓)
                    draw.ellipse(
                        [rx0, ry0, rx1, ry1],
                        fill=(16, 185, 129, 255),    # #10b981
                        outline=(52, 211, 153, 255), # #34d399
                        width=int(2 * self.scale * SCALE),
                    )
                    chk_size = cur_round_size * 0.38
                    p1 = (cx - chk_size * 0.45, cy + chk_size * 0.05)
                    p2 = (cx - chk_size * 0.10, cy + chk_size * 0.42)
                    p3 = (cx + chk_size * 0.52, cy - chk_size * 0.40)
                    draw.line([p1, p2, p3], fill=(255, 255, 255, 255), width=int(2.8 * self.scale * SCALE), joint="curve")

                elif t.status == "error":
                    # Status Error: Rose Red + Cross (✗)
                    draw.ellipse(
                        [rx0, ry0, rx1, ry1],
                        fill=(239, 68, 68, 255),
                        outline=(248, 113, 113, 255),
                        width=int(2 * self.scale * SCALE),
                    )
                    crs_size = cur_round_size * 0.28
                    draw.line([(cx - crs_size, cy - crs_size), (cx + crs_size, cy + crs_size)], fill=(255, 255, 255, 255), width=int(2.5 * self.scale * SCALE))
                    draw.line([(cx + crs_size, cy - crs_size), (cx - crs_size, cy + crs_size)], fill=(255, 255, 255, 255), width=int(2.5 * self.scale * SCALE))

                else:
                    # Status Running: Indigo background + rotating spinner ring!
                    draw.ellipse(
                        [rx0, ry0, rx1, ry1],
                        fill=(79, 70, 229, 255),      # #4f46e5
                        outline=(129, 140, 248, 180), # #818cf8
                        width=int(2 * self.scale * SCALE),
                    )
                    # Rotating Loading Spinner Arc
                    spin_angle = (now * 360 * 1.1) % 360
                    spin_len = 110
                    draw.arc(
                        [rx0 - 2 * SCALE, ry0 - 2 * SCALE, rx1 + 2 * SCALE, ry1 + 2 * SCALE],
                        start=spin_angle,
                        end=spin_angle + spin_len,
                        fill=(255, 255, 255, 240),
                        width=int(2.8 * self.scale * SCALE),
                    )
                    # Center Label ("AGY")
                    t_bbox = draw.textbbox((0, 0), t.label, font=self.font_round)
                    tw = t_bbox[2] - t_bbox[0]
                    th = t_bbox[3] - t_bbox[1]
                    draw.text(
                        (cx - tw / 2.0, cy - th / 2.0 - 2 * SCALE),
                        t.label,
                        fill=(255, 255, 255, 255),
                        font=self.font_round,
                    )

            curr_x += round_size + gap_rounds

        # 3. Pill Body (Solid #0f172a, border rgba(99, 102, 241, 0.6))
        draw_capsule(
            draw,
            pill_x, pill_y, pill_w, pill_h,
            fill=(15, 23, 42, 255),
            outline=pill_border,
            outline_w=int(1 * self.scale * SCALE),
        )

        # 4. Animated Audio Equalizer Volume Bars (Always Visible, Active ONLY while speaking)
        bar_x = pill_x + pill_pad_x
        base_heights = [5, 8, 12, 8, 5]
        mod_phase = (now * 11.0)
        flutter = [
            0.55 + 0.20 * math.sin(mod_phase),
            0.90 + 0.20 * math.sin(mod_phase + 1.3),
            1.00 + 0.20 * math.sin(mod_phase + 2.6),
            0.85 + 0.20 * math.sin(mod_phase + 3.9),
            0.50 + 0.20 * math.sin(mod_phase + 5.2),
        ]

        max_bar_h = 24 * self.scale * SCALE
        min_bar_h = 4 * self.scale * SCALE

        for i in range(num_bars):
            if is_speaking:
                active_h = min_bar_h + (max_bar_h - min_bar_h) * min(1.0, max(0.0, self.smoothed_audio_level * flutter[i] * 2.2))
                bh = max(min_bar_h, active_h * self.bar_expansion + base_heights[i] * (1.0 - self.bar_expansion) * self.scale * SCALE)
                bar_color = (165, 180, 252, 255)
            else:
                # Stationary waveform at rest
                bh = base_heights[i] * self.scale * SCALE
                bar_color = (129, 140, 248, 180)

            bx = bar_x + i * (cur_bar_w + cur_bar_gap)
            by = pill_y + (pill_h - bh) / 2.0
            draw.rounded_rectangle(
                [bx, by, bx + cur_bar_w, by + bh],
                radius=cur_bar_w / 2.0,
                fill=bar_color,
            )

        # 5. Pill Text
        tx = bar_x + meter_w + meter_gap
        ty = pill_y + (pill_h - text_h) / 2.0 - 2 * SCALE
        draw.text((tx, ty), display_text, fill=(226, 232, 240, 255), font=self.font_pill)

        return im.resize((w, h), Image.Resampling.LANCZOS)

    def _update_layered_window(self, pil_img: Image.Image) -> bool:
        if not self.hwnd or not user32 or not gdi32:
            return False

        w, h = pil_img.size
        raw = pil_img.tobytes()
        arr = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 4))

        # Premultiply alpha for AC_SRC_ALPHA
        r = arr[:, :, 0].astype(np.uint32)
        g = arr[:, :, 1].astype(np.uint32)
        b = arr[:, :, 2].astype(np.uint32)
        a = arr[:, :, 3].astype(np.uint32)

        pr = ((r * a) // 255).astype(np.uint8)
        pg = ((g * a) // 255).astype(np.uint8)
        pb = ((b * a) // 255).astype(np.uint8)
        pa = arr[:, :, 3]  # uint8
        bgra = np.dstack([pb, pg, pr, pa]).tobytes()

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h  # top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        p_bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(p_bits), None, 0)
        if not hbmp or not p_bits.value:
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)
            return False

        dest = ctypes.c_void_p(p_bits.value)
        ctypes.memmove(dest, bgra, len(bgra))
        old_bmp = gdi32.SelectObject(hdc_mem, hbmp)

        pt_src = POINT(0, 0)
        size_wnd = SIZE(w, h)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

        res = user32.UpdateLayeredWindow(
            self.hwnd, hdc_screen, None, ctypes.byref(size_wnd),
            hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA
        )

        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        return bool(res)

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
                    _, tid, label, status = cmd
                    self.tasks.append(AgyTask(task_id=tid, label=label, status=status, created_at=now))

                elif action == "update_task_log":
                    _, tid, line = cmd
                    for t in self.tasks:
                        if t.task_id == tid:
                            t.log_lines.append(line)
                            if len(t.log_lines) > 30:
                                t.log_lines = t.log_lines[-30:]
                            if self.console_popup:
                                self.console_popup.update_task_log(t)
                            break

                elif action == "complete_task":
                    _, tid, status = cmd
                    for t in self.tasks:
                        if t.task_id == tid:
                            t.status = status
                            t.finished_at = now
                            if self.console_popup:
                                self.console_popup.update_task_log(t)
                            break

                elif action == "remove_task":
                    _, tid = cmd
                    self.tasks = [t for t in self.tasks if t.task_id != tid]
                    if self.console_popup and self.console_popup.current_task_id == tid:
                        self.console_popup.hide()

                elif action == "clear_tasks":
                    self.tasks.clear()
                    if self.console_popup:
                        self.console_popup.hide()

        except Exception:
            pass

        # Auto-remove completed tasks after 6 seconds so user can see completion checkmark
        self.tasks = [
            t for t in self.tasks
            if not (t.finished_at and (now - t.finished_at > 6.0))
        ]

        # Check mouse hover on task round boxes via GetCursorPos
        pt = POINT()
        if user32 and user32.GetCursorPos(ctypes.byref(pt)):
            mx, my = pt.x, pt.y
            hovered = None
            for t in self.tasks:
                x0, y0, x1, y1 = t.rect
                if x0 <= mx <= x1 and y0 <= my <= y1:
                    hovered = t
                    break

            if hovered and self.console_popup:
                cx = (hovered.rect[0] + hovered.rect[2]) / 2.0
                cy = (hovered.rect[1] + hovered.rect[3]) / 2.0
                self.console_popup.show_task(hovered, cx, cy, self.win_x, self.win_y, self.win_h)
            elif self.console_popup:
                self.console_popup.hide()

        # Update visuals
        if self.state == "idle" and not self.tasks:
            if self.root.winfo_viewable():
                self.root.withdraw()
            if self.console_popup:
                self.console_popup.hide()
        else:
            if not self.root.winfo_viewable():
                self.root.deiconify()
                self.root.attributes("-topmost", True)

            # Render 32-bit ARGB image with true Gaussian glow
            img = self._render_frame(self.win_w, self.win_h, self.text, self.state, now)
            self._update_layered_window(img)

        if self.root:
            self.root.after(35, self._poll_queue)

    def _auto_hide(self) -> None:
        self.state = "idle"
        if not self.tasks and self.root:
            self.root.withdraw()
        if self.console_popup:
            self.console_popup.hide()

    # Drag and Drop handlers
    def _on_mouse_down(self, event) -> None:
        self._is_dragging = True
        self._drag_start_x = event.x_root - self.root.winfo_x()
        self._drag_start_y = event.y_root - self.root.winfo_y()

    def _on_mouse_drag(self, event) -> None:
        if self._is_dragging:
            self.win_x = event.x_root - self._drag_start_x
            self.win_y = event.y_root - self._drag_start_y
            self.root.geometry(f"+{self.win_x}+{self.win_y}")

    def _on_mouse_up(self, event) -> None:
        self._is_dragging = False

    def run(self, worker: Callable[[], None]) -> None:
        import tkinter as tk

        self.root = tk.Tk()
        self.root.title("Jev Voice Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        try:
            dpi = user32.GetDpiForSystem()
            self.scale = max(1.0, dpi / 96.0)
        except Exception:
            self.scale = 1.0

        self.win_w = int(540 * self.scale)
        self.win_h = int(110 * self.scale)

        sw = user32.GetSystemMetrics(0) if user32 else 1920
        margin_x = int(12 * self.scale)
        margin_y = int(12 * self.scale)

        if self.win_x is None:
            self.win_x = sw - self.win_w - margin_x
        if self.win_y is None:
            self.win_y = margin_y

        self.root.geometry(f"{self.win_w}x{self.win_h}+{self.win_x}+{self.win_y}")

        # Enable WS_EX_LAYERED for true per-pixel alpha transparency
        self.hwnd = self.root.winfo_id()
        style = GetWindowLong(self.hwnd, GWL_EXSTYLE)
        SetWindowLong(self.hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW)

        # Bind mouse events for drag and drop
        self.root.bind("<Button-1>", self._on_mouse_down)
        self.root.bind("<B1-Motion>", self._on_mouse_drag)
        self.root.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Initialize ConsolePopup
        self.console_popup = ConsolePopup(self.root, self.scale)

        # Load typography
        SCALE = 2
        try:
            self.font_pill = ImageFont.truetype(FONT_PATH, int(13 * self.scale * SCALE))
            self.font_round = ImageFont.truetype(FONT_PATH, int(12 * self.scale * SCALE))
        except Exception:
            self.font_pill = ImageFont.load_default()
            self.font_round = ImageFont.load_default()

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

    def set_audio_level(self, level: float) -> None:
        pass

    def add_task(self, label: str = "AGY", status: str = "running") -> str:
        return "noop"

    def update_task_log(self, task_id: str, line: str) -> None:
        pass

    def complete_task(self, task_id: str, status: str = "done") -> None:
        pass

    def remove_task(self, task_id: str) -> None:
        pass

    def clear_tasks(self) -> None:
        pass

    def run(self, worker: Callable[[], None]) -> None:
        worker()


Overlay = WindowsOverlay
