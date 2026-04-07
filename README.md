# Leap Control v1

Python-first gesture + voice controller for Ultraleap/Leap Motion on macOS.

## What it does

- Reads live `LeapC` hand-tracking frames from the installed Ultraleap runtime
- Recognizes a small control-oriented gesture vocabulary:
  - `ptt_start`
  - `ptt_end`
  - `confirm`
  - `hand_present`
  - `hand_lost`
- Maintains a simple pinch-first controller state machine
- Shows a minimal always-on-top HUD
- Exposes a localhost websocket API for external voice feeds and future adapters
- Supports guided calibration and offline replay fixtures
- Writes persistent JSONL logs for frames, recognizer events, public events, and debug metrics

## Requirements

- macOS with Ultraleap Hand Tracking installed
- Python 3.13
- PyObjC and `websockets` available in the active Python

The implementation uses `ctypes` for `LeapC`, so it does not depend on the bundled
`leapc_cffi` CPython 3.12 module.

## Commands

Run the controller:

```bash
python3 -m leapcontrol run
```

Run guided calibration:

```bash
python3 -m leapcontrol calibrate --profile default
```

Replay a saved fixture:

```bash
python3 -m leapcontrol replay ~/Library/Application\ Support/LeapControl/fixtures/<session>/<fixture>.json
```

Watch live debug output:

```bash
python3 -m leapcontrol watch-debug
```

Send external voice updates into the live controller:

```bash
python3 -m leapcontrol voice session_started
python3 -m leapcontrol voice partial --text "draft transcript"
python3 -m leapcontrol voice final --text "final transcript" --options OptionA OptionB
python3 -m leapcontrol voice cancelled
```

## Local API

The controller listens on:

- `ws://127.0.0.1:8765`

Outbound messages:

- `gesture_event`
- `controller_state`
- `hud_state`
- `system_event`

Inbound messages:

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

## Config and data

Default app home:

- `~/Library/Application Support/LeapControl`

Generated files:

- `config.json`
- `profiles/<name>.json`
- `fixtures/<session>/*.json`
- `logs/events.jsonl`

Set a custom app home for development:

```bash
export LEAPCONTROL_HOME=/tmp/leapcontrol-dev
```

## Tests

Run the software-only tests:

```bash
python3 -m unittest discover -s /Users/konark/code/leap/tests -v
```
