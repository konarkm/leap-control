from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import time

import websockets

from .calibration import CalibrationRunner, SessionRecorder, load_session_and_analyze
from .config import (
    AppConfig,
    CalibrationProfile,
    fixture_root,
    load_app_config,
    load_profile,
)
from .controller import LeapControlController
from .replay import load_fixture, run_replay


async def _send_api_message(host: str, port: int, payload: dict) -> None:
    uri = f"ws://{host}:{port}"
    async with websockets.connect(uri) as websocket:
        await websocket.recv()  # hello
        await websocket.send(json.dumps(payload))


async def _watch_api(host: str, port: int) -> None:
    uri = f"ws://{host}:{port}"
    last_debug: dict | None = None
    async with websockets.connect(uri) as websocket:
        async for raw in websocket:
            payload = json.loads(raw)
            kind = payload.get("type")
            if kind == "debug_metrics":
                drag_delta = payload.get("drag_delta") or {}
                compact = {
                    "state": payload.get("controller_state"),
                    "gesture": payload.get("active_gesture"),
                    "hand": payload.get("hand"),
                    "pinch": round(float(payload.get("pinch_strength", 0.0)), 3),
                    "grab": round(float(payload.get("grab_strength", 0.0)), 3),
                    "fingers": payload.get("finger_count"),
                    "speed": round(float(payload.get("palm_speed", 0.0)), 1),
                    "pinch_hold_emitted": payload.get("pinch_hold_emitted"),
                    "drag_active": payload.get("drag_active"),
                    "drag_axis": payload.get("drag_axis"),
                    "drag_direction": payload.get("drag_direction"),
                    "drag_dx": round(float(drag_delta.get("x", 0.0)), 1),
                    "drag_dy": round(float(drag_delta.get("y", 0.0)), 1),
                    "drag_axis_value": round(float(payload.get("drag_axis_value", 0.0)), 1),
                }
                if compact != last_debug:
                    print(json.dumps(compact))
                    last_debug = compact
            else:
                print(json.dumps(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leapcontrol")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the live controller.")
    run_parser.add_argument("--profile", default="default")
    run_parser.add_argument("--overlay", action=argparse.BooleanOptionalAction, default=True)

    calibrate_parser = sub.add_parser("calibrate", help="Run guided calibration.")
    calibrate_parser.add_argument("--profile", default="default")

    record_parser = sub.add_parser("record-session", help="Record a raw unlabeled sensor session.")
    record_parser.add_argument("--duration", type=float, default=12.0)
    record_parser.add_argument("--output", type=Path, default=None)

    analyze_parser = sub.add_parser("analyze-session", help="Analyze a raw recorded session.")
    analyze_parser.add_argument("session", type=Path)
    analyze_parser.add_argument("--profile", default="default")

    replay_parser = sub.add_parser("replay", help="Replay a saved fixture.")
    replay_parser.add_argument("fixture", type=Path)
    replay_parser.add_argument("--profile", default="default")

    voice_parser = sub.add_parser("voice", help="Send an external voice state update.")
    voice_parser.add_argument("status", choices=["session_started", "partial", "final", "cancelled"])
    voice_parser.add_argument("--text", default="")
    voice_parser.add_argument("--options", nargs="*", default=None)

    seed_parser = sub.add_parser("seed-state", help="Force a controller state for local debugging.")
    seed_parser.add_argument("state")
    seed_parser.add_argument("--selection-index", type=int, default=0)

    watch_parser = sub.add_parser("watch-debug", help="Watch live controller debug output.")
    watch_parser.add_argument("--host", default=None)
    watch_parser.add_argument("--port", type=int, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_app_config()

    if args.command == "run":
        config.overlay_enabled = args.overlay
        profile = load_profile(args.profile)
        controller = LeapControlController(config, profile)
        try:
            asyncio.run(controller.run())
        except KeyboardInterrupt:
            return 0
        return 0

    if args.command == "calibrate":
        runner = CalibrationRunner(tracking_mode=config.tracking_mode)
        summary = asyncio.run(runner.run(profile_name=args.profile))
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "record-session":
        output = args.output
        if output is None:
            output = fixture_root() / time.strftime("%Y%m%d-%H%M%S") / "raw_session.json"
        recorder = SessionRecorder(tracking_mode=config.tracking_mode)
        summary = asyncio.run(recorder.record(args.duration, output))
        print(json.dumps({"output": str(output), "metadata": summary}, indent=2))
        return 0

    if args.command == "analyze-session":
        payload = load_session_and_analyze(args.session, load_profile(args.profile))
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "replay":
        metadata, frames, expected = load_fixture(args.fixture)
        result = run_replay(frames, load_profile(args.profile), metadata=metadata)
        payload = {
            "fixture": str(args.fixture),
            "expected_public_events": expected,
            "actual_public_events": [event.to_message() for event in result.public_events],
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "voice":
        asyncio.run(
            _send_api_message(
                config.api_host,
                config.api_port,
                {
                    "type": "voice_state",
                    "status": args.status,
                    "text": args.text,
                    "options": args.options,
                },
            )
        )
        return 0

    if args.command == "seed-state":
        asyncio.run(
            _send_api_message(
                config.api_host,
                config.api_port,
                {
                    "type": "debug_command",
                    "command": "seed_state",
                    "state": args.state,
                    "selection_index": args.selection_index,
                },
            )
        )
        return 0

    if args.command == "watch-debug":
        host = args.host or config.api_host
        port = args.port or config.api_port
        try:
            asyncio.run(_watch_api(host, port))
        except KeyboardInterrupt:
            return 0
        return 0

    parser.error("Unknown command")
    return 2
