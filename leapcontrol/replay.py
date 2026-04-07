from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CalibrationProfile
from .models import FrameSnapshot, InternalEvent, PublicEvent
from .recognizer import GestureRecognizer
from .sensor import load_frames_from_fixture
from .state_machine import InteractionStateMachine


@dataclass(slots=True)
class ReplayResult:
    metadata: dict[str, Any]
    internal_events: list[InternalEvent]
    public_events: list[PublicEvent]


def run_replay(
    frames: list[FrameSnapshot],
    profile: CalibrationProfile,
    *,
    metadata: dict[str, Any] | None = None,
) -> ReplayResult:
    metadata = metadata or {}
    recognizer = GestureRecognizer(profile)
    machine = InteractionStateMachine(profile)
    if frames:
        machine.seed(
            metadata.get("initial_state", "idle"),
            now=frames[0].monotonic_time,
            voice=metadata.get("voice"),
            selection_index=int(metadata.get("selection_index", 0)),
        )
    internal_events: list[InternalEvent] = []
    public_events: list[PublicEvent] = []
    for frame in frames:
        for event in recognizer.process(frame):
            internal_events.append(event)
            public_events.extend(machine.handle_internal(event))
    return ReplayResult(metadata=metadata, internal_events=internal_events, public_events=public_events)


def load_fixture(path: Path) -> tuple[dict[str, Any], list[FrameSnapshot], list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    frames = [FrameSnapshot.from_dict(item) for item in payload.get("frames", [])]
    expected_public = list(payload.get("expected_public_events", []))
    return payload.get("metadata", {}), frames, expected_public
