from __future__ import annotations

from typing import Any

from .config import CalibrationProfile
from .models import (
    ControllerSnapshot,
    ControllerStateName,
    HudViewModel,
    InternalEvent,
    PublicEvent,
    VoiceContext,
)


class InteractionStateMachine:
    def __init__(self, profile: CalibrationProfile):
        self.profile = profile
        self.state: ControllerStateName = "idle"
        self.state_since = 0.0
        self.selection_index = 0
        self.active_gesture = ""
        self.voice = VoiceContext()

    def seed(
        self,
        state: ControllerStateName,
        now: float,
        voice: dict[str, Any] | None = None,
        selection_index: int = 0,
    ) -> None:
        self.state = state
        self.state_since = now
        self.selection_index = selection_index
        self.active_gesture = ""
        self.voice.clear()
        if voice:
            self.voice.transcript_partial = str(voice.get("transcript_partial", ""))
            self.voice.transcript_final = str(voice.get("transcript_final", ""))
            self.voice.options = list(voice.get("options", []))
            self.voice.session_active = bool(voice.get("session_active", False))

    def snapshot(self) -> ControllerSnapshot:
        return ControllerSnapshot(
            state=self.state,
            state_since=self.state_since,
            selection_index=self.selection_index,
            active_gesture=self.active_gesture,
            voice=self.voice,
        )

    def handle_internal(self, event: InternalEvent) -> list[PublicEvent]:
        self.active_gesture = event.name
        output: list[PublicEvent] = []
        if event.name == "hand_present":
            output.append(self._public("hand_present", event))
            return output
        if event.name == "hand_lost":
            output.append(self._public("hand_lost", event))
            return output

        if self.state == "idle" and event.name == "pinch_tap":
            output.append(self._public("confirm", event))
            self._transition("confirmed", event.timestamp)
            return output

        if self.state == "idle" and event.name == "pinch_hold_start":
            self._transition("listening", event.timestamp)
            self.voice.session_active = True
            output.append(self._public("ptt_start", event, phase="start"))
            return output

        if self.state == "listening" and event.name == "pinch_hold_end":
            output.append(self._public("ptt_end", event, phase="end"))
            self.voice.session_active = False
            self.voice.clear()
            self.selection_index = 0
            self._transition("idle", event.timestamp)
            return output

        return output

    def handle_voice_update(self, payload: dict[str, Any], now: float) -> None:
        status = str(payload.get("status", "")).lower()
        text = str(payload.get("text", ""))
        options = payload.get("options")
        if status == "session_started":
            self.voice.session_active = True
            return
        if status == "partial":
            self.voice.transcript_partial = text
        elif status == "final":
            self.voice.transcript_final = text
            self.voice.transcript_partial = text
        elif status == "cancelled":
            self.voice.clear()
            if self.state in {"armed", "listening", "preview"}:
                self._transition("cancelled", now)
        if options is not None:
            self.voice.options = [str(item) for item in options]
            if self.voice.options:
                self.selection_index %= len(self.voice.options)
            else:
                self.selection_index = 0

    def handle_tick(self, now: float) -> bool:
        if self.state == "armed" and now - self.state_since >= self.profile.armed_timeout_s:
            self.voice.clear()
            self.selection_index = 0
            self._transition("idle", now)
            return True
        if self.state in {"confirmed", "cancelled"} and now - self.state_since >= self.profile.flash_duration_s:
            self._transition("idle", now)
            return True
        return False

    def hud_model(self) -> HudViewModel:
        if self.state == "idle":
            return HudViewModel(False, "idle", "", "")
        title_map = {
            "listening": "Listening",
            "confirmed": "Confirmed",
        }
        subtitle = ""
        if self.state == "listening":
            subtitle = self.voice.current_text or "Listening for transcript updates..."
        elif self.state == "confirmed":
            subtitle = "Pinch tap sent Enter."
        return HudViewModel(
            visible=True,
            state=self.state,
            title=title_map[self.state],
            subtitle=subtitle,
            active_gesture=self.active_gesture,
            options=list(self.voice.options),
            selection_index=self.selection_index,
        )

    def _public(
        self,
        name: str,
        event: InternalEvent,
        *,
        phase: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PublicEvent:
        return PublicEvent(
            name=name,
            timestamp=event.timestamp,
            hand=event.hand,
            phase=phase or event.phase,
            confidence=event.confidence,
            metrics=event.metrics,
            metadata=metadata or {},
        )

    def _transition(self, state: ControllerStateName, now: float) -> None:
        self.state = state
        self.state_since = now
