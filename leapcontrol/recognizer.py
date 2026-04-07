from __future__ import annotations

from dataclasses import dataclass

from .config import CalibrationProfile
from .models import DebugSnapshot, FrameSnapshot, HandMetrics, InternalEvent, MetricSnapshot, Vector3


@dataclass(slots=True)
class _PinchState:
    started_at: float | None = None
    hold_emitted: bool = False


@dataclass(slots=True)
class _DragState:
    anchor_position: Vector3 | None = None
    axis: str = ""
    last_emitted_direction: str = ""
    last_update_axis_value: float | None = None
    filtered_axis_value: float | None = None
    last_update_timestamp: float | None = None
    last_update_direction: str = ""


class GestureRecognizer:
    def __init__(self, profile: CalibrationProfile):
        self.profile = profile
        self._hand_present = False
        self._open_palm_since: float | None = None
        self._open_palm_fired = False
        self._pinch = _PinchState()
        self._drag = _DragState()
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
            self._drag = _DragState()
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
                self._drag.anchor_position = hand.palm_position
                self._drag.axis = ""
                self._drag.last_emitted_direction = ""
                self._drag.last_update_axis_value = None
                self._drag.filtered_axis_value = None
                self._drag.last_update_timestamp = timestamp
                self._drag.last_update_direction = ""
            if self._pinch.hold_emitted:
                self._update_drag_axis(hand)
                drag_event = self._maybe_emit_drag_direction(timestamp, hand, metrics)
                if drag_event is not None:
                    events.append(drag_event)
                drag_update = self._maybe_emit_drag_update(timestamp, hand, metrics)
                if drag_update is not None:
                    events.append(drag_update)
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
            self._drag = _DragState()

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
                drag_active=False,
                drag_axis="",
                drag_direction="",
                drag_anchor_position=Vector3(0.0, 0.0, 0.0),
                drag_delta=Vector3(0.0, 0.0, 0.0),
                drag_axis_value=0.0,
            )
        drag_anchor = self._drag.anchor_position or hand.palm_position
        drag_delta = Vector3(
            hand.palm_position.x - drag_anchor.x,
            hand.palm_position.y - drag_anchor.y,
            hand.palm_position.z - drag_anchor.z,
        )
        drag_axis_value = 0.0
        drag_direction = ""
        if self._drag.axis == "x":
            drag_axis_value = drag_delta.x
            if abs(drag_axis_value) >= self.profile.drag_deadzone_mm:
                drag_direction = "right" if drag_axis_value > 0 else "left"
        elif self._drag.axis == "y":
            drag_axis_value = drag_delta.y
            if abs(drag_axis_value) >= self.profile.drag_deadzone_mm:
                drag_direction = "up" if drag_axis_value > 0 else "down"
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
            drag_active=self._pinch.hold_emitted and self._drag.anchor_position is not None,
            drag_axis=self._drag.axis,
            drag_direction=drag_direction,
            drag_anchor_position=drag_anchor,
            drag_delta=drag_delta,
            drag_axis_value=drag_axis_value,
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

    def _update_drag_axis(self, hand: HandMetrics) -> None:
        if self._drag.anchor_position is None or self._drag.axis:
            return
        delta_x = hand.palm_position.x - self._drag.anchor_position.x
        delta_y = hand.palm_position.y - self._drag.anchor_position.y
        abs_x = abs(delta_x)
        abs_y = abs(delta_y)
        leading = max(abs_x, abs_y)
        if leading < self.profile.drag_deadzone_mm:
            return
        ratio = max(self.profile.drag_axis_lock_ratio, 1.0)
        if abs_x >= abs_y * ratio:
            self._drag.axis = "x"
            self._drag.last_update_axis_value = delta_x
            self._drag.filtered_axis_value = delta_x
        elif abs_y >= abs_x * ratio:
            self._drag.axis = "y"
            self._drag.last_update_axis_value = delta_y
            self._drag.filtered_axis_value = delta_y

    def _maybe_emit_drag_direction(
        self,
        timestamp: float,
        hand: HandMetrics,
        metrics: MetricSnapshot,
    ) -> InternalEvent | None:
        if self._drag.anchor_position is None or not self._drag.axis:
            return None
        delta_x = hand.palm_position.x - self._drag.anchor_position.x
        delta_y = hand.palm_position.y - self._drag.anchor_position.y
        axis_value = delta_x if self._drag.axis == "x" else delta_y
        if abs(axis_value) < self.profile.drag_deadzone_mm:
            return None
        direction = ""
        if self._drag.axis == "x":
            direction = "right" if axis_value > 0 else "left"
        elif self._drag.axis == "y":
            direction = "up" if axis_value > 0 else "down"
        if not direction or direction == self._drag.last_emitted_direction:
            return None
        self._drag.last_emitted_direction = direction
        return InternalEvent(
            "pinch_drag_direction",
            timestamp,
            hand.hand,
            phase="update",
            metrics=metrics,
            metadata={
                "axis": self._drag.axis,
                "direction": direction,
                "axis_value": axis_value,
                "delta": {
                    "x": delta_x,
                    "y": delta_y,
                    "z": hand.palm_position.z - self._drag.anchor_position.z,
                },
            },
        )

    def _maybe_emit_drag_update(
        self,
        timestamp: float,
        hand: HandMetrics,
        metrics: MetricSnapshot,
    ) -> InternalEvent | None:
        if self._drag.anchor_position is None or not self._drag.axis:
            return None
        raw_axis_value = (
            hand.palm_position.x - self._drag.anchor_position.x
            if self._drag.axis == "x"
            else hand.palm_position.y - self._drag.anchor_position.y
        )
        filtered = self._drag.filtered_axis_value
        if filtered is None:
            filtered = raw_axis_value
        else:
            alpha = max(0.0, min(1.0, self.profile.drag_smoothing_alpha))
            filtered = filtered + alpha * (raw_axis_value - filtered)
        self._drag.filtered_axis_value = filtered
        last_value = self._drag.last_update_axis_value
        if last_value is None:
            self._drag.last_update_axis_value = filtered
            self._drag.last_update_timestamp = timestamp
            return None
        if (
            self._drag.last_update_timestamp is not None
            and timestamp - self._drag.last_update_timestamp < self.profile.drag_update_min_interval_s
        ):
            return None
        delta_value = filtered - last_value
        if abs(delta_value) < self.profile.drag_update_step_mm:
            return None
        direction = ""
        if self._drag.axis == "x":
            direction = "right" if delta_value > 0 else "left"
        else:
            direction = "up" if delta_value > 0 else "down"
        if (
            self._drag.last_update_direction
            and direction != self._drag.last_update_direction
            and abs(delta_value) < self.profile.drag_reverse_deadzone_mm
        ):
            return None
        max_delta = max(self.profile.drag_max_delta_mm, self.profile.drag_update_step_mm)
        if abs(delta_value) > max_delta:
            delta_value = max_delta if delta_value > 0 else -max_delta
        self._drag.last_update_axis_value = last_value + delta_value
        self._drag.last_update_timestamp = timestamp
        self._drag.last_update_direction = direction
        return InternalEvent(
            "pinch_drag_update",
            timestamp,
            hand.hand,
            phase="update",
            metrics=metrics,
            metadata={
                "axis": self._drag.axis,
                "direction": direction,
                "axis_value": filtered,
                "delta_value": delta_value,
            },
        )

    @staticmethod
    def _confidence_from_margin(margin: float, scale: float) -> float:
        if scale <= 0:
            return 1.0
        return max(0.0, min(1.0, margin / scale))
