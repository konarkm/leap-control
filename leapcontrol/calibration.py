from __future__ import annotations

import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CalibrationProfile, fixture_root, profile_path, save_profile, write_json
from .models import FrameSnapshot, HandMetrics
from .replay import run_replay
from .sensor import LiveSensor


def _quantile(values: list[float], q: float, default: float) -> float:
    if not values:
        return default
    if len(values) == 1:
        return values[0]
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
    return values[idx]


@dataclass(slots=True)
class CalibrationStep:
    name: str
    prompt: str
    duration_s: float
    initial_state: str = "idle"
    voice: dict[str, Any] | None = None


class CalibrationRunner:
    def __init__(self, tracking_mode: str = "desktop"):
        self.sensor = LiveSensor(tracking_mode=tracking_mode)

    async def run(self, profile_name: str = "default") -> dict[str, Any]:
        self.sensor.open()
        session_dir = fixture_root() / time.strftime("%Y%m%d-%H%M%S")
        session_dir.mkdir(parents=True, exist_ok=True)

        steps = [
            CalibrationStep(
                "neutral_hand_present",
                "Place one relaxed hand over the sensor for 2 seconds.",
                2.0,
                initial_state="idle",
            ),
            CalibrationStep(
                "wake_open_palm_hold",
                "Hold an open palm steady over the sensor for 2 seconds.",
                2.0,
                initial_state="idle",
            ),
            CalibrationStep(
                "pinch_hold_release",
                "Start relaxed, then pinch and hold briefly, then release.",
                2.0,
                initial_state="armed",
                voice={"transcript_partial": "draft transcript", "session_active": False},
            ),
            CalibrationStep(
                "cancel_open_palm_hold",
                "While ready to cancel, hold the open palm steady again.",
                2.0,
                initial_state="preview",
                voice={"transcript_partial": "preview transcript", "options": ["One", "Two"]},
            ),
            CalibrationStep(
                "cycle_right",
                "Perform a deliberate rightward cycle swipe.",
                1.5,
                initial_state="preview",
                voice={"transcript_partial": "preview transcript", "options": ["One", "Two", "Three"]},
            ),
            CalibrationStep(
                "cycle_left",
                "Perform a deliberate leftward cycle swipe.",
                1.5,
                initial_state="preview",
                voice={"transcript_partial": "preview transcript", "options": ["One", "Two", "Three"]},
            ),
        ]

        captures: dict[str, list[FrameSnapshot]] = {}
        print("Starting guided Leap Control calibration.")
        for step in steps:
            input(f"\n{step.prompt}\nPress Enter to capture {step.name}...")
            captures[step.name] = await self._capture(step.duration_s)
            print(f"Captured {len(captures[step.name])} frames for {step.name}.")

        profile = self._derive_profile(captures)
        save_profile(profile, profile_name)

        summary = {"profile_path": str(profile_path(profile_name)), "fixtures": [], "checks": []}
        for step in steps:
            frames = captures[step.name]
            replay = run_replay(
                frames,
                profile,
                metadata={
                    "name": step.name,
                    "initial_state": step.initial_state,
                    "voice": step.voice or {},
                },
            )
            expected_public = [
                {"event": event.name, "phase": event.phase, "hand": event.hand}
                for event in replay.public_events
            ]
            fixture_path = session_dir / f"{step.name}.json"
            write_json(
                fixture_path,
                {
                    "metadata": {
                        "name": step.name,
                        "initial_state": step.initial_state,
                        "voice": step.voice or {},
                    },
                    "frames": [frame.to_dict() for frame in frames],
                    "expected_public_events": expected_public,
                },
            )
            summary["fixtures"].append(str(fixture_path))
            summary["checks"].append(
                {
                    "name": step.name,
                    "event_count": len(expected_public),
                    "events": expected_public,
                }
            )

        return summary

    async def _capture(self, duration_s: float) -> list[FrameSnapshot]:
        frames: list[FrameSnapshot] = []
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            event = await self.sensor.next_event(timeout_ms=25)
            if event is None or event.kind != "frame" or event.frame is None:
                continue
            frames.append(event.frame)
        return frames

    def _derive_profile(self, captures: dict[str, list[FrameSnapshot]]) -> CalibrationProfile:
        neutral_hands = [frame.hand for frame in captures["neutral_hand_present"] if frame.hand]
        wake_hands = [frame.hand for frame in captures["wake_open_palm_hold"] if frame.hand]
        pinch_hands = [frame.hand for frame in captures["pinch_hold_release"] if frame.hand]
        cancel_hands = [frame.hand for frame in captures["cancel_open_palm_hold"] if frame.hand]
        cycle_right = [frame.hand for frame in captures["cycle_right"] if frame.hand]
        cycle_left = [frame.hand for frame in captures["cycle_left"] if frame.hand]

        neutral_pinch = [hand.pinch_strength for hand in neutral_hands]
        pinch_values = [hand.pinch_strength for hand in pinch_hands]
        neutral_speed = [hand.palm_speed for hand in neutral_hands]
        wake_speed = [hand.palm_speed for hand in wake_hands]
        wake_grab = [hand.grab_strength for hand in wake_hands + cancel_hands]
        cycle_velocity = [
            abs(hand.palm_velocity.x) for hand in cycle_right + cycle_left if hand is not None
        ]

        start_threshold = (
            _quantile(neutral_pinch, 0.95, 0.35) + _quantile(pinch_values, 0.25, 0.85)
        ) / 2.0
        start_threshold = max(0.55, min(0.95, start_threshold))
        release_threshold = max(0.20, min(start_threshold - 0.10, start_threshold * 0.55))
        stillness = max(
            40.0,
            _quantile(neutral_speed + wake_speed, 0.9, 55.0) * 1.10,
        )
        swipe_velocity = max(160.0, _quantile(cycle_velocity, 0.35, 220.0) * 0.75)
        active_hand = "either"
        all_hands = neutral_hands + wake_hands + pinch_hands + cancel_hands
        if all_hands:
            hand_names = [hand.hand for hand in all_hands]
            active_hand = statistics.mode(hand_names)

        return CalibrationProfile(
            active_hand_preference=active_hand,
            open_palm_min_fingers=4,
            open_palm_max_grab=min(0.45, _quantile(wake_grab, 0.85, 0.30) + 0.05),
            pinch_start_threshold=start_threshold,
            pinch_release_threshold=release_threshold,
            grab_threshold=max(0.65, _quantile([hand.grab_strength for hand in pinch_hands], 0.90, 0.75)),
            stillness_velocity_threshold=stillness,
            swipe_velocity_threshold=swipe_velocity,
            swipe_min_distance=45.0,
        )


@dataclass(slots=True)
class SessionAnalysisSegment:
    label: str
    start_time: float
    end_time: float
    frame_count: int
    hand: str
    pinch_min: float
    pinch_max: float
    grab_min: float
    grab_max: float
    finger_set: list[int]
    max_abs_vx: float
    max_speed: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_s": self.end_time - self.start_time,
            "frame_count": self.frame_count,
            "hand": self.hand,
            "pinch_min": self.pinch_min,
            "pinch_max": self.pinch_max,
            "grab_min": self.grab_min,
            "grab_max": self.grab_max,
            "finger_set": self.finger_set,
            "max_abs_vx": self.max_abs_vx,
            "max_speed": self.max_speed,
        }


class SessionRecorder:
    def __init__(self, tracking_mode: str = "desktop"):
        self.sensor = LiveSensor(tracking_mode=tracking_mode)

    async def record(self, duration_s: float, output_path: Path) -> dict[str, Any]:
        frames: list[FrameSnapshot] = []
        self.sensor.open()
        started = time.monotonic()
        deadline = started + duration_s
        try:
            while time.monotonic() < deadline:
                event = await self.sensor.next_event(timeout_ms=25)
                if event is None or event.kind != "frame" or event.frame is None:
                    continue
                frames.append(event.frame)
        finally:
            self.sensor.close()

        payload = {
            "metadata": {
                "kind": "raw_session",
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "duration_s": duration_s,
                "frame_count": len(frames),
            },
            "frames": [frame.to_dict() for frame in frames],
        }
        write_json(output_path, payload)
        return payload["metadata"]


def analyze_session_frames(
    frames: list[FrameSnapshot], profile: CalibrationProfile
) -> dict[str, Any]:
    hands = [frame.hand for frame in frames if frame.hand is not None]
    summary = {
        "frame_count": len(frames),
        "hand_frames": len(hands),
        "hands_seen": sorted({hand.hand for hand in hands}),
        "pinch_range": None,
        "grab_range": None,
        "speed_range": None,
        "finger_set": sorted({hand.finger_count for hand in hands}),
        "segments": [],
    }
    if not hands:
        return summary

    pinch_values = [hand.pinch_strength for hand in hands]
    grab_values = [hand.grab_strength for hand in hands]
    speed_values = [hand.palm_speed for hand in hands]
    summary["pinch_range"] = [min(pinch_values), max(pinch_values)]
    summary["grab_range"] = [min(grab_values), max(grab_values)]
    summary["speed_range"] = [min(speed_values), max(speed_values)]
    summary["segments"] = [segment.to_dict() for segment in _find_segments(frames, profile)]
    summary["suggested_profile"] = _suggest_profile_from_raw_session(hands, profile)
    return summary


def load_session_and_analyze(path: Path, profile: CalibrationProfile) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    frames = [FrameSnapshot.from_dict(item) for item in payload.get("frames", [])]
    return {
        "path": str(path),
        "metadata": payload.get("metadata", {}),
        "analysis": analyze_session_frames(frames, profile),
    }


def _frame_label(frame: FrameSnapshot, profile: CalibrationProfile) -> str | None:
    hand = frame.hand
    if hand is None:
        return None
    if hand.pinch_strength >= profile.pinch_start_threshold:
        return "pinch_active"
    if hand.grab_strength >= max(profile.grab_threshold, 0.65):
        return "grab_active"
    if _is_open_palm(hand, profile):
        return "open_palm"
    return "other"


def _is_open_palm(hand: HandMetrics, profile: CalibrationProfile) -> bool:
    return (
        hand.finger_count >= profile.open_palm_min_fingers
        and hand.grab_strength <= max(profile.open_palm_max_grab, 0.18)
        and hand.pinch_strength <= max(profile.pinch_release_threshold, 0.20)
        and hand.palm_speed <= max(profile.stillness_velocity_threshold, 55.0)
    )


def _find_segments(
    frames: list[FrameSnapshot], profile: CalibrationProfile
) -> list[SessionAnalysisSegment]:
    segments: list[SessionAnalysisSegment] = []
    current_label: str | None = None
    current_frames: list[FrameSnapshot] = []

    def flush() -> None:
        nonlocal current_label, current_frames
        if not current_label or not current_frames:
            current_label = None
            current_frames = []
            return
        if len(current_frames) < 8:
            current_label = None
            current_frames = []
            return
        hands = [frame.hand for frame in current_frames if frame.hand is not None]
        if not hands:
            current_label = None
            current_frames = []
            return
        segments.append(
            SessionAnalysisSegment(
                label=current_label,
                start_time=current_frames[0].monotonic_time,
                end_time=current_frames[-1].monotonic_time,
                frame_count=len(current_frames),
                hand=statistics.mode([hand.hand for hand in hands]),
                pinch_min=min(hand.pinch_strength for hand in hands),
                pinch_max=max(hand.pinch_strength for hand in hands),
                grab_min=min(hand.grab_strength for hand in hands),
                grab_max=max(hand.grab_strength for hand in hands),
                finger_set=sorted({hand.finger_count for hand in hands}),
                max_abs_vx=max(abs(hand.palm_velocity.x) for hand in hands),
                max_speed=max(hand.palm_speed for hand in hands),
            )
        )
        current_label = None
        current_frames = []

    for frame in frames:
        label = _frame_label(frame, profile)
        if label == current_label:
            current_frames.append(frame)
            continue
        flush()
        current_label = label
        current_frames = [frame] if label is not None else []
    flush()
    return segments


def _suggest_profile_from_raw_session(
    hands: list[HandMetrics], profile: CalibrationProfile
) -> dict[str, Any]:
    open_palm = [hand for hand in hands if hand.finger_count >= 4 and hand.grab_strength <= 0.18]
    pinch_active = [hand for hand in hands if hand.pinch_strength >= 0.55]
    grab_active = [hand for hand in hands if hand.grab_strength >= 0.65]
    neutral = [
        hand
        for hand in hands
        if hand.pinch_strength <= 0.15 and hand.grab_strength <= 0.15 and hand.finger_count >= 4
    ]

    pinch_start = max(
        0.55,
        min(
            0.9,
            (_quantile([hand.pinch_strength for hand in neutral], 0.95, 0.12) +
             _quantile([hand.pinch_strength for hand in pinch_active], 0.20, 0.82))
            / 2.0,
        ),
    )
    pinch_release = max(0.2, min(pinch_start * 0.6, pinch_start - 0.1))
    open_palm_max_grab = min(
        0.25,
        _quantile([hand.grab_strength for hand in open_palm], 0.90, 0.08) + 0.03,
    )
    stillness_velocity = max(
        45.0,
        _quantile([hand.palm_speed for hand in open_palm + neutral], 0.90, 55.0) * 1.15,
    )
    grab_threshold = max(
        0.65,
        min(
            0.92,
            (_quantile([hand.grab_strength for hand in neutral], 0.95, 0.10) +
             _quantile([hand.grab_strength for hand in grab_active], 0.20, 0.82))
            / 2.0,
        ),
    )
    return {
        "active_hand_preference": statistics.mode([hand.hand for hand in hands]) if hands else profile.active_hand_preference,
        "pinch_start_threshold": pinch_start,
        "pinch_release_threshold": pinch_release,
        "grab_threshold": grab_threshold,
        "open_palm_max_grab": open_palm_max_grab,
        "stillness_velocity_threshold": stillness_velocity,
    }
