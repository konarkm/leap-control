from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import ensure_directories


class JsonlLogger:
    def __init__(self, name: str = "events") -> None:
        log_dir = ensure_directories()["logs"]
        self.path = log_dir / f"{name}.jsonl"

    def log(self, record_type: str, payload: dict[str, Any]) -> None:
        entry = {
            "ts": time.time(),
            "record_type": record_type,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")))
            handle.write("\n")
