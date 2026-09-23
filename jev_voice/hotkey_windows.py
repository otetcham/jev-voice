"""Windows Global Hotkey (Alt + Space) push-to-talk listener using RegisterHotKey and GetAsyncKeyState."""
from __future__ import annotations

import ctypes
import threading
import time
from typing import Callable

user32 = ctypes.windll.user32

MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
HOTKEY_ID = 1
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


def remap_capslock() -> None:
    pass


def capslock_remapped() -> bool:
    return True


def request_permissions() -> dict[str, bool]:
    return {"accessibility": True, "input_monitoring": True}


def open_permission_panes() -> None:
    pass


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_ulonglong),
        ("lParam", ctypes.c_longlong),
        ("time", ctypes.c_ulong),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


class WindowsHotkeyListener:
    """Global Alt + Space listener for Windows.
    Supports hold-to-talk and tap-to-toggle.
    """

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None],
                 mod: int = MOD_ALT, vk: int = VK_SPACE) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.mod = mod
        self.vk = vk
        self.down = False
        self.thread: threading.Thread | None = None
        self.thread_id = 0
        self.ok = threading.Event()
        self.failed = threading.Event()
        self._running = False

    def _monitor_release(self) -> None:
        """Poll GetAsyncKeyState while key is held down to detect release."""
        # Wait until both Alt (VK_MENU: 0x12) or Space (0x20) are released
        while self.down and self._running:
            alt_down = (user32.GetAsyncKeyState(0x12) & 0x8000) != 0
            space_down = (user32.GetAsyncKeyState(self.vk) & 0x8000) != 0
            if not (alt_down and space_down):
                self.down = False
                try:
                    self.on_release()
                except Exception:
                    pass
                break
            time.sleep(0.02)

    def _run(self) -> None:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        self.thread_id = kernel32.GetCurrentThreadId()

        # Register Alt + Space as global hotkey
        res = user32.RegisterHotKey(None, HOTKEY_ID, self.mod | MOD_NOREPEAT, self.vk)
        if not res:
            # Fallback without MOD_NOREPEAT if unsupported
            res = user32.RegisterHotKey(None, HOTKEY_ID, self.mod, self.vk)

        if not res:
            self.failed.set()
            return

        self._running = True
        self.ok.set()

        msg = MSG()
        try:
            while self._running:
                # GetMessage blocks until a message arrives
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:  # WM_QUIT or error
                    break
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    if not self.down:
                        self.down = True
                        try:
                            self.on_press()
                        except Exception:
                            pass
                        # Start release watcher
                        threading.Thread(target=self._monitor_release, daemon=True).start()
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            self._running = False

    def start(self) -> bool:
        self.thread = threading.Thread(target=self._run, daemon=True, name="win-hotkey")
        self.thread.start()
        while not (self.ok.is_set() or self.failed.is_set()):
            self.ok.wait(0.05)
            self.failed.wait(0.01)
        return self.ok.is_set()

    def stop(self) -> None:
        self._running = False
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)


# Backward compatibility alias for main.py
CapsLockListener = WindowsHotkeyListener
