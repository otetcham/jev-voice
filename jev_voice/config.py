from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# API resolution: prioritize TypeSafe native key, fallback to OpenRouter decisions API
if TYPESAFE_API_KEY:
    API_KEY = TYPESAFE_API_KEY
    API_URL = os.environ.get("TYPESAFE_URL", "https://api.typesafe.ai/v1/systemone")
    JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")
elif OPENROUTER_API_KEY:
    API_KEY = OPENROUTER_API_KEY
    API_URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/alpha/decisions")
    JEV_MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
else:
    API_KEY = ""
    API_URL = os.environ.get("TYPESAFE_URL", "https://api.typesafe.ai/v1/systemone")
    JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")

TYPESAFE_URL = API_URL

WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "ja")
_default_whisper = (
    ROOT / "models" / "ggml-small.bin" if (ROOT / "models" / "ggml-small.bin").exists()
    else ROOT / "models" / "ggml-tiny.bin" if (ROOT / "models" / "ggml-tiny.bin").exists()
    else ROOT / "models" / "ggml-base.bin" if (ROOT / "models" / "ggml-base.bin").exists()
    else ROOT / "models" / "ggml-base.en.bin"
)
WHISPER_MODEL = Path(os.environ.get("WHISPER_MODEL", _default_whisper))
WHISPER_PORT = int(os.environ.get("WHISPER_PORT", "8188"))
WHISPER_THREADS = int(os.environ.get("WHISPER_THREADS", str(min(8, os.cpu_count() or 6))))

SAMPLE_RATE = 16000
TTS_VOICE = os.environ.get("TTS_VOICE", "Samantha")
TTS_RATE = int(os.environ.get("TTS_RATE", "210"))

# Confidence gates (tune on your own usage; see docs.typesafe.ai/confidence)
ACTION_MIN_CONFIDENCE = float(os.environ.get("ACTION_MIN_CONFIDENCE", "0.35"))
YES = 0.6

# Antigravity CLI Fallback: when Jev cannot execute or confidence is low, hand off to agy
FALLBACK_TO_ANTIGRAVITY = os.environ.get("FALLBACK_TO_ANTIGRAVITY", "1") not in ("0", "false", "no")
ANTIGRAVITY_MODEL = os.environ.get("ANTIGRAVITY_MODEL", "")
ANTIGRAVITY_TIMEOUT = float(os.environ.get("ANTIGRAVITY_TIMEOUT", "180"))
