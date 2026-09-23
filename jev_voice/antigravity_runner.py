"""Fallback runner for tasks that Jev cannot handle directly.
Invokes Antigravity CLI (`agy`) with high autonomy (`--dangerously-skip-permissions`).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from typing import Callable

AGY_BIN = os.environ.get("AGY_BIN", "agy")
AGY_MODEL = os.environ.get("AGY_MODEL", "")  # default CLI model if unset


def is_agy_available() -> bool:
    """Check if agy is available in PATH or at specified location."""
    return shutil.which(AGY_BIN) is not None or os.path.exists(AGY_BIN)


def run_antigravity(
    prompt: str,
    *,
    model: str | None = None,
    on_output: Callable[[str], None] | None = None,
    timeout: float = 180.0,
) -> str:
    """Run a prompt through Antigravity CLI and return the response."""
    if not is_agy_available():
        msg = "Antigravity CLI (agy) がシステムに見つかりません。"
        print(f"  ! {msg}")
        return msg

    cmd = [
        AGY_BIN,
        "-p",
        prompt,
        "--dangerously-skip-permissions",
    ]
    selected_model = model or AGY_MODEL
    if selected_model:
        cmd.extend(["--model", selected_model])

    print(f"  ⚡ [Antigravity Fallback] 実行開始: {prompt}")

    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
        )

        stdout_lines: list[str] = []

        def reader():
            try:
                assert process.stdout is not None
                for line in iter(process.stdout.readline, ""):
                    if not line:
                        break
                    stdout_lines.append(line)
                    clean_line = line.strip()
                    if clean_line and on_output:
                        on_output(clean_line)
            except (ValueError, OSError):
                pass

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        try:
            process.wait(timeout=timeout)
            t.join(timeout=2.0)
            stderr = process.stderr.read() if process.stderr else ""
        except subprocess.TimeoutExpired:
            process.kill()
            return "Antigravity の実行がタイムアウトしました。"

        res = "".join(stdout_lines).strip()
        if not res and process.returncode != 0:
            err = stderr.strip() if stderr else f"Exit code {process.returncode}"
            print(f"  ! agy error: {err}")
            return f"Antigravity の実行中にエラーが発生しました: {err[:120]}"

        return res or "完了しました。"
    except Exception as e:
        print(f"  ! agy execution failed: {e}")
        return f"Antigravity 実行失敗: {e}"
