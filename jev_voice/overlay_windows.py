"""Windows Native High-DPI Floating Voice Pill & Antigravity Round Box Overlay.
Rendered directly via Edge WebView2 (Chromium) with full Per-Pixel Alpha Translucency.
100% faithful to user CSS/HTML specifications:
- Exact CSS keyframes: audio-pill-pulse (box-shadow pulse 0 0 10px to 24px)
- Exact CSS keyframes: dot-pop (cubic-bezier(0.34, 1.56, 0.64, 1) scale 0 -> 1.18 -> 1)
- Exact styling:
    - .round-box (44x44px, #4f46e5, 2px solid #818cf8, white bold 12px)
    - .pill (height 44px, padding 0 20px, #0f172a, 1px solid rgba(99, 102, 241, 0.6))
    - #leftRoundBoxes (gap 8px)
    - container (gap 10px)
"""
from __future__ import annotations

import ctypes
import json
import queue
import sys
import threading
import time
from typing import Callable

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
body {
  background: transparent;
  width: 100vw;
  height: 100vh;
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  padding: 16px 20px 0 0;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Segoe UI Variable Text", sans-serif;
}
@keyframes audio-pill-pulse {
  0%, 100% { box-shadow: 0 0 10px rgba(99, 102, 241, 0.35); }
  50% { box-shadow: 0 0 24px rgba(99, 102, 241, 0.7); }
}
@keyframes dot-pop {
  0% { transform: scale(0); opacity: 0; }
  70% { transform: scale(1.18); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}
@keyframes dot-fadeout {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(0.6); opacity: 0; }
}
.round-box {
  width: 44px; height: 44px; border-radius: 50%;
  background: #4f46e5; border: 2px solid #818cf8; color: #ffffff;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600;
  animation: dot-pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
  flex-shrink: 0;
}
.round-box.removing {
  animation: dot-fadeout 0.2s ease forwards;
}
.pill {
  height: 44px; padding: 0 20px; border-radius: 9999px;
  background: #0f172a; border: 1px solid rgba(99, 102, 241, 0.6);
  display: flex; align-items: center; gap: 10px;
  animation: audio-pill-pulse 2.8s ease-in-out infinite;
  white-space: nowrap;
  transition: opacity 0.25s ease, transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
  flex-shrink: 0;
}
.pill.state-done {
  border-color: rgba(52, 211, 153, 0.8);
  box-shadow: 0 0 16px rgba(52, 211, 153, 0.4);
  animation: none;
}
.pill.state-error {
  border-color: rgba(248, 113, 113, 0.8);
  box-shadow: 0 0 16px rgba(248, 113, 113, 0.4);
  animation: none;
}
.pill.state-thinking {
  animation: none;
  box-shadow: 0 0 14px rgba(99, 102, 241, 0.45);
}
.pill-text {
  color: #e2e8f0; font-size: 13px; font-weight: 500;
}
#overlayWrapper {
  display: flex; align-items: center; gap: 10px;
  transition: opacity 0.25s ease, transform 0.25s ease;
}
#overlayWrapper.hidden {
  opacity: 0;
  pointer-events: none;
  transform: translateY(-8px) scale(0.95);
}
</style>
</head>
<body>
<div id="overlayWrapper" class="hidden">
  <!-- タスク追加時に丸いボックスが並ぶコンテナ -->
  <div id="leftRoundBoxes" style="display: flex; align-items: center; gap: 8px;"></div>

  <!-- 横長の角丸ボックス（単色ソリッド） -->
  <div id="voicePill" class="pill">
    <span class="pill-text" id="pillText">音声入力中</span>
  </div>
</div>

<script>
const wrapper = document.getElementById('overlayWrapper');
const pill = document.getElementById('voicePill');
const pillText = document.getElementById('pillText');
const leftBoxes = document.getElementById('leftRoundBoxes');

window.updateOverlay = function(state, text) {
  if (state === 'idle' && leftBoxes.children.length === 0) {
    wrapper.classList.add('hidden');
    return;
  }
  wrapper.classList.remove('hidden');

  if (text) {
    pillText.textContent = text;
  } else if (state === 'listening') {
    pillText.textContent = '音声入力中';
  } else if (state === 'thinking') {
    pillText.textContent = '解析中…';
  } else if (state === 'done') {
    pillText.textContent = '完了';
  }

  pill.className = 'pill';
  if (state === 'done') {
    pill.classList.add('state-done');
  } else if (state === 'error') {
    pill.classList.add('state-error');
  } else if (state === 'thinking') {
    pill.classList.add('state-thinking');
  }
};

window.addRoundBox = function(id, label) {
  wrapper.classList.remove('hidden');
  const existing = document.getElementById(id);
  if (existing) return;

  const box = document.createElement('div');
  box.id = id;
  box.className = 'round-box';
  box.textContent = label || 'AGY';
  leftBoxes.appendChild(box);
};

window.removeRoundBox = function(id) {
  const box = document.getElementById(id);
  if (box) {
    box.classList.add('removing');
    setTimeout(() => {
      box.remove();
      if (wrapper.classList.contains('state-idle') && leftBoxes.children.length === 0) {
        wrapper.classList.add('hidden');
      }
    }, 200);
  }
};

window.clearRoundBoxes = function() {
  leftBoxes.innerHTML = '';
};
</script>
</body>
</html>
"""


class WindowsOverlay:
    """Full-Fidelity WebView2 Floating Voice Pill with Antigravity Task Round Boxes."""

    def __init__(self) -> None:
        self.window = None
        self.q: queue.Queue[tuple[str, ...]] = queue.Queue()
        self._revert_timer = None
        self._task_counter = 1
        self._ready = threading.Event()

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

    def _eval_js(self, js: str) -> None:
        if self.window and self._ready.is_set():
            try:
                self.window.evaluate_js(js)
            except Exception:
                pass

    def _pump_queue(self) -> None:
        while True:
            time.sleep(0.025)
            if not self._ready.is_set() or not self.window:
                continue

            try:
                while not self.q.empty():
                    cmd = self.q.get_nowait()
                    action = cmd[0]

                    if action == "set":
                        _, state, text, revert_after = cmd
                        s_esc = json.dumps(state)
                        t_esc = json.dumps(text)
                        self._eval_js(f"window.updateOverlay({s_esc}, {t_esc});")

                        if self._revert_timer:
                            self._revert_timer.cancel()
                            self._revert_timer = None

                        if revert_after:
                            def _auto_revert():
                                self.set("idle", "")
                            self._revert_timer = threading.Timer(revert_after, _auto_revert)
                            self._revert_timer.start()

                    elif action == "add_task":
                        _, tid, label = cmd
                        i_esc = json.dumps(tid)
                        l_esc = json.dumps(label)
                        self._eval_js(f"window.addRoundBox({i_esc}, {l_esc});")

                    elif action == "remove_task":
                        _, tid = cmd
                        i_esc = json.dumps(tid)
                        self._eval_js(f"window.removeRoundBox({i_esc});")

                    elif action == "clear_tasks":
                        self._eval_js("window.clearRoundBoxes();")

            except Exception:
                pass

    def run(self, worker: Callable[[], None]) -> None:
        import webview

        sw = user32.GetSystemMetrics(0) if user32 else 1920
        win_w = 650
        win_h = 100
        win_x = sw - win_w - 10
        win_y = 6

        self.window = webview.create_window(
            'Jev Voice Overlay',
            html=HTML_TEMPLATE,
            frameless=True,
            transparent=True,
            on_top=True,
            width=win_w,
            height=win_h,
            x=win_x,
            y=win_y,
        )

        def _on_loaded():
            self._ready.set()
            threading.Thread(target=self._pump_queue, daemon=True, name="overlay-pump").start()
            # Start worker thread
            threading.Thread(target=_worker_wrapper, daemon=True, name="jev-worker").start()

        def _worker_wrapper():
            try:
                worker()
            finally:
                if self.window:
                    time.sleep(0.2)
                    self.window.destroy()

        try:
            webview.start(_on_loaded, gui='edgechromium')
        except KeyboardInterrupt:
            if self.window:
                self.window.destroy()


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
