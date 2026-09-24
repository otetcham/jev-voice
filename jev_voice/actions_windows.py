"""Windows execution layer for jev-voice.
Implements the same interfaces as actions.py (macOS) using Win32 API, PowerShell, and ctypes.
No external heavy dependencies required: uses built-in Python stdlib + ctypes.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import webbrowser
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

# ---------------------------------------------------------------- Win32 Ctypes setup
user32 = ctypes.windll.user32 if sys.platform == "win32" else None

# Common Virtual Key Codes
VK_CODES = {
    "enter": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete_forward": 0x2E,
    "arrow_up": 0x26,
    "arrow_down": 0x28,
    "arrow_left": 0x25,
    "arrow_right": 0x27,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "win": 0x5B,
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_play_pause": 0xB3,
}

# ---------------------------------------------------------------- apps

import json
import shutil
import threading
from typing import Any

ALWAYS_APPS = [
    "Chrome", "Edge", "Explorer", "Notepad", "Task Manager", "Calculator",
    "Terminal", "PowerShell", "Settings", "Code", "Discord", "Spotify", "Slack",
    "LINE", "Steam", "Zoom", "Snipping Tool"
]

COMMON_PROTOCOLS: dict[str, str] = {
    "line": "line:",
    "spotify": "spotify:",
    "discord": "discord:",
    "slack": "slack:",
    "notion": "notion:",
    "steam": "steam:",
    "calculator": "calc:",
    "settings": "ms-settings:",
    "camera": "microsoft.windows.camera:",
    "clock": "ms-clock:",
}

COMMON_ALIASES: dict[str, str] = {
    # Japanese aliases
    "ライン": "line",
    "クローム": "chrome",
    "グーグルクローム": "chrome",
    "エッジ": "edge",
    "マイクロソフトエッジ": "edge",
    "ディスコード": "discord",
    "スラック": "slack",
    "スポティファイ": "spotify",
    "ノーション": "notion",
    "スチーム": "steam",
    "電卓": "calculator",
    "計算機": "calculator",
    "メモ帳": "notepad",
    "設定": "settings",
    "エクスプローラー": "explorer",
    "ファイルエクスプローラー": "explorer",
    "ターミナル": "terminal",
    "コマンドプロンプト": "cmd",
    "パワーシェル": "powershell",
    "タスクマネージャー": "task manager",
    "タスクマネージャ": "task manager",
    # English / Abbreviations
    "calc": "calculator",
    "wt": "terminal",
    "code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "google chrome": "chrome",
    "microsoft edge": "edge",
    "taskmgr": "task manager",
}

COMMON_EXES: dict[str, str] = {
    "chrome": "chrome",
    "edge": "msedge",
    "calculator": "calc",
    "terminal": "wt",
    "powershell": "powershell",
    "cmd": "cmd",
    "notepad": "notepad",
    "explorer": "explorer",
    "settings": "ms-settings:",
    "task manager": "taskmgr",
    "code": "code",
}


class AppRegistry:
    """Registry of installed Windows applications combining Start Menu shortcuts (.lnk),
    UWP/Store apps (Get-StartApps AppID), protocol handlers, and standard executables."""

    _instance: AppRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._apps: dict[str, dict[str, Any]] = {}
        self._cache_dir = Path.home() / ".cache" / "jev-voice"
        self._cache_file = self._cache_dir / "windows_apps.json"
        self._init_registry()

    @classmethod
    def get(cls) -> AppRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = AppRegistry()
        return cls._instance

    def _init_registry(self) -> None:
        # 1. Fast LNK scan (~10ms)
        self._scan_lnks()

        # 2. Disk cache load (~1ms)
        cache_loaded = self._load_cache()

        # 3. If cache missing or stale (>3 days), refresh in background
        if not cache_loaded:
            threading.Thread(target=self._refresh_start_apps, daemon=True).start()

    def _scan_lnks(self) -> None:
        start_dirs = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]
        exclude_keywords = (
            "uninstall", "アンインストール", "help", "ヘルプ", "readme",
            "documentation", "マニュアル", "manual", "website", "web site", "url"
        )
        for d in start_dirs:
            if not d.exists():
                continue
            try:
                for p in d.rglob("*.lnk"):
                    stem = p.stem.strip()
                    lower_stem = stem.lower()
                    if any(k in lower_stem for k in exclude_keywords):
                        continue
                    entry = self._apps.setdefault(lower_stem, {"display_name": stem})
                    if "lnk" not in entry or not entry["lnk"]:
                        entry["lnk"] = str(p)
            except Exception:
                pass

    def _load_cache(self) -> bool:
        if not self._cache_file.exists():
            return False
        try:
            mtime = self._cache_file.stat().st_mtime
            if time.time() - mtime > 86400 * 3:
                return False
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    name = item.get("Name", "").strip()
                    appid = item.get("AppID", "").strip()
                    if name and appid:
                        lower_name = name.lower()
                        entry = self._apps.setdefault(lower_name, {"display_name": name})
                        entry["appid"] = appid
                return True
        except Exception:
            pass
        return False

    def _refresh_start_apps(self) -> None:
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                if isinstance(data, list):
                    for item in data:
                        name = item.get("Name", "").strip()
                        appid = item.get("AppID", "").strip()
                        if name and appid:
                            lower_name = name.lower()
                            entry = self._apps.setdefault(lower_name, {"display_name": name})
                            entry["appid"] = appid
                    # Save to cache
                    try:
                        self._cache_dir.mkdir(parents=True, exist_ok=True)
                        self._cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                    except Exception:
                        pass
        except Exception:
            pass

    def list_display_names(self) -> list[str]:
        names: set[str] = set(ALWAYS_APPS)
        for entry in self._apps.values():
            disp = entry.get("display_name", "")
            if disp:
                names.add(disp)
        return sorted(names, key=str.lower)

    def resolve_app(self, query: str) -> dict[str, Any] | None:
        q = query.strip().lower()
        resolved_key = COMMON_ALIASES.get(q, q)

        # 1. Exact match in registry
        if resolved_key in self._apps:
            return self._apps[resolved_key]
        if q in self._apps:
            return self._apps[q]

        # 2. Word / prefix / substring match
        candidates = []
        for k, v in self._apps.items():
            if resolved_key == k:
                return v
            if resolved_key in k.split():
                candidates.append((1, v))
            elif k.startswith(resolved_key):
                candidates.append((2, v))
            elif resolved_key in k:
                candidates.append((3, v))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]

        # 3. Fallback object if protocol or known exe exists
        proto = COMMON_PROTOCOLS.get(resolved_key) or COMMON_PROTOCOLS.get(q)
        exe = COMMON_EXES.get(resolved_key) or COMMON_EXES.get(q)
        if proto or exe:
            return {"display_name": query, "protocol": proto, "exe": exe}

        return None


def installed_apps() -> list[str]:
    """Discover installed applications on Windows via Start Menu shortcuts and StartApps registry."""
    return AppRegistry.get().list_display_names()


def launch_app(name: str) -> bool:
    """Launch application safely on Windows without popping up 'file not found' dialogs."""
    reg = AppRegistry.get()
    app = reg.resolve_app(name)

    if app:
        # 1. Try .lnk shortcut
        lnk = app.get("lnk")
        if lnk and os.path.exists(lnk):
            try:
                os.startfile(lnk)
                return True
            except Exception:
                pass

        # 2. Try AppID (shell:AppsFolder\<AppID>)
        appid = app.get("appid")
        if appid:
            try:
                os.startfile(f"shell:AppsFolder\\{appid}")
                return True
            except Exception:
                pass

        # 3. Try protocol handler (e.g. line:, spotify:)
        proto = app.get("protocol") or COMMON_PROTOCOLS.get(name.lower())
        if proto:
            try:
                os.startfile(proto)
                return True
            except Exception:
                pass

        # 4. Try exe path or common command
        exe = app.get("exe") or COMMON_EXES.get(name.lower())
        if exe:
            try:
                os.startfile(exe)
                return True
            except Exception:
                try:
                    subprocess.Popen([exe], shell=False)
                    return True
                except Exception:
                    pass

    # Check if name is in PATH
    which_path = shutil.which(name)
    if which_path:
        try:
            os.startfile(which_path)
            return True
        except Exception:
            try:
                subprocess.Popen([which_path], shell=False)
                return True
            except Exception:
                pass

    # Check protocol aliases
    norm = COMMON_ALIASES.get(name.lower(), name.lower())
    if norm in COMMON_PROTOCOLS:
        try:
            os.startfile(COMMON_PROTOCOLS[norm])
            return True
        except Exception:
            pass

    # Suppress cmd /c start "" to prevent Windows "File not found" dialogs
    print(f"⚠️ アプリが見つかりませんでした: '{name}'")
    return False


def frontmost_pid() -> int:
    """Return process ID of current foreground window."""
    if not user32:
        return 0
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def frontmost_app() -> str:
    """Return app name or title of current foreground window."""
    if not user32:
        return ""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if " - " in title:
            return title.split(" - ")[-1].strip()
        return title
    return ""


def open_app(name: str) -> None:
    launch_app(name)


def focus_app(name: str, timeout: float = 2.0) -> bool:
    return launch_app(name)


def open_url(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)


# ---------------------------------------------------------------- sites / search

SITES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "google_calendar": "https://calendar.google.com",
    "google_drive": "https://drive.google.com",
    "google_docs": "https://docs.google.com",
    "google_maps": "https://maps.google.com",
    "github": "https://github.com",
    "twitter_x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "amazon": "https://www.amazon.co.jp",
    "netflix": "https://www.netflix.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "notion": "https://www.notion.so",
    "spotify_web": "https://open.spotify.com",
    "wikipedia": "https://ja.wikipedia.org",
    "yahoo": "https://search.yahoo.co.jp",
    "qiita": "https://qiita.com",
    "zenn": "https://zenn.dev",
    "trip_com": "https://jp.trip.com/flights/",
    "google_flights": "https://www.google.com/travel/flights",
    "expedia": "https://www.expedia.co.jp",
}

SEARCH_ENGINES: dict[str, str] = {
    "google": "https://www.google.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "amazon": "https://www.amazon.co.jp/s?k={q}",
    "wikipedia": "https://ja.wikipedia.org/wiki/{q}",
    "github": "https://github.com/search?q={q}",
    "google_maps": "https://www.google.com/maps/search/{q}",
    "twitter_x": "https://x.com/search?q={q}",
    "yahoo": "https://search.yahoo.co.jp/search?p={q}",
    "perplexity": "https://www.perplexity.ai/search?q={q}",
}


def web_search(engine: str, query: str) -> None:
    tpl = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["google"])
    open_url(tpl.format(q=quote_plus(query)))


# ---------------------------------------------------------------- keyboard & input

def send_key_event(vk_code: int, down: bool = True) -> None:
    """Send low-level keyboard event via user32.keybd_event."""
    if not user32:
        return
    flags = 0 if down else 0x0002
    user32.keybd_event(vk_code, 0, flags, 0)


def type_text(text: str) -> None:
    """Type arbitrary text (including Japanese and Unicode) via SendInput or PowerShell clip."""
    # Using PowerShell SendKeys or clipboard paste for reliable Unicode / Japanese support
    try:
        # Copy to clipboard and simulate Ctrl+V
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        press("paste")
    except Exception:
        # Fallback to keybd_event per char
        for ch in text:
            vk = user32.VkKeyScanW(ord(ch)) & 0xFF
            if vk != 0xFF:
                send_key_event(vk, True)
                send_key_event(vk, False)
            time.sleep(0.01)


SHORTCUTS: dict[str, tuple[str, list[str]]] = {
    "enter": ("enter", []),
    "escape": ("escape", []),
    "tab": ("tab", []),
    "space": ("space", []),
    "backspace": ("backspace", []),
    "delete_forward": ("delete_forward", []),
    "arrow_up": ("arrow_up", []),
    "arrow_down": ("arrow_down", []),
    "arrow_left": ("arrow_left", []),
    "arrow_right": ("arrow_right", []),
    "copy": ("c", ["control"]),
    "paste": ("v", ["control"]),
    "cut": ("x", ["control"]),
    "undo": ("z", ["control"]),
    "redo": ("y", ["control"]),
    "select_all": ("a", ["control"]),
    "save": ("s", ["control"]),
    "find": ("f", ["control"]),
    "new": ("n", ["control"]),
    "new_tab": ("t", ["control"]),
    "close_tab_or_window": ("w", ["control"]),
    "reopen_closed_tab": ("t", ["control", "shift"]),
    "quit_app": ("F4", ["alt"]),
    "minimize_window": ("arrow_down", ["win"]),
    "fullscreen": ("F11", []),
    "next_tab": ("tab", ["control"]),
    "previous_tab": ("tab", ["control", "shift"]),
    "browser_back": ("arrow_left", ["alt"]),
    "browser_forward": ("arrow_right", ["alt"]),
    "reload": ("F5", []),
    "address_bar": ("l", ["alt"]),
    "switch_app": ("tab", ["alt"]),
    "lock_screen": ("l", ["win"]),
    "show_desktop": ("d", ["win"]),
}


def press(shortcut: str, times: int = 1) -> None:
    if shortcut not in SHORTCUTS:
        return
    key_name, mods = SHORTCUTS[shortcut]

    def to_vk(k: str) -> int:
        if k in VK_CODES:
            return VK_CODES[k]
        if k.startswith("F") and k[1:].isdigit():
            return 0x6F + int(k[1:])  # F1..F12
        if len(k) == 1:
            return ord(k.upper())
        return 0

    mod_vks = [to_vk(m) for m in mods]
    key_vk = to_vk(key_name)

    for _ in range(max(1, times)):
        for m in mod_vks:
            send_key_event(m, True)
        send_key_event(key_vk, True)
        time.sleep(0.02)
        send_key_event(key_vk, False)
        for m in reversed(mod_vks):
            send_key_event(m, False)
        time.sleep(0.03)


# ---------------------------------------------------------------- scroll & volume

def scroll(direction: str, amount: str = "page") -> None:
    """Scroll wheel simulation on Windows."""
    if not user32:
        return
    clicks = {"little": 2, "page": 6, "a_lot": 15}.get(amount, 6)
    delta = 120 * clicks if direction in ("up", "top") else -120 * clicks
    user32.mouse_event(0x0800, 0, 0, delta, 0)  # MOUSEEVENTF_WHEEL


def volume(op: str) -> str:
    """Control system volume via Windows media keys."""
    if op in ("up", "louder"):
        for _ in range(5):
            send_key_event(VK_CODES["volume_up"], True)
            send_key_event(VK_CODES["volume_up"], False)
        return "音量を上げました。"
    if op in ("down", "quieter"):
        for _ in range(5):
            send_key_event(VK_CODES["volume_down"], True)
            send_key_event(VK_CODES["volume_down"], False)
        return "音量を下げました。"
    if op in ("mute", "unmute"):
        send_key_event(VK_CODES["volume_mute"], True)
        send_key_event(VK_CODES["volume_mute"], False)
        return "消音を切り替えました。"
    return ""


def media(op: str) -> None:
    """Control media playback on Windows."""
    key_map = {
        "play_pause": VK_CODES["media_play_pause"],
        "next": VK_CODES["media_next"],
        "previous": VK_CODES["media_prev"],
    }
    vk = key_map.get(op, VK_CODES["media_play_pause"])
    send_key_event(vk, True)
    send_key_event(vk, False)


# ---------------------------------------------------------------- misc

FOLDERS = {
    "home": Path.home(),
    "desktop": Path.home() / "Desktop",
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "videos": Path.home() / "Videos",
}


def open_folder(name: str) -> None:
    target = FOLDERS.get(name.lower(), Path.home())
    os.startfile(str(target))


def screenshot() -> Path:
    out = Path.home() / "Desktop" / f"Screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
    # PowerShell screengrab
    cmd = (
        f"Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
        f"$b = New-Object Drawing.Bitmap([Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, [Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); "
        f"$g = [Drawing.Graphics]::FromImage($b); "
        f"$g.CopyFromScreen(0, 0, 0, 0, $b.Size); "
        f"$b.Save('{str(out)}'); $g.Dispose(); $b.Dispose()"
    )
    subprocess.run(["powershell", "-Command", cmd], capture_output=True)
    return out


def system(op: str) -> str:
    if op == "lock":
        press("lock_screen")
        return "画面をロックしました。"
    if op == "show_desktop":
        press("show_desktop")
        return "デスクトップを表示しました。"
    if op == "sleep_display":
        # Turn off display via SendMessage
        if user32:
            user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        return "ディスプレイをスリープにしました。"
    return ""


def accessibility_ok() -> bool:
    return True
