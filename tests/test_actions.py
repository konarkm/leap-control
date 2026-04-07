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


if __name__ == "__main__":
    unittest.main()
