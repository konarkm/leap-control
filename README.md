# Leap Control

Gesture-first local controller for Ultraleap / Leap Motion on macOS.

This repo is an experiment in using pinch, pinch-hold, and pinch-drag as a lightweight control layer on top of the Mac. The current implementation is intentionally simple and practical:

- short pinch -> `Enter`
- long pinch hold -> hold `right_control`
- vertical pinch-drag -> natural scrolling

It also exposes a small localhost websocket API so a future voice layer, CLI tool, or app adapter can subscribe to gesture events.

## Current State

Implemented:

- live Ultraleap frame ingestion through a small C helper plus Python controller
- pinch tap vs pinch hold recognition
- latched pinch-drag with axis locking
- continuous vertical scrolling from held-pinch drag
- localhost websocket debug/event stream
- JSONL event logging
- offline tests for recognizer, state machine, and action routing

Not production-ready:

- the Tk HUD is not reliable on macOS yet
- no packaged installer or launch agent
- gesture vocabulary is still intentionally small

## Requirements

- macOS
- Ultraleap Hand Tracking installed
- Python 3.13
- PyObjC
- `websockets`
- Xcode Command Line Tools / `clang`

The tracking stack uses `LeapC` directly and does not depend on the bundled `leapc_cffi` wheel.

## Setup

Clone the repo and install dependencies:

```bash
git clone https://github.com/konarkm/leap-control.git
cd leap-control
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
```

The live sensor path uses a small C helper that is built automatically on first run from `src/leap_stream_helper.c`, so you do not need a separate manual build step.

## Quick Start

Run the live controller:

```bash
python3 -m leapcontrol run --no-overlay
```

In another terminal, watch the debug stream:

```bash
python3 -m leapcontrol watch-debug
```

Current default gestures:

- short pinch: sends `Enter`
- long pinch hold: holds `right_control`
- held pinch + vertical drag: scrolls with natural direction

## Calibration and Replay

Run guided calibration:

```bash
python3 -m leapcontrol calibrate --profile default
```

Replay a saved fixture:

```bash
python3 -m leapcontrol replay ~/Library/Application\\ Support/LeapControl/fixtures/<session>/<fixture>.json
```

Record and analyze a raw session:

```bash
python3 -m leapcontrol record-session --duration 12
python3 -m leapcontrol analyze-session ~/Library/Application\\ Support/LeapControl/fixtures/<session>/raw_session.json
```

## Local API

Default websocket endpoint:

- `ws://127.0.0.1:8765`

Outbound message types:

- `gesture_event`
- `controller_state`
- `hud_state`
- `system_event`

Inbound message types:

- `voice_state`
- `debug_command`

Example inbound payload:

```json
{
  "type": "voice_state",
  "status": "partial",
  "text": "draft transcript",
  "options": ["Option A", "Option B"]
}
```

## Local Data

Default app home:

- `~/Library/Application Support/LeapControl`

Generated local files:

- `config.json`
- `profiles/<name>.json`
- `fixtures/<session>/*.json`
- `logs/events.jsonl`

Use a separate app home for development:

```bash
export LEAPCONTROL_HOME=/tmp/leapcontrol-dev
```

## Tests

Run the software-only test suite:

```bash
python3 -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)
