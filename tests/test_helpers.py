from __future__ import annotations

from leapcontrol.models import FrameSnapshot, HandMetrics, MetricSnapshot, Vector3


def make_hand(
    *,
    hand: str = "right",
    pinch: float = 0.0,
    grab: float = 0.0,
    x: float = 0.0,
    y: float = 220.0,
    z: float = 120.0,
    vx: float = 0.0,
    vy: float = 0.0,
    vz: float = 0.0,
    fingers: int = 5,
) -> HandMetrics:
    return HandMetrics(
        hand=hand,
        confidence=1.0,
        flags=0,
        pinch_strength=pinch,
        pinch_distance=20.0,
        grab_strength=grab,
        grab_angle=0.0,
        finger_count=fingers,
        visible_time_us=1_000_000,
        palm_position=Vector3(x, y, z),
        palm_velocity=Vector3(vx, vy, vz),
        palm_normal=Vector3(0.0, -1.0, 0.0),
        palm_direction=Vector3(0.0, 0.0, -1.0),
        palm_width=80.0,
    )


def make_frame(
    t: float,
    *,
    hand: HandMetrics | None,
    frame_id: int = 1,
    tracking_frame_id: int = 1,
) -> FrameSnapshot:
    return FrameSnapshot(
        monotonic_time=t,
        service_timestamp_us=int(t * 1_000_000),
        frame_id=frame_id,
        tracking_frame_id=tracking_frame_id,
        framerate=115.0,
        device_id=1,
        hand=hand,
    )


def metric_snapshot() -> MetricSnapshot:
    return MetricSnapshot(
        pinch_strength=0.9,
        grab_strength=0.1,
        palm_position=Vector3(0.0, 220.0, 120.0),
        palm_velocity=Vector3(0.0, 0.0, 0.0),
        finger_count=5,
        stillness_score=1.0,
    )
