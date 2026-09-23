"""Windows Native High-DPI Top-Right Floating Overlay Pill.
Crisp typography, native DWM rounded corners, per-monitor DPI aware.
"""
from __future__ import annotations

import ctypes
import queue
import threading
from typing import Callable

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

# Enable Per-Monitor V2 DPI awareness before Tkinter creates windows
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

COLORS = {
    "idle": ("#8E8E93", "待機中"),
    "listening": ("#FF3B30", "🎙️ 音声を聞き取り中…"),
    "thinking": ("#0A84FF", "⏳ 音声を読み込み中…"),
    "done": ("#30D158", "✔ 完了"),
    "error": ("#FF9F0A", "⚠ エラー"),
}

BG_COLOR = "#18181C"
FG_COLOR = "#F5F5F7"
BORDER_COLOR = "#323238"


def _apply_dwm_styling(hwnd: int) -> None:
    """Apply native Windows 11 rounded corners and dark mode."""
    try:
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
        corner_pref = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
    except Exception:
        pass
    try:
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(dark), ctypes.sizeof(dark))
    except Exception:
        pass


class WindowsOverlay:
    """Crisp, high-DPI floating status pill in the top-right corner."""

    def __init__(self) -> None:
        self.root = None
        self.canvas_dot = None
        self.label = None
        self.q: queue.Queue[tuple[str, str, float | None]] = queue.Queue()
        self._revert_job = None
        self.scale = 1.0

    def set(self, state: str, text: str, revert_after: float | None = None) -> None:
        self.q.put((state, text, revert_after))

    def _poll_queue(self) -> None:
        try:
            while not self.q.empty():
                state, text, revert_after = self.q.get_nowait()
                self._apply(state, text, revert_after)
        except Exception:
            pass
        if self.root:
            self.root.after(40, self._poll_queue)

    def _apply(self, state: str, text: str, revert_after: float | None = None) -> None:
        if not self.root:
            return

        if state == "idle" and not text:
            self.root.withdraw()
            return

        color, def_title = COLORS.get(state, ("#0A84FF", ""))
        display_text = text or def_title

        if len(display_text) > 36:
            display_text = display_text[:33] + "..."

        # Update smooth dot
        dot_r = int(5 * self.scale)
        self.canvas_dot.delete("all")
        cx = int(9 * self.scale)
        cy = int(12 * self.scale)
        self.canvas_dot.create_oval(cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r, fill=color, outline="")

        self.label.config(text=display_text)

        # Reposition and size
        self.root.update_idletasks()
        req_w = self.label.winfo_reqwidth()
        dot_w = int(24 * self.scale)
        pad_x = int(32 * self.scale)
        w = max(int(190 * self.scale), req_w + dot_w + pad_x)
        h = int(42 * self.scale)

        sw = user32.GetSystemMetrics(0)
        margin = int(24 * self.scale)
        x = sw - w - margin
        y = margin

        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.deiconify()
        self.root.attributes("-topmost", True)

        if self._revert_job:
            try:
                self.root.after_cancel(self._revert_job)
            except Exception:
                pass
            self._revert_job = None

        if revert_after:
            self._revert_job = self.root.after(int(revert_after * 1000), self._hide)

    def _hide(self) -> None:
        if self.root:
            self.root.withdraw()

    def run(self, worker: Callable[[], None]) -> None:
        import tkinter as tk
        import tkinter.font as tkfont

        self.root = tk.Tk()
        self.root.title("Jev Voice Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=BORDER_COLOR)

        try:
            dpi = user32.GetDpiForSystem()
            self.scale = max(1.0, dpi / 96.0)
        except Exception:
            self.scale = 1.0

        font_size = max(9, int(10 * self.scale))
        # Choose best crisp font on Windows
        font_family = "Segoe UI Variable Text"
        try:
            available = tkfont.families(self.root)
            if font_family not in available:
                font_family = "Segoe UI" if "Segoe UI" in available else "Yu Gothic UI"
        except Exception:
            font_family = "Segoe UI"

        # Frame container
        pad_in = max(1, int(1 * self.scale))
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=int(14 * self.scale), pady=int(6 * self.scale))
        frame.pack(fill="both", expand=True, padx=pad_in, pady=pad_in)

        # Dot canvas for crisp circle
        dot_box_w = int(18 * self.scale)
        dot_box_h = int(24 * self.scale)
        self.canvas_dot = tk.Canvas(frame, width=dot_box_w, height=dot_box_h, bg=BG_COLOR, highlightthickness=0)
        self.canvas_dot.pack(side="left", padx=(0, int(4 * self.scale)))

        # Crisp label
        self.label = tk.Label(frame, text="", font=(font_family, font_size, "bold"),
                              fg=FG_COLOR, bg=BG_COLOR)
        self.label.pack(side="left", fill="both", expand=True)

        # Initial hidden state
        self.root.withdraw()

        # Apply native Windows 11 DWM rounded corners
        self.root.update_idletasks()
        try:
            hwnd = int(self.root.wm_frame(), 16) if isinstance(self.root.wm_frame(), str) else self.root.winfo_id()
            _apply_dwm_styling(hwnd)
        except Exception:
            pass

        self.root.after(40, self._poll_queue)

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
    def set(self, state: str, text: str, revert_after: float | None = None) -> None:
        pass

    def run(self, worker: Callable[[], None]) -> None:
        worker()


Overlay = WindowsOverlay
