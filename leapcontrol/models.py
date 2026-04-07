from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ControllerStateName = Literal[
    "idle",
    "armed",
    "listening",
    "preview",
    "confirmed",
    "cancelled",
]
HandName = Literal["left", "right", "unknown"]
EventPhase = Literal["start", "update", "end", "instant"]


@dataclass(slots=True)
class Vector3:
    x: float
    y: float
    z: float

    @property
    def magnitude(self) -> float:
        return (self.x ** 2 + self.y ** 2 + self.z ** 2) ** 0.5

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Vector3":
        return cls(
            x=float(payload.get("x", 0.0)),
            y=float(payload.get("y", 0.0)),
            z=float(payload.get("z", 0.0)),
        )


@dataclass(slots=True)
class HandMetrics:
    hand: HandName
    confidence: float
    flags: int
    pinch_strength: float
    pinch_distance: float
    grab_strength: float
    grab_angle: float
    finger_count: int
    visible_time_us: int
    palm_position: Vector3
    palm_velocity: Vector3
    palm_normal: Vector3
    palm_direction: Vector3
    palm_width: float

    @property
    def palm_speed(self) -> float:
        return self.palm_velocity.magnitude

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["palm_position"] = self.palm_position.to_dict()
        payload["palm_velocity"] = self.palm_velocity.to_dict()
        payload["palm_normal"] = self.palm_normal.to_dict()
        payload["palm_direction"] = self.palm_direction.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HandMetrics":
        return cls(
            hand=payload.get("hand", "unknown"),
            confidence=float(payload.get("confidence", 0.0)),
            flags=int(payload.get("flags", 0)),
            pinch_strength=float(payload.get("pinch_strength", 0.0)),
            pinch_distance=float(payload.get("pinch_distance", 0.0)),
            grab_strength=float(payload.get("grab_strength", 0.0)),
            grab_angle=float(payload.get("grab_angle", 0.0)),
            finger_count=int(payload.get("finger_count", 0)),
            visible_time_us=int(payload.get("visible_time_us", 0)),
            palm_position=Vector3.from_dict(payload.get("palm_position", {})),
            palm_velocity=Vector3.from_dict(payload.get("palm_velocity", {})),
            palm_normal=Vector3.from_dict(payload.get("palm_normal", {})),
            palm_direction=Vector3.from_dict(payload.get("palm_direction", {})),
            palm_width=float(payload.get("palm_width", 0.0)),
        )


@dataclass(slots=True)
class FrameSnapshot:
    monotonic_time: float
    service_timestamp_us: int
    frame_id: int
    tracking_frame_id: int
    framerate: float
    device_id: int
    hand: HandMetrics | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "monotonic_time": self.monotonic_time,
            "service_timestamp_us": self.service_timestamp_us,
            "frame_id": self.frame_id,
            "tracking_frame_id": self.tracking_frame_id,
            "framerate": self.framerate,
            "device_id": self.device_id,
            "hand": None if self.hand is None else self.hand.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FrameSnapshot":
        hand_payload = payload.get("hand")
        return cls(
            monotonic_time=float(payload["monotonic_time"]),
            service_timestamp_us=int(payload.get("service_timestamp_us", 0)),
            frame_id=int(payload.get("frame_id", 0)),
            tracking_frame_id=int(payload.get("tracking_frame_id", 0)),
            framerate=float(payload.get("framerate", 0.0)),
            device_id=int(payload.get("device_id", 0)),
            hand=None if hand_payload is None else HandMetrics.from_dict(hand_payload),
        )


@dataclass(slots=True)
class SensorEvent:
    kind: Literal["frame", "system"]
    frame: FrameSnapshot | None = None
    system_name: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetricSnapshot:
    pinch_strength: float
    grab_strength: float
    palm_position: Vector3
    palm_velocity: Vector3
    finger_count: int
    stillness_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pinch_strength": self.pinch_strength,
            "grab_strength": self.grab_strength,
            "palm_position": self.palm_position.to_dict(),
            "palm_velocity": self.palm_velocity.to_dict(),
            "finger_count": self.finger_count,
            "stillness_score": self.stillness_score,
        }


@dataclass(slots=True)
class InternalEvent:
    name: str
    timestamp: float
    hand: HandName
    phase: EventPhase = "instant"
    confidence: float = 1.0
    metrics: MetricSnapshot | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PublicEvent:
    name: str
    timestamp: float
    hand: HandName
    phase: EventPhase = "instant"
    confidence: float = 1.0
    metrics: MetricSnapshot | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "gesture_event",
            "event": self.name,
            "phase": self.phase,
            "hand": self.hand,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "metrics": None if self.metrics is None else self.metrics.to_dict(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class DebugSnapshot:
    timestamp: float
    controller_state: ControllerStateName
    active_gesture: str
    hand_present: bool
    hand: HandName
    pinch_strength: float
    grab_strength: float
    finger_count: int
    palm_speed: float
    palm_position: Vector3
    palm_velocity: Vector3
    pinch_started_at: float | None
    pinch_hold_emitted: bool
    open_palm_since: float | None
    open_palm_fired: bool

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "debug_metrics",
            "timestamp": self.timestamp,
            "controller_state": self.controller_state,
            "active_gesture": self.active_gesture,
            "hand_present": self.hand_present,
            "hand": self.hand,
            "pinch_strength": self.pinch_strength,
            "grab_strength": self.grab_strength,
            "finger_count": self.finger_count,
            "palm_speed": self.palm_speed,
            "palm_position": self.palm_position.to_dict(),
            "palm_velocity": self.palm_velocity.to_dict(),
            "pinch_started_at": self.pinch_started_at,
            "pinch_hold_emitted": self.pinch_hold_emitted,
            "open_palm_since": self.open_palm_since,
            "open_palm_fired": self.open_palm_fired,
        }


@dataclass(slots=True)
class VoiceContext:
    transcript_partial: str = ""
    transcript_final: str = ""
    options: list[str] = field(default_factory=list)
    session_active: bool = False

    @property
    def current_text(self) -> str:
        return self.transcript_final or self.transcript_partial

    def clear(self) -> None:
        self.transcript_partial = ""
        self.transcript_final = ""
        self.options = []
        self.session_active = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript_partial": self.transcript_partial,
            "transcript_final": self.transcript_final,
            "options": list(self.options),
            "session_active": self.session_active,
        }


@dataclass(slots=True)
class HudViewModel:
    visible: bool
    state: ControllerStateName
    title: str
    subtitle: str
    active_gesture: str = ""
    options: list[str] = field(default_factory=list)
    selection_index: int = 0

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "hud_state",
            "visible": self.visible,
            "state": self.state,
            "title": self.title,
            "subtitle": self.subtitle,
            "active_gesture": self.active_gesture,
            "options": list(self.options),
            "selection_index": self.selection_index,
        }


@dataclass(slots=True)
class ControllerSnapshot:
    state: ControllerStateName
    state_since: float
    selection_index: int
    active_gesture: str
    voice: VoiceContext

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "controller_state",
            "state": self.state,
            "state_since": self.state_since,
            "selection_index": self.selection_index,
            "active_gesture": self.active_gesture,
            "voice": self.voice.to_dict(),
        }
