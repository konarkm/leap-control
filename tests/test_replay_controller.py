from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from leapcontrol.config import AppConfig, CalibrationProfile
from leapcontrol.controller import LeapControlController
from leapcontrol.overlay import NullHud

from test_helpers import make_frame, make_hand


class ReplayControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_fixture_emits_wake(self) -> None:
        frames = [
            make_frame(0.0, hand=make_hand()),
            make_frame(0.2, hand=make_hand()),
            make_frame(0.8, hand=make_hand()),
        ]
        payload = {
            "metadata": {"name": "wake_fixture", "initial_state": "idle"},
            "frames": [frame.to_dict() for frame in frames],
            "expected_public_events": [{"event": "wake"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "fixture.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            controller = LeapControlController(
                AppConfig(overlay_enabled=False),
                CalibrationProfile(wake_dwell_s=0.6),
                overlay=NullHud(),
            )
            messages = await controller.run_fixture(path)
        gesture_messages = [message for message in messages if message.get("type") == "gesture_event"]
        self.assertEqual([message["event"] for message in gesture_messages], ["hand_present"])


if __name__ == "__main__":
    unittest.main()
