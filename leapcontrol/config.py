from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def app_home() -> Path:
    env_home = os.environ.get("LEAPCONTROL_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / "Library" / "Application Support" / "LeapControl"


@dataclass(slots=True)
class ActionSpec:
    type: str
    command: str | None = None
    key: str | None = None
    modifiers: list[str] = field(default_factory=list)
    key_action: str = "tap"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActionSpec":
        return cls(
            type=str(payload["type"]),
            command=payload.get("command"),
            key=payload.get("key"),
            modifiers=list(payload.get("modifiers", [])),
            key_action=str(payload.get("key_action", "tap")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CalibrationProfile:
    active_hand_preference: str = "either"
    open_palm_min_fingers: int = 4
    open_palm_max_grab: float = 0.35
    pinch_start_threshold: float = 0.82
    pinch_release_threshold: float = 0.35
    grab_threshold: float = 0.78
    stillness_velocity_threshold: float = 65.0
    swipe_velocity_threshold: float = 220.0
    swipe_min_distance: float = 55.0
    wake_dwell_s: float = 0.75
    cancel_dwell_s: float = 0.55
    pinch_hold_dwell_s: float = 1.00
    pinch_tap_min_s: float = 0.03
    pinch_tap_max_s: float = 1.00
    swipe_cooldown_s: float = 0.60
    armed_timeout_s: float = 4.00
    flash_duration_s: float = 0.80

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CalibrationProfile":
        kwargs = asdict(cls())
        kwargs.update(payload)
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AppConfig:
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    overlay_enabled: bool = True
    tracking_mode: str = "desktop"
    profile_name: str = "default"
    routes: dict[str, list[ActionSpec]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppConfig":
        routes_payload = payload.get("routes", {})
        routes = {
            name: [ActionSpec.from_dict(item) for item in items]
            for name, items in routes_payload.items()
        }
        return cls(
            api_host=str(payload.get("api_host", "127.0.0.1")),
            api_port=int(payload.get("api_port", 8765)),
            overlay_enabled=bool(payload.get("overlay_enabled", True)),
            tracking_mode=str(payload.get("tracking_mode", "desktop")),
            profile_name=str(payload.get("profile_name", "default")),
            routes=routes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_host": self.api_host,
            "api_port": self.api_port,
            "overlay_enabled": self.overlay_enabled,
            "tracking_mode": self.tracking_mode,
            "profile_name": self.profile_name,
            "routes": {
                name: [item.to_dict() for item in items]
                for name, items in self.routes.items()
            },
        }


def ensure_directories() -> dict[str, Path]:
    home = app_home()
    dirs = {
        "home": home,
        "profiles": home / "profiles",
        "fixtures": home / "fixtures",
        "logs": home / "logs",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def config_path() -> Path:
    return ensure_directories()["home"] / "config.json"


def profile_path(name: str) -> Path:
    return ensure_directories()["profiles"] / f"{name}.json"


def fixture_root() -> Path:
    return ensure_directories()["fixtures"]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_app_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or config_path()
    if not cfg_path.exists():
        config = AppConfig(routes=default_routes())
        write_json(cfg_path, config.to_dict())
        return config
    config = AppConfig.from_dict(load_json(cfg_path))
    if not config.routes:
        config.routes = default_routes()
        write_json(cfg_path, config.to_dict())
    return config


def save_app_config(config: AppConfig, path: Path | None = None) -> Path:
    cfg_path = path or config_path()
    write_json(cfg_path, config.to_dict())
    return cfg_path


def default_routes() -> dict[str, list[ActionSpec]]:
    return {
        "confirm": [ActionSpec(type="key_event", key="return", key_action="tap")],
        "ptt_start": [ActionSpec(type="key_event", key="right_control", key_action="down")],
        "ptt_end": [ActionSpec(type="key_event", key="right_control", key_action="up")],
    }


def load_profile(name: str = "default") -> CalibrationProfile:
    path = profile_path(name)
    if not path.exists():
        profile = CalibrationProfile()
        write_json(path, profile.to_dict())
        return profile
    return CalibrationProfile.from_dict(load_json(path))


def save_profile(profile: CalibrationProfile, name: str = "default") -> Path:
    path = profile_path(name)
    write_json(path, profile.to_dict())
    return path
