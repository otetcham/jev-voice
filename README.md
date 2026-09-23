# Jev Voice (Windows & macOS + Japanese Support)

Talk to your PC / Mac in English or Japanese. You speak, it opens apps, types, searches, scrolls, presses keys.

Everything runs locally except one ~250 ms call to **Jev** (TypeSafe's System One model / OpenRouter `typesafe/jev-1.13`), which turns the transcript into a typed action plus typed arguments in a single fan-out request. Jev never generates text; code produces candidate values and Jev *selects*. Code owns execution.

```
mic ─► energy VAD ─► whisper.cpp (~100 ms) ─► Jev (1 request, ~250 ms) ─► OS actions (Win32/macOS) ─► TTS
```

## Features
- **Cross-Platform**: Full native execution on **Windows** (`ctypes.windll.user32` / PowerShell) and **macOS** (`AppKit` / `Quartz`).
- **Japanese Voice Support (日本語対応)**: Transcribe and execute natural Japanese commands (e.g. 「Chromeを開いて」「YouTubeでLo-Fiを検索」「こんにちはと入力してエンター」).
- **Dual API Support**: Works out-of-the-box with **TypeSafe API** (`TYPESAFE_API_KEY`) or **OpenRouter** (`OPENROUTER_API_KEY`).

---

## Setup (Windows)

1. **Clone & Configure**:
   ```powershell
   git clone https://github.com/otetcham/jev-voice.git
   cd jev-voice
   copy .env.example .env
   ```
2. **Set your API Key** in `.env`:
   ```env
   # Either TypeSafe native key:
   TYPESAFE_API_KEY=your_key_here
   # Or OpenRouter key:
   OPENROUTER_API_KEY=sk-or-v1-...
   
   # For Japanese recognition:
   WHISPER_LANGUAGE=ja
   ```
3. **Install Dependencies**:
   ```powershell
   uv sync
   # or
   pip install -e .
   ```
4. **Whisper Model (Multilingual for Japanese)**:
   ```powershell
   mkdir -p models
   curl -L -o models/ggml-base.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
   ```
   Install `whisper-server.exe` from [whisper.cpp releases](https://github.com/ggerganov/whisper.cpp/releases) and add it to your PATH.

---

## Setup (macOS, Apple Silicon)

```sh
cp .env.example .env                       # add your TYPESAFE_API_KEY or OPENROUTER_API_KEY
./scripts/setup.sh
```

---

## Run

```sh
# Push-to-talk in terminal (Press Enter to start/stop):
jev-voice --ptt

# Direct text command test (no microphone needed):
jev-voice --text "Chromeを開いて" --dry-run
jev-voice --text "YouTubeでLo-Fi音楽を検索"
jev-voice --text "open chrome and go to youtube"

# Hands-free open mic:
jev-voice --always-on
```

## What you can say (音声コマンド例)

| 英語 (English) | 日本語 (Japanese) | 動作 (Action) |
| --- | --- | --- |
| "open chrome", "switch to cursor" | 「Chromeを開いて」「メモ帳を起動」 | アプリ起動・切り替え |
| "go to youtube", "open github" | 「YouTubeを開いて」「GitHubに行って」 | サイトを開く |
| "search youtube for lofi hip hop" | 「YouTubeでローファイを検索」「Pythonの使い方をググって」 | 各種Web検索 |
| "type hello world and hit enter" | 「こんにちはと入力してエンター」 | フォーカス中の欄に入力・送信 |
| "close this tab", "copy", "paste" | 「タブを閉じて」「コピー」「ペースト」「やり直し」 | キーボードショートカット |
| "scroll down", "go to top" | 「下にスクロール」「一番上へ移動」 | マウスホイールスクロール |
| "volume up", "mute", "next song" | 「音量を上げて」「ミュート」「次の曲」 | 音量・メディア操作 |
| "take a screenshot", "lock the screen" | 「スクリーンショットを撮って」「画面をロック」 | システム操作 |

## Multi-step tasks: the ultrafast loop on the desktop

Single commands above are one Jev call and one action. Anything that needs *looking at the
screen* runs the agent loop from [jev-ultrafast](https://github.com/browser-use/jev-ultrafast),
ported from the DOM to the macOS Accessibility tree:

```
AX tree of the frontmost window ─► indexed element table ─► one Jev request ─► executor
                                   [1] button   Back                │ operation
                                   [2] textfield Address and search │ click_target
                                   [3] link     Home                │ type_text_target
                                   ...                              │ open_app_target
                                                                    │ press_key_target
                                                            use the matching head only
```

```sh
jev-agent --goal "open notes and write buy milk"          # from the terminal
jev-agent --goal "..." --choose --elements                # pause before each step, show the table
jev --goal "reply to the last email from Sam saying yes"  # same loop, spoken reply
```

By voice, Jev routes an utterance to `task` when it needs several on-screen steps
("Alfred, find the cheapest flight to London on google flights"). The pill shows each step.

Operations are `CLICK`, `TYPE_TEXT`, `OPEN_APP`, `PRESS_KEY`, `SCROLL_UP`, `SCROLL_DOWN`,
`WAIT`, `DONE`, `BLOCKED`. Only operations with a valid target on this screen are offered.
Every target is an observed `AXUIElement` held by code; the model never emits selectors,
coordinates, scripts, or shell. Before input the executor re-reads the target's role, label,
value and enabled state, re-resolves its geometry, and hit-tests its centre so a covered
control is never clicked. `TYPE_TEXT` values come from a small text model if
`TEXT_MODEL_API_KEY` is set, otherwise Jev *selects* the value from spans cut out of the goal
(nothing generated). Runs are bounded: 40 actions, 80 Jev calls, and three actions in a row
that change nothing stop the run as `BLOCKED`. A `DONE` choice is the model's claim, not proof.

### Browser driver (default) and recommendations

Browser goals run on [jev-ultrafast](https://github.com/browser-use/jev-ultrafast) unmodified:
Chrome over CDP through browser-harness, in a new window on `AGENT_DISPLAY`. One-time setup:
tick **Allow remote debugging for this browser instance** at `chrome://inspect/#remote-debugging`
and click Allow. `TASK_DRIVER=desktop` switches to the experimental Accessibility-tree port.

```sh
jev-agent --url https://www.autotrader.ca --recommend \
  --goal "Find a used 2020 Mercedes-Benz CLA under \$15,000 CAD near Toronto. Postal code M5V 3L9. Stop when the filtered listings are visible."
```

`--recommend` (or saying "recommend me…" by voice) adds one more Jev choice after the run:
code reads the listing cards (title, price, mileage, distance) from the results and following
pages, Jev picks one against your goal, Jev picks the reason from facts code verified
(cheapest, lowest mileage, requested year, closest), and the agent opens that listing.
Nothing is generated. A typical AutoTrader run: ~13 s, ~30 Jev calls, about one cent.

Around ultrafast, all code-owned: controls behind an open modal are withdrawn; an action
repeated twice without leaving the page is withdrawn; a BLOCKED under 50% executes the
runner-up operation from the same request; a DONE chosen twice stands on live pages;
an unchanged page reuses the decision for free; three rejections of one choice stop the run.
Without `TEXT_MODEL_API_KEY`, TYPE_TEXT values are Jev choices over spans cut from the goal
(sentences, comma clauses, labelled values like "postal code M5V 3L9", numbers as "$15,000"/"15000").

### Chess on chess.com (Stockfish proposes, Jev chooses, code moves)

```sh
uv run jev-agent --chess --url https://www.chess.com --goal "On chess.com, start a game and stop when a live board is on screen."
```

Jev gets the tab to a live game (Play, matchmaking, or resuming a game already open). From there, each turn:
code reads the board from the DOM and keeps the exact position with python-chess (the opponent's move is
inferred from the changed squares); Stockfish returns its top five moves with evaluations; Jev selects one
(strongest by default, `CHESS_STYLE` to bias it); code clicks the piece and the square and confirms the board.
About 1.3 s per move. It has won rated 10-minute games by checkmate.

**Teaching mode** (on by default): true facts about the chosen move are computed in code, Jev picks the one worth
stressing, Haiku writes a coach's sentence from those facts only, and the local open-source Kokoro voice speaks
it. The move waits for the narration to finish (and at least `CHESS_MOVE_DELAY` seconds). The inspector shows the
decision tree under the live feed: every candidate in plain words ("pawn takes pawn on e5"), its rank, eval,
line and Jev's probability, plus the narration. `CHESS_VOICE=0` mutes; `CHESS_EXPLAIN=template` skips the LLM.

Engine play in rated games is against chess.com's fair-play rules; use bots or unrated games for an account you care about.

### Inspector

```sh
uv run jev-inspect          # open http://127.0.0.1:8766 on the monitor the agent is NOT confined to
```

The inspector is the jev-ultrafast demo page for the desktop: the confined monitor with numbered
element badges, the operation and target probabilities of each Jev request, the text value
(selected by Jev or written by the text helper), the executed-step checklist with elapsed
seconds and median decision latency, and an exportable decision trail. **Choose next** pauses
before execution; **Run automatically** loops. Pick the monitor in the form; `AGENT_DISPLAY`
in `.env` sets the default. Left/right follow the macOS Displays arrangement, so use `main`
or an index when that differs from the physical layout.

### Browser-use modes

```sh
uv run jev-modes            # open http://127.0.0.1:8767
```

A second, separate page (own port, own static files) that drives Chrome in one of three modes:

| Mode | What runs |
| --- | --- |
| **Ultrafast** | jev-ultrafast exactly as it shipped: the stock `Agent` on a plain CDP tab, Jev chooses, the OpenAI-compatible text helper writes `TYPE_TEXT` (needs `TEXT_MODEL_API_KEY`), 60-step budget, no guards, no Claude. Its Google Flights and fixture scenarios are kept. |
| **Jev + guards** | `WebAgent` with Claude switched off: the window confined to `AGENT_DISPLAY`, modal/cycle/futile pruning, hesitant BLOCKED, provider retries, `TYPE_TEXT` selected by Jev from the goal when no text model is set. |
| **Agent** | The full agent: Claude planner, Jev → Haiku → Fable tie-breaks, DONE verifier, learned site rules and per-site trust. Needs `ANTHROPIC_API_KEY`. |

Step through with **Choose next / Execute choice**, or **Run automatically** (a background job the page polls; **Pause** stops after the current step). Agent modes accept a follow-up goal on the same tab. The right column shows Jev's operation and target probabilities, the text value, run cost, and, in agent mode, every Claude escalation.

Read [docs/design.md](docs/design.md) for the freshness guards and the differences from the browser version.

## How the Jev layer works (`jev_voice/brain.py`)

One request per utterance with ~15 speculative questions evaluated in parallel:

- `action` — Choice over 13 action kinds.
- `app` — Choice over your installed apps (+ `none`); `site`, `engine`, `folder`,
  `shortcut`, `scroll_dir`, `volume_op`, `media_op`, `system_op` — Choices over
  closed sets whose keys are exactly what the executor accepts.
- `text` — Choice over **candidate spans** cut from the transcript by regex
  ("type X", "search for X", quoted text, whole utterance). Jev picks the one that
  is exactly the payload. This is the "select instead of generate" pattern.
- `submit`, `compound` — Nouls.

Code reads only the answers the chosen action needs. Plan confidence is the
minimum over the judgements used. Below `ACTION_MIN_CONFIDENCE` (0.35) it says
"not sure" instead of acting. Thresholds live in `jev_voice/config.py`.

## Latency (Mac mini M4, measured)

| Stage | Time |
| --- | --- |
| End-of-speech detection | 550 ms of silence (tune `VADConfig.end_silence_ms`) |
| whisper.cpp base.en | 80–130 ms |
| Jev fan-out | 170–420 ms |
| Execute + `say` | ~50–100 ms |

## Floating transcription pill

A small always-on-top bar at the top-center of the screen shows what whisper
heard, what Jev decided, and the result (gray idle · red listening · yellow
heard · blue thinking · green done · orange error). It never takes keyboard
focus. `OVERLAY=0` or `--no-overlay` hides it.

## Feedback

`FEEDBACK=ding` (default) plays a chime when an action completes and a low buzz
on failure. `FEEDBACK=voice` gives spoken replies from a posh butler persona
(`PERSONA=alfred`, or `cowboy`) using the best British voice installed, or
ElevenLabs if `ELEVENLABS_API_KEY` is set (phrases cached to disk, so repeats are
instant).

## Layout

```
jev_voice/
  main.py     loop, CLI, compound handling, task hand-off
  brain.py    Jev questions, candidate extraction, Plan (single commands)
  agent.py    multi-step loop: observe → choose → act (port of jev-ultrafast/agent.py)
  desktop.py  AX-tree snapshot, indexed controls, freshness guards, execution (snapshot.js + browser.py)
  policy.py   dynamic operation/target heads, text helper (model.py)
  questions.py model instructions for the agent
  inspector.py loopback inspector server (demo.py); static/ holds the page
  modes.py    browser-use modes page (ultrafast / jev + guards / agent); static_modes/ holds it
  web.py      browser driver: jev-ultrafast Agent/Browser on a confined Chrome window + guards
  recommend.py listing harvest → Jev pick → verified reason → open the listing
  chess_play.py board reader, Stockfish candidates → Jev choice, click-click moves, teaching lines
  escalate.py  Haiku/Fable escalation: plan, text values, tie-break, verify, progress, move explanations
  costs.py    Jev / text-helper cost accounting
  actions.py  macOS execution (open, keystrokes, scroll, volume, media keys…)
  audio.py    mic + VAD endpointing
  stt.py      whisper-server client
  tts.py      macOS `say`
  config.py   env / thresholds
  hotkey.py   Caps Lock (remapped to F18) global key tap
  overlay.py  floating transcription pill (AppKit)
  persona.py  butler / cowboy phrasing
scripts/
  setup.sh    one-shot install: deps, model, Caps Lock remap, launcher, permissions
tests/
  test_agent.py  offline contracts for the agent loop (no screen, no paid APIs)
```

## Development

```sh
uv run ruff check .
uv run pytest          # offline
```

## License

MIT
