from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .actions import ActionRouter
from .api import LocalApiServer
from .config import AppConfig, CalibrationProfile
from .logging_utils import JsonlLogger
from .models import DebugSnapshot, PublicEvent
from .overlay import BaseHud, NullHud, TkHudOverlay
from .replay import load_fixture
from .recognizer import GestureRecognizer
from .sensor import LiveSensor, ReplaySensor
from .state_machine import InteractionStateMachine


class LeapControlController:
    def __init__(
        self,
        config: AppConfig,
        profile: CalibrationProfile,
        *,
        overlay: BaseHud | None = None,
        sensor: LiveSensor | ReplaySensor | None = None,
        router: ActionRouter | None = None,
    ):
        self.config = config
        self.profile = profile
        self.recognizer = GestureRecognizer(profile)
        self.machine = InteractionStateMachine(profile)
        self.overlay = overlay if overlay is not None else self._build_overlay()
        self.sensor = sensor if sensor is not None else LiveSensor(config.tracking_mode)
        self.router = router or ActionRouter(config.routes)
        self.logger = JsonlLogger()
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.api = LocalApiServer(
            config.api_host,
            config.api_port,
            self._queue_message,
            snapshot_provider=self._snapshot_messages,
        )
        self._last_state_payload: dict[str, Any] | None = None
        self._last_hud_payload: dict[str, Any] | None = None
        self._last_debug_payload: dict[str, Any] | None = None
        self._running = False

    async def run(self) -> None:
        self._running = True
        await self.api.start()
        try:
            await self._loop()
        finally:
            self._running = False
            await self.api.stop()
            self.overlay.close()
            close = getattr(self.sensor, "close", None)
            if callable(close):
                close()

    async def run_fixture(self, fixture_path: Path) -> list[dict[str, Any]]:
        metadata, frames, _expected = load_fixture(fixture_path)
        self.sensor = ReplaySensor(frames)
        if frames:
            self.machine.seed(
                metadata.get("initial_state", "idle"),
                frames[0].monotonic_time,
                voice=metadata.get("voice"),
                selection_index=int(metadata.get("selection_index", 0)),
            )
        public_messages: list[dict[str, Any]] = []
        while True:
            event = await self.sensor.next_event()
            if event is None:
                break
            public_messages.extend(await self._process_sensor_event(event))
        return public_messages

    async def _loop(self) -> None:
        while self._running:
            await self._drain_messages()
            event = await self.sensor.next_event(timeout_ms=25)
            if event is not None:
                await self._process_sensor_event(event)
            if self.machine.handle_tick(asyncio.get_running_loop().time()):
                await self._emit_state()

    async def _process_sensor_event(self, event) -> list[dict[str, Any]]:
        outbound: list[dict[str, Any]] = []
        if event.kind == "system":
            payload = {"type": "system_event", "event": event.system_name, "payload": event.payload}
            self.logger.log("system_event", payload)
            outbound.append(payload)
            await self.api.broadcast(payload)
            return outbound

        frame = event.frame
        assert frame is not None
        self.logger.log("frame", frame.to_dict())
        for internal_event in self.recognizer.process(frame):
            self.logger.log(
                "internal_event",
                {
                    "name": internal_event.name,
                    "timestamp": internal_event.timestamp,
                    "hand": internal_event.hand,
                    "phase": internal_event.phase,
                    "confidence": internal_event.confidence,
                    "metrics": None if internal_event.metrics is None else internal_event.metrics.to_dict(),
                    "metadata": internal_event.metadata,
                },
            )
            public_events = self.machine.handle_internal(internal_event)
            for public_event in public_events:
                payload = public_event.to_message()
                self.logger.log("public_event", payload)
                outbound.append(payload)
                await self.api.broadcast(payload)
                self.router.route(public_event)
        await self._emit_state()
        return outbound

    async def _queue_message(self, payload: dict[str, Any]) -> None:
        await self._message_queue.put(payload)

    async def _drain_messages(self) -> None:
        while not self._message_queue.empty():
            payload = await self._message_queue.get()
            await self._handle_inbound_message(payload)

    async def _handle_inbound_message(self, payload: dict[str, Any]) -> None:
        kind = payload.get("type")
        now = asyncio.get_running_loop().time()
        if kind == "voice_state":
            self.machine.handle_voice_update(payload, now)
            await self._emit_state()
        elif kind == "debug_command":
            command = payload.get("command")
            if command == "seed_state":
                self.machine.seed(
                    payload.get("state", "idle"),
                    now,
                    voice=payload.get("voice"),
                    selection_index=int(payload.get("selection_index", 0)),
                )
                await self._emit_state()

    async def _emit_state(self) -> None:
        snapshot = self.machine.snapshot()
        state_payload = snapshot.to_message()
        if state_payload != self._last_state_payload:
            self._last_state_payload = state_payload
            self.logger.log("controller_state", state_payload)
            await self.api.broadcast(state_payload)

        hud = self.machine.hud_model()
        self.overlay.update(hud)
        hud_payload = hud.to_message()
        if hud_payload != self._last_hud_payload:
            self._last_hud_payload = hud_payload
            self.logger.log("hud_state", hud_payload)
            await self.api.broadcast(hud_payload)

        debug_payload = self._build_debug_payload(snapshot.state, snapshot.active_gesture)
        if debug_payload != self._last_debug_payload:
            self._last_debug_payload = debug_payload
            self.logger.log("debug_metrics", debug_payload)
            await self.api.broadcast(debug_payload)

    def _snapshot_messages(self) -> list[dict[str, Any]]:
        snapshot = self.machine.snapshot()
        messages = [
            snapshot.to_message(),
            self.machine.hud_model().to_message(),
            self._build_debug_payload(snapshot.state, snapshot.active_gesture),
        ]
        return messages

    def _build_overlay(self) -> BaseHud:
        if self.config.overlay_enabled:
            return TkHudOverlay()
        return NullHud()

    def _build_debug_payload(self, controller_state: str, active_gesture: str) -> dict[str, Any]:
        debug = self.recognizer.debug_snapshot()
        debug.controller_state = controller_state
        debug.active_gesture = active_gesture
        return debug.to_message()
