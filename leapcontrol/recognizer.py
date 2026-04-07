from __future__ import annotations

from dataclasses import dataclass

from .config import CalibrationProfile
from .models import DebugSnapshot, FrameSnapshot, HandMetrics, InternalEvent, MetricSnapshot, Vector3


@dataclass(slots=True)
class _PinchState:
    started_at: float | None = None
    hold_emitted: bool = False


class GestureRecognizer:
    def __init__(self, profile: CalibrationProfile):
        self.profile = profile
        self._hand_present = False
        self._open_palm_since: float | None = None
        self._open_palm_fired = False
        self._pinch = _PinchState()
        self._prev_frame: FrameSnapshot | None = None
        self._last_hand: HandMetrics | None = None
        self._last_timestamp: float = 0.0

    def process(self, frame: FrameSnapshot) -> list[InternalEvent]:
        events: list[InternalEvent] = []
        hand = self._select_hand(frame.hand)
        timestamp = frame.monotonic_time
        self._last_timestamp = timestamp
        self._last_hand = hand

        if hand is None:
            if self._hand_present:
                events.append(InternalEvent("hand_lost", timestamp, "unknown", phase="end"))
            self._hand_present = False
            self._open_palm_since = None
            self._open_palm_fired = False
            if self._pinch.started_at is not None and self._pinch.hold_emitted:
                events.append(
                    InternalEvent("pinch_hold_end", timestamp, "unknown", phase="end")
                )
            self._pinch = _PinchState()
            self._prev_frame = frame
            return events

        metrics = self._metric_snapshot(hand)
        if not self._hand_present:
            events.append(
                InternalEvent(
                    "hand_present",
                    timestamp,
                    hand.hand,
                    phase="start",
                    metrics=metrics,
                )
            )
        self._hand_present = True

        open_palm = self._is_open_palm(hand)
        if open_palm:
            if self._open_palm_since is None:
                self._open_palm_since = timestamp
                self._open_palm_fired = False
            dwell = timestamp - self._open_palm_since
            if dwell >= self.profile.wake_dwell_s and not self._open_palm_fired:
                events.append(
                    InternalEvent(
                        "open_palm_hold",
                        timestamp,
                        hand.hand,
                        metrics=metrics,
                        confidence=self._confidence_from_margin(
                            self.profile.stillness_velocity_threshold - hand.palm_speed,
                            self.profile.stillness_velocity_threshold,
                        ),
                    )
                )
                self._open_palm_fired = True
        else:
            self._open_palm_since = None
            self._open_palm_fired = False

        pinch_active = hand.pinch_strength >= self.profile.pinch_start_threshold
        pinch_released = hand.pinch_strength <= self.profile.pinch_release_threshold
        if pinch_active:
            if self._pinch.started_at is None:
                self._pinch.started_at = timestamp
                self._pinch.hold_emitted = False
            dwell = timestamp - self._pinch.started_at
            if dwell >= self.profile.pinch_hold_dwell_s and not self._pinch.hold_emitted:
                events.append(
                    InternalEvent(
                        "pinch_hold_start",
                        timestamp,
                        hand.hand,
                        phase="start",
                        metrics=metrics,
                    )
                )
                self._pinch.hold_emitted = True
        elif pinch_released and self._pinch.started_at is not None:
            duration = timestamp - self._pinch.started_at
            if self._pinch.hold_emitted:
                events.append(
                    InternalEvent(
                        "pinch_hold_end",
                        timestamp,
                        hand.hand,
                        phase="end",
                        metrics=metrics,
                    )
                )
            elif self.profile.pinch_tap_min_s <= duration <= self.profile.pinch_tap_max_s:
                events.append(
                    InternalEvent(
                        "pinch_tap",
                        timestamp,
                        hand.hand,
                        metrics=metrics,
                    )
                )
            self._pinch = _PinchState()

        self._prev_frame = frame
        return events

    def debug_snapshot(self) -> DebugSnapshot:
        hand = self._last_hand
        if hand is None:
            return DebugSnapshot(
                timestamp=self._last_timestamp,
                controller_state="idle",
                active_gesture="",
                hand_present=False,
                hand="unknown",
                pinch_strength=0.0,
                grab_strength=0.0,
                finger_count=0,
                palm_speed=0.0,
                palm_position=Vector3(0.0, 0.0, 0.0),
                palm_velocity=Vector3(0.0, 0.0, 0.0),
                pinch_started_at=self._pinch.started_at,
                pinch_hold_emitted=self._pinch.hold_emitted,
                open_palm_since=self._open_palm_since,
                open_palm_fired=self._open_palm_fired,
            )
        return DebugSnapshot(
            timestamp=self._last_timestamp,
            controller_state="idle",
            active_gesture="",
            hand_present=True,
            hand=hand.hand,
            pinch_strength=hand.pinch_strength,
            grab_strength=hand.grab_strength,
            finger_count=hand.finger_count,
            palm_speed=hand.palm_speed,
            palm_position=hand.palm_position,
            palm_velocity=hand.palm_velocity,
            pinch_started_at=self._pinch.started_at,
            pinch_hold_emitted=self._pinch.hold_emitted,
            open_palm_since=self._open_palm_since,
            open_palm_fired=self._open_palm_fired,
        )

    def _select_hand(self, hand: HandMetrics | None) -> HandMetrics | None:
        if hand is None:
            return None
        pref = self.profile.active_hand_preference
        if pref == "either" or hand.hand == pref:
            return hand
        return None

    def _metric_snapshot(self, hand: HandMetrics) -> MetricSnapshot:
        threshold = max(self.profile.stillness_velocity_threshold, 1.0)
        stillness_score = max(0.0, min(1.0, 1.0 - (hand.palm_speed / threshold)))
        return MetricSnapshot(
            pinch_strength=hand.pinch_strength,
            grab_strength=hand.grab_strength,
            palm_position=hand.palm_position,
            palm_velocity=hand.palm_velocity,
            finger_count=hand.finger_count,
            stillness_score=stillness_score,
        )

    def _is_open_palm(self, hand: HandMetrics) -> bool:
        return (
            hand.finger_count >= self.profile.open_palm_min_fingers
            and hand.grab_strength <= self.profile.open_palm_max_grab
            and hand.pinch_strength <= self.profile.pinch_release_threshold
            and hand.palm_speed <= self.profile.stillness_velocity_threshold
        )

    @staticmethod
    def _confidence_from_margin(margin: float, scale: float) -> float:
        if scale <= 0:
            return 1.0
        return max(0.0, min(1.0, margin / scale))
