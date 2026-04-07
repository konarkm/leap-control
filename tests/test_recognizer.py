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

if __name__ == "__main__":
    unittest.main()
