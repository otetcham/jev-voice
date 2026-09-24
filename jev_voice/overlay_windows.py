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
from dataclasses import dataclass
from typing import Callable

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
    label: str
    created_at: float


class WindowsOverlay:
    """True 32-bit ARGB layered floating overlay with genuine Gaussian aura, audio meter, and drag-and-drop."""

    def __init__(self) -> None:
        self.root = None
        self.hwnd = None
        self.q: queue.Queue[tuple[str, ...]] = queue.Queue()
        self._revert_timer = None
        self.scale = 1.0

        # State
        self.state = "idle"
        self.text = "音声入力中"
        self.tasks: list[AgyTask] = []
        self._task_counter = 1

        # Audio volume visualization
        self.target_audio_level = 0.0
        self.smoothed_audio_level = 0.0

        # Positioning & Dragging
        self.win_x = None
        self.win_y = None
        self.win_w = 520
        self.win_h = 110
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False

        self.font_pill = None
        self.font_round = None

    def set(self, state: str, text: str = "", revert_after: float | None = None) -> None:
        self.q.put(("set", state, text, revert_after))

    def set_audio_level(self, level: float) -> None:
        """Set current microphone volume level (RMS ~ 0.0 to 1.0)."""
        self.target_audio_level = max(0.0, min(1.0, float(level)))

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
        if len(display_text) > 28:
            display_text = display_text[:26] + "…"

        draw = ImageDraw.Draw(im)
        bbox = draw.textbbox((0, 0), display_text, font=self.font_pill)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Equalizer volume meter: 4 vertical bars
        bar_w = 3 * self.scale * SCALE
        bar_gap = 3 * self.scale * SCALE
        num_bars = 4
        meter_w = num_bars * bar_w + (num_bars - 1) * bar_gap
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
        # 0%, 100%: box-shadow: 0 0 10px rgba(99, 102, 241, 0.35)
        # 50%: box-shadow: 0 0 24px rgba(99, 102, 241, 0.70)
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
        else: # thinking / other
            aura_blur = 14 * self.scale * SCALE
            aura_color = (99, 102, 241, int(255 * 0.45))
            pill_border = (99, 102, 241, 153)

        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        draw_capsule(glow_draw, pill_x, pill_y, pill_w, pill_h, fill=aura_color)
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=aura_blur / 2.0))
        im.paste(glow_layer, (0, 0), glow_layer)

        draw = ImageDraw.Draw(im)

        # 2. Left Round Boxes (.round-box) with dot-pop animation
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
                # Main round box: #4f46e5 background, 2px solid #818cf8 border
                draw.ellipse(
                    [rx0, ry0, rx1, ry1],
                    fill=(79, 70, 229, 255),
                    outline=(129, 140, 248, 255),
                    width=int(2 * self.scale * SCALE)
                )
                t_bbox = draw.textbbox((0, 0), t.label, font=self.font_round)
                tw = t_bbox[2] - t_bbox[0]
                th = t_bbox[3] - t_bbox[1]
                draw.text(
                    (cx - tw / 2.0, cy - th / 2.0 - 2 * SCALE),
                    t.label,
                    fill=(255, 255, 255, 255),
                    font=self.font_round
                )

            curr_x += round_size + gap_rounds

        # 3. Pill Body (Solid #0f172a, border rgba(99, 102, 241, 0.6))
        draw_capsule(
            draw,
            pill_x, pill_y, pill_w, pill_h,
            fill=(15, 23, 42, 255),
            outline=pill_border,
            outline_w=int(1 * self.scale * SCALE)
        )

        # 4. Animated Audio Equalizer Volume Bars
        bar_x = pill_x + pill_pad_x
        max_bar_h = 22 * self.scale * SCALE
        min_bar_h = 5 * self.scale * SCALE

        # 4 dynamic bars reacting to microphone level + simulated frequency flutter
        mod_phase = (now * 9.0)
        flutter = [
            0.55 + 0.15 * math.sin(mod_phase),
            0.95 + 0.15 * math.sin(mod_phase + 1.2),
            0.80 + 0.20 * math.sin(mod_phase + 2.5),
            0.50 + 0.15 * math.sin(mod_phase + 3.8),
        ]

        active_level = self.smoothed_audio_level if state == "listening" else 0.05
        for i, factor in enumerate(flutter):
            bh = min_bar_h + (max_bar_h - min_bar_h) * min(1.0, max(0.0, active_level * factor * 1.5))
            bx = bar_x + i * (bar_w + bar_gap)
            by = pill_y + (pill_h - bh) / 2.0
            draw.rounded_rectangle(
                [bx, by, bx + bar_w, by + bh],
                radius=bar_w / 2.0,
                fill=(129, 140, 248, 255) # bright indigo/cyan glow
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
        pa = arr[:, :, 3] # uint8
        bgra = np.dstack([pb, pg, pr, pa]).tobytes()

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h # top-down
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
            if self.root.winfo_viewable():
                self.root.withdraw()
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

        self.win_w = int(520 * self.scale)
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

    def add_task(self, label: str = "AGY") -> str:
        return "noop"

    def remove_task(self, task_id: str) -> None:
        pass

    def clear_tasks(self) -> None:
        pass

    def run(self, worker: Callable[[], None]) -> None:
        worker()


Overlay = WindowsOverlay
