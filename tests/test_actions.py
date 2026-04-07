from __future__ import annotations

import unittest

from leapcontrol.actions import ActionRouter
from leapcontrol.config import ActionSpec
from leapcontrol.models import PublicEvent

from test_helpers import metric_snapshot


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute_shell(self, command: str, event: PublicEvent) -> None:
        self.calls.append(("shell", (command, event.name)))

    def execute_hotkey(self, key: str, modifiers: list[str], key_action: str = "tap") -> None:
        self.calls.append(("hotkey", (key, tuple(modifiers), key_action)))

    def execute_scroll(self, amount: float, *, axis: str = "vertical", natural: bool = True) -> None:
        self.calls.append(("scroll", (round(amount, 3), axis, natural)))


class ActionRouterTests(unittest.TestCase):
    def test_routes_shell_and_hotkey(self) -> None:
        runner = FakeRunner()
        router = ActionRouter(
            {
                "confirm": [
                    ActionSpec(type="shell", command="echo confirm"),
                    ActionSpec(type="hotkey", key="space", modifiers=["command"]),
                ]
            },
            runner=runner,
        )
        router.route(
            PublicEvent(
                name="confirm",
                timestamp=1.0,
                hand="right",
                metrics=metric_snapshot(),
            )
        )
        self.assertEqual(
            runner.calls,
            [
                ("shell", ("echo confirm", "confirm")),
                ("hotkey", ("space", ("command",), "tap")),
            ],
        )

    def test_routes_vertical_drag_update_to_scroll(self) -> None:
        runner = FakeRunner()
        router = ActionRouter(
            {
                "drag_update": [
                    ActionSpec(type="scroll_event", scroll_axis="vertical", scroll_scale=0.4, scroll_natural=True)
                ]
            },
            runner=runner,
        )
        router.route(
            PublicEvent(
                name="drag_update",
                timestamp=1.0,
                hand="left",
                phase="update",
                metrics=metric_snapshot(),
                metadata={"axis": "y", "direction": "up", "axis_value": 48.0, "delta_value": 12.5},
            )
        )
        self.assertEqual(runner.calls, [("scroll", (5.0, "vertical", True))])


if __name__ == "__main__":
    unittest.main()
