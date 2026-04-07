from __future__ import annotations

import unittest

from leapcontrol.config import CalibrationProfile
from leapcontrol.models import InternalEvent
from leapcontrol.state_machine import InteractionStateMachine

from test_helpers import metric_snapshot


def make_internal(name: str, t: float) -> InternalEvent:
    return InternalEvent(name=name, timestamp=t, hand="right", metrics=metric_snapshot())


class StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.machine = InteractionStateMachine(CalibrationProfile())
        self.machine.seed("idle", 0.0)

    def test_wake_to_armed(self) -> None:
        events = self.machine.handle_internal(make_internal("pinch_tap", 1.0))
        self.assertEqual(self.machine.state, "confirmed")
        self.assertEqual([event.name for event in events], ["confirm"])

    def test_listening_to_preview(self) -> None:
        self.machine.seed("idle", 0.0)
        start = self.machine.handle_internal(make_internal("pinch_hold_start", 0.1))
        self.assertEqual(self.machine.state, "listening")
        self.assertEqual(start[0].name, "ptt_start")

        self.machine.handle_voice_update({"status": "partial", "text": "hello world"}, 0.2)
        end = self.machine.handle_internal(make_internal("pinch_hold_end", 0.3))
        self.assertEqual(self.machine.state, "idle")
        self.assertEqual(end[0].name, "ptt_end")

    def test_confirm_from_preview(self) -> None:
        self.machine.seed("idle", 0.0)
        events = self.machine.handle_internal(make_internal("pinch_tap", 0.5))
        self.assertEqual(events[0].name, "confirm")
        self.assertEqual(self.machine.state, "confirmed")

    def test_cancel_from_preview(self) -> None:
        self.machine.seed("confirmed", 0.0, voice={"transcript_partial": "draft"})
        changed = self.machine.handle_tick(1.0)
        self.assertTrue(changed)
        self.assertEqual(self.machine.state, "idle")

    def test_cycle_in_preview(self) -> None:
        self.machine.seed("listening", 0.0)
        events = self.machine.handle_internal(make_internal("pinch_tap", 0.4))
        self.assertEqual(events, [])

    def test_drag_direction_passthrough_while_listening(self) -> None:
        self.machine.seed("listening", 0.0)
        event = make_internal("pinch_drag_direction", 0.4)
        event.metadata = {"direction": "right", "axis": "x", "axis_value": 42.0}
        events = self.machine.handle_internal(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "drag_direction")
        self.assertEqual(events[0].metadata["direction"], "right")

    def test_drag_update_passthrough_while_listening(self) -> None:
        self.machine.seed("listening", 0.0)
        event = make_internal("pinch_drag_update", 0.4)
        event.metadata = {"direction": "up", "axis": "y", "axis_value": 52.0, "delta_value": 11.0}
        events = self.machine.handle_internal(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "drag_update")
        self.assertEqual(events[0].metadata["delta_value"], 11.0)


if __name__ == "__main__":
    unittest.main()
