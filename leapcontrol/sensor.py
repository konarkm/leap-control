from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any
import subprocess

from .models import FrameSnapshot, SensorEvent


class LiveSensor:
    def __init__(self, tracking_mode: str = "desktop"):
        self._tracking_mode = tracking_mode
        self._proc: asyncio.subprocess.Process | None = None
        self._helper_path = Path(__file__).resolve().parents[1] / "build" / "leap_stream_helper"
        self._helper_source = Path(__file__).resolve().parents[1] / "src" / "leap_stream_helper.c"
        self._build_script = Path(__file__).resolve().parents[1] / "scripts" / "build_stream_helper.sh"

    def open(self) -> None:
        return

    async def _ensure_process(self) -> None:
        if self._proc is not None:
            return
        self._ensure_helper()
        self._proc = await asyncio.create_subprocess_exec(
            str(self._helper_path),
            "--tracking-mode",
            self._tracking_mode,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def next_event(self, timeout_ms: int = 50) -> SensorEvent | None:
        await self._ensure_process()
        assert self._proc is not None and self._proc.stdout is not None
        try:
            raw = await asyncio.wait_for(
                self._proc.stdout.readline(),
                timeout=max(timeout_ms / 1000.0, 0.01),
            )
        except TimeoutError:
            return None
        if not raw:
            return None
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("type") == "frame":
            frame = FrameSnapshot.from_dict(payload)
            frame.monotonic_time = time.monotonic()
            return SensorEvent(
                kind="frame",
                frame=frame,
            )
        return SensorEvent(
            kind="system",
            system_name=payload.get("event"),
            payload=payload.get("payload", {}),
        )

    def close(self) -> None:
        if self._proc is None:
            return
        self._proc.terminate()
        self._proc = None

    def _ensure_helper(self) -> None:
        if (
            not self._helper_path.exists()
            or self._helper_path.stat().st_mtime < self._helper_source.stat().st_mtime
        ):
            subprocess.run(
                ["/bin/zsh", str(self._build_script)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


class ReplaySensor:
    def __init__(self, frames: list[FrameSnapshot], realtime: bool = False):
        self._frames = list(frames)
        self._index = 0
        self._realtime = realtime

    async def next_event(self, timeout_ms: int = 0) -> SensorEvent | None:
        del timeout_ms
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        if self._realtime and self._index < len(self._frames):
            next_frame = self._frames[self._index]
            await asyncio.sleep(max(0.0, next_frame.monotonic_time - frame.monotonic_time))
        return SensorEvent(kind="frame", frame=frame)


def load_frames_from_fixture(path: Path) -> tuple[dict[str, Any], list[FrameSnapshot]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    frames = [FrameSnapshot.from_dict(item) for item in payload.get("frames", [])]
    return payload.get("metadata", {}), frames
