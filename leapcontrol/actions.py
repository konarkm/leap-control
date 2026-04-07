from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Protocol

import Quartz

from .config import ActionSpec
from .models import PublicEvent


SPECIAL_KEY_CODES = {
    "fn": 63,
    "right_control": 62,
    "right_option": 61,
    "right_shift": 60,
    "right_command": 54,
    "space": 49,
    "return": 36,
    "tab": 48,
    "escape": 53,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "f5": 96,
}

KEY_SELF_FLAGS = {
    "fn": Quartz.kCGEventFlagMaskSecondaryFn,
    "right_control": Quartz.kCGEventFlagMaskControl,
    "right_option": Quartz.kCGEventFlagMaskAlternate,
    "right_shift": Quartz.kCGEventFlagMaskShift,
    "right_command": Quartz.kCGEventFlagMaskCommand,
}


class ActionRunner(Protocol):
    def execute_shell(self, command: str, event: PublicEvent) -> None: ...

    def execute_hotkey(self, key: str, modifiers: list[str], key_action: str = "tap") -> None: ...

    def execute_scroll(
        self,
        amount: float,
        *,
        axis: str = "vertical",
        natural: bool = True,
    ) -> None: ...


@dataclass(slots=True)
class SubprocessActionRunner:
    _scroll_remainder: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self._scroll_remainder is None:
            self._scroll_remainder = {"vertical": 0.0, "horizontal": 0.0}

    def execute_shell(self, command: str, event: PublicEvent) -> None:
        env = {
            **dict(os.environ),
            "LEAPCONTROL_EVENT_JSON": json.dumps(event.to_message()),
        }
        subprocess.run(
            ["/bin/zsh", "-lc", command],
            check=False,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def execute_hotkey(self, key: str, modifiers: list[str], key_action: str = "tap") -> None:
        keycode = SPECIAL_KEY_CODES.get(key)
        if keycode is None:
            raise ValueError(f"Unsupported key: {key}")
        modifier_flags = 0
        for modifier in modifiers:
            modifier_flags |= {
                "command": Quartz.kCGEventFlagMaskCommand,
                "shift": Quartz.kCGEventFlagMaskShift,
                "option": Quartz.kCGEventFlagMaskAlternate,
                "control": Quartz.kCGEventFlagMaskControl,
            }.get(modifier, 0)

        def post(down: bool) -> None:
            event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
            flags = modifier_flags
            if down:
                flags |= KEY_SELF_FLAGS.get(key, 0)
            Quartz.CGEventSetFlags(event, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

        if key_action == "tap":
            post(True)
            post(False)
        elif key_action == "down":
            post(True)
        elif key_action == "up":
            post(False)
        else:
            raise ValueError(f"Unsupported key_action: {key_action}")

    def execute_scroll(
        self,
        amount: float,
        *,
        axis: str = "vertical",
        natural: bool = True,
    ) -> None:
        if amount == 0:
            return
        signed_amount = -amount if natural else amount
        assert self._scroll_remainder is not None
        bucket = self._scroll_remainder.get(axis, 0.0) + signed_amount
        pixel_delta = int(bucket)
        self._scroll_remainder[axis] = bucket - pixel_delta
        if pixel_delta == 0:
            return
        if axis == "vertical":
            event = Quartz.CGEventCreateScrollWheelEvent(
                None,
                Quartz.kCGScrollEventUnitPixel,
                1,
                pixel_delta,
            )
            Quartz.CGEventSetIntegerValueField(event, Quartz.kCGScrollWheelEventPointDeltaAxis1, pixel_delta)
            Quartz.CGEventSetIntegerValueField(
                event,
                Quartz.kCGScrollWheelEventFixedPtDeltaAxis1,
                pixel_delta << 16,
            )
        elif axis == "horizontal":
            event = Quartz.CGEventCreateScrollWheelEvent(
                None,
                Quartz.kCGScrollEventUnitPixel,
                2,
                0,
                pixel_delta,
            )
            Quartz.CGEventSetIntegerValueField(event, Quartz.kCGScrollWheelEventPointDeltaAxis2, pixel_delta)
            Quartz.CGEventSetIntegerValueField(
                event,
                Quartz.kCGScrollWheelEventFixedPtDeltaAxis2,
                pixel_delta << 16,
            )
        else:
            raise ValueError(f"Unsupported scroll axis: {axis}")
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGScrollWheelEventIsContinuous, 1)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


class ActionRouter:
    def __init__(self, routes: dict[str, list[ActionSpec]], runner: ActionRunner | None = None):
        self.routes = routes
        self.runner = runner or SubprocessActionRunner()

    def route(self, event: PublicEvent) -> None:
        for action in self.routes.get(event.name, []):
            if action.type == "shell" and action.command:
                self.runner.execute_shell(action.command, event)
            elif action.type in {"hotkey", "key_event"} and action.key:
                self.runner.execute_hotkey(action.key, action.modifiers, action.key_action)
            elif action.type == "scroll_event":
                metadata = event.metadata or {}
                axis = metadata.get("axis")
                allowed_axes = {None, action.scroll_axis}
                if action.scroll_axis == "vertical":
                    allowed_axes.add("y")
                elif action.scroll_axis == "horizontal":
                    allowed_axes.add("x")
                if axis not in allowed_axes:
                    continue
                raw_delta = float(metadata.get("delta_value", 0.0))
                amount = raw_delta * action.scroll_scale
                if amount:
                    self.runner.execute_scroll(
                        amount,
                        axis=action.scroll_axis,
                        natural=action.scroll_natural,
                    )
