"""Windows Native Top-Right Floating Overlay Pill using Tkinter.
Zero dependencies, non-activating, thread-safe.
"""
from __future__ import annotations

import queue
import sys
import threading
import time
from typing import Callable

COLORS = {
    "idle": ("#8E8E93", "待機中"),
    "listening": ("#FF3B30", "🎙️ 録音中…"),
    "thinking": ("#007AFF", "⏳ 音声読み込み中…"),
    "done": ("#34C759", "✔ 完了"),
    "error": ("#FF9500", "⚠ エラー"),
}

BG_COLOR = "#1C1C1E"
FG_COLOR = "#FFFFFF"
BORDER_COLOR = "#38383A"


class WindowsOverlay:
    """Top-right floating status pill on Windows screen."""

    def __init__(self) -> None:
        self.root = None
        self.label = None
        self.dot = None
        self.q: queue.Queue[tuple[str, str, float | None]] = queue.Queue()
        self._current_state = "idle"
        self._revert_job = None
        self._ready = threading.Event()

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
            self.root.after(50, self._poll_queue)

    def _apply(self, state: str, text: str, revert_after: float | None = None) -> None:
        if not self.root:
            return

        if state == "idle" and not text:
            self.root.withdraw()
            return

        color, def_title = COLORS.get(state, ("#007AFF", ""))
        display_text = text or def_title

        # Truncate if overly long
        if len(display_text) > 36:
            display_text = display_text[:33] + "..."

        self.dot.config(fg=color)
        self.label.config(text=display_text)

        # Reposition and resize to fit text
        self.root.update_idletasks()
        w = max(180, self.label.winfo_reqwidth() + 50)
        h = 38
        sw = self.root.winfo_screenwidth()
        x = sw - w - 24
        y = 24
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.deiconify()
        self.root.attributes("-topmost", True)

        # Handle revert
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

        self.root = tk.Tk()
        self.root.title("Jev Voice Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=BORDER_COLOR)

        # Frame for inner rounded-like padding and border
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=12, pady=6)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        # Color dot indicator
        self.dot = tk.Label(frame, text="●", font=("Segoe UI", 12), fg="#007AFF", bg=BG_COLOR)
        self.dot.pack(side="left", padx=(0, 6))

        # Text label
        self.label = tk.Label(frame, text="", font=("Meiryo UI", 10, "bold"), fg=FG_COLOR, bg=BG_COLOR)
        self.label.pack(side="left", fill="both", expand=True)

        # Initial hidden state
        self.root.withdraw()

        # Start queue polling
        self.root.after(50, self._poll_queue)

        # Run background worker thread
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

