from __future__ import annotations

import unittest

from leapcontrol.config import CalibrationProfile
from leapcontrol.recognizer import GestureRecognizer

from test_helpers import make_frame, make_hand


class RecognizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = CalibrationProfile(
            wake_dwell_s=0.5,
            cancel_dwell_s=0.5,
            pinch_hold_dwell_s=0.2,
            pinch_tap_max_s=0.2,
        )
        self.recognizer = GestureRecognizer(self.profile)

    def test_wake_open_palm_hold(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand()),
            make_frame(0.2, hand=make_hand()),
            make_frame(0.6, hand=make_hand()),
        ]
        names = []
        for frame in frames:
            names.extend(event.name for event in self.recognizer.process(frame))
        self.assertEqual(names, ["hand_present", "open_palm_hold"])

    def test_pinch_hold_start_and_end(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand(pinch=0.9, fingers=2)),
            make_frame(0.25, hand=make_hand(pinch=0.9, fingers=2)),
            make_frame(0.35, hand=make_hand(pinch=0.1, fingers=5)),
        ]
        names = []
        for frame in frames:
            names.extend(event.name for event in self.recognizer.process(frame))
        self.assertIn("pinch_hold_start", names)
        self.assertIn("pinch_hold_end", names)

    def test_pinch_tap(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand(pinch=0.9, fingers=2)),
            make_frame(0.10, hand=make_hand(pinch=0.2, fingers=5)),
        ]
        names = []
        for frame in frames:
            names.extend(event.name for event in self.recognizer.process(frame))
        self.assertIn("pinch_tap", names)

    def test_pinch_drag_debug_locks_to_horizontal_axis(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand(pinch=0.9, fingers=2, x=10.0, y=220.0)),
            make_frame(0.25, hand=make_hand(pinch=0.9, fingers=2, x=10.0, y=220.0)),
            make_frame(0.35, hand=make_hand(pinch=0.9, fingers=2, x=46.0, y=226.0)),
        ]
        for frame in frames:
            self.recognizer.process(frame)
        snapshot = self.recognizer.debug_snapshot()
        self.assertTrue(snapshot.drag_active)
        self.assertEqual(snapshot.drag_axis, "x")
        self.assertEqual(snapshot.drag_direction, "right")
        self.assertAlmostEqual(snapshot.drag_delta.x, 36.0)
        self.assertAlmostEqual(snapshot.drag_delta.y, 6.0)

    def test_pinch_drag_debug_labels_vertical_direction(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand(pinch=0.9, fingers=2, x=0.0, y=220.0)),
            make_frame(0.25, hand=make_hand(pinch=0.9, fingers=2, x=0.0, y=220.0)),
            make_frame(0.35, hand=make_hand(pinch=0.9, fingers=2, x=4.0, y=258.0)),
        ]
        for frame in frames:
            self.recognizer.process(frame)
        snapshot = self.recognizer.debug_snapshot()
        self.assertEqual(snapshot.drag_axis, "y")
        self.assertEqual(snapshot.drag_direction, "up")

    def test_pinch_drag_direction_event_emits_once_for_locked_axis(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand(pinch=0.9, fingers=2, x=0.0, y=220.0)),
            make_frame(0.25, hand=make_hand(pinch=0.9, fingers=2, x=0.0, y=220.0)),
            make_frame(0.35, hand=make_hand(pinch=0.9, fingers=2, x=42.0, y=224.0)),
            make_frame(0.45, hand=make_hand(pinch=0.9, fingers=2, x=54.0, y=226.0)),
        ]
        names = []
        drag_events = []
        for frame in frames:
            events = self.recognizer.process(frame)
            names.extend(event.name for event in events)
            drag_events.extend(event for event in events if event.name == "pinch_drag_direction")
        self.assertIn("pinch_hold_start", names)
        self.assertEqual(len(drag_events), 1)
        self.assertEqual(drag_events[0].metadata["direction"], "right")
        self.assertEqual(drag_events[0].metadata["axis"], "x")

    def test_pinch_drag_update_emits_incremental_vertical_delta(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand(pinch=0.9, fingers=2, x=0.0, y=220.0)),
            make_frame(0.25, hand=make_hand(pinch=0.9, fingers=2, x=0.0, y=220.0)),
            make_frame(0.35, hand=make_hand(pinch=0.9, fingers=2, x=2.0, y=258.0)),
            make_frame(0.45, hand=make_hand(pinch=0.9, fingers=2, x=3.0, y=272.0)),
        ]
        drag_updates = []
        for frame in frames:
            drag_updates.extend(
                event for event in self.recognizer.process(frame) if event.name == "pinch_drag_update"
            )
        self.assertEqual(len(drag_updates), 1)
        self.assertEqual(drag_updates[0].metadata["axis"], "y")
        self.assertEqual(drag_updates[0].metadata["direction"], "up")
        self.assertAlmostEqual(drag_updates[0].metadata["delta_value"], 3.0)

    def test_pinch_drag_resets_after_release(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand(pinch=0.9, fingers=2, x=0.0, y=220.0)),
            make_frame(0.25, hand=make_hand(pinch=0.9, fingers=2, x=0.0, y=220.0)),
            make_frame(0.35, hand=make_hand(pinch=0.9, fingers=2, x=40.0, y=220.0)),
            make_frame(0.45, hand=make_hand(pinch=0.1, fingers=5, x=42.0, y=220.0)),
        ]
        for frame in frames:
            self.recognizer.process(frame)
        snapshot = self.recognizer.debug_snapshot()
        self.assertFalse(snapshot.drag_active)
        self.assertEqual(snapshot.drag_axis, "")
        self.assertEqual(snapshot.drag_direction, "")

if __name__ == "__main__":
    unittest.main()
