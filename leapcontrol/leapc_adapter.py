from __future__ import annotations

import ctypes as ct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import FrameSnapshot, HandMetrics, SensorEvent, Vector3


LEAP_SDK_ROOT = Path("/Applications/Ultraleap Hand Tracking.app/Contents/LeapSDK")
LEAP_LIB_PATH = LEAP_SDK_ROOT / "lib" / "libLeapC.dylib"


class LeapError(RuntimeError):
    pass


class LEAP_VECTOR(ct.Structure):
    _pack_ = 1
    _fields_ = [("x", ct.c_float), ("y", ct.c_float), ("z", ct.c_float)]


class LEAP_QUATERNION(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("x", ct.c_float),
        ("y", ct.c_float),
        ("z", ct.c_float),
        ("w", ct.c_float),
    ]


class LEAP_BONE(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("prev_joint", LEAP_VECTOR),
        ("next_joint", LEAP_VECTOR),
        ("width", ct.c_float),
        ("rotation", LEAP_QUATERNION),
    ]


class LEAP_DIGIT(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("finger_id", ct.c_int32),
        ("bones", LEAP_BONE * 4),
        ("is_extended", ct.c_uint32),
    ]


class LEAP_PALM(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("position", LEAP_VECTOR),
        ("stabilized_position", LEAP_VECTOR),
        ("velocity", LEAP_VECTOR),
        ("normal", LEAP_VECTOR),
        ("width", ct.c_float),
        ("direction", LEAP_VECTOR),
        ("orientation", LEAP_QUATERNION),
    ]


class LEAP_HAND(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("id", ct.c_uint32),
        ("flags", ct.c_uint32),
        ("type", ct.c_int32),
        ("confidence", ct.c_float),
        ("visible_time", ct.c_uint64),
        ("pinch_distance", ct.c_float),
        ("grab_angle", ct.c_float),
        ("pinch_strength", ct.c_float),
        ("grab_strength", ct.c_float),
        ("palm", LEAP_PALM),
        ("digits", LEAP_DIGIT * 5),
        ("arm", LEAP_BONE),
    ]


class LEAP_FRAME_HEADER(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("reserved", ct.c_void_p),
        ("frame_id", ct.c_int64),
        ("timestamp", ct.c_int64),
    ]


class LEAP_TRACKING_EVENT(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("info", LEAP_FRAME_HEADER),
        ("tracking_frame_id", ct.c_int64),
        ("nHands", ct.c_uint32),
        ("pHands", ct.POINTER(LEAP_HAND)),
        ("framerate", ct.c_float),
    ]


class LEAP_CONNECTION_EVENT(ct.Structure):
    _pack_ = 1
    _fields_ = [("flags", ct.c_uint32)]


class LEAP_CONNECTION_LOST_EVENT(ct.Structure):
    _pack_ = 1
    _fields_ = [("flags", ct.c_uint32)]


class LEAP_DEVICE_REF(ct.Structure):
    _pack_ = 1
    _fields_ = [("handle", ct.c_void_p), ("id", ct.c_uint32)]


class LEAP_DEVICE_EVENT(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("flags", ct.c_uint32),
        ("device", LEAP_DEVICE_REF),
        ("status", ct.c_uint32),
    ]


class LEAP_POLICY_EVENT(ct.Structure):
    _pack_ = 1
    _fields_ = [("reserved", ct.c_uint32), ("current_policy", ct.c_uint32)]


class LEAP_TRACKING_MODE_EVENT(ct.Structure):
    _pack_ = 1
    _fields_ = [("reserved", ct.c_uint32), ("current_tracking_mode", ct.c_int32)]


class LEAP_MESSAGE_UNION(ct.Union):
    _pack_ = 1
    _fields_ = [
        ("pointer", ct.c_void_p),
        ("connection_event", ct.POINTER(LEAP_CONNECTION_EVENT)),
        ("connection_lost_event", ct.POINTER(LEAP_CONNECTION_LOST_EVENT)),
        ("device_event", ct.POINTER(LEAP_DEVICE_EVENT)),
        ("policy_event", ct.POINTER(LEAP_POLICY_EVENT)),
        ("tracking_event", ct.POINTER(LEAP_TRACKING_EVENT)),
        ("tracking_mode_event", ct.POINTER(LEAP_TRACKING_MODE_EVENT)),
    ]


class LEAP_CONNECTION_MESSAGE(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("size", ct.c_uint32),
        ("type", ct.c_int32),
        ("event", LEAP_MESSAGE_UNION),
        ("device_id", ct.c_uint32),
    ]


EVENT_CONNECTION = 1
EVENT_CONNECTION_LOST = 2
EVENT_DEVICE = 3
EVENT_POLICY = 5
EVENT_TRACKING = 0x100
EVENT_DEVICE_LOST = 0x104
EVENT_TRACKING_MODE = 0x10B

TRACKING_MODE_DESKTOP = 0
TRACKING_MODE_HMD = 1
TRACKING_MODE_SCREENTOP = 2


@dataclass(slots=True)
class LowLevelMessage:
    event_type: int
    name: str
    payload: dict[str, Any]
    frame: FrameSnapshot | None


class LeapCLibrary:
    def __init__(self, lib_path: Path = LEAP_LIB_PATH):
        self.lib = ct.CDLL(str(lib_path))
        self.lib.LeapCreateConnection.argtypes = [ct.c_void_p, ct.POINTER(ct.c_void_p)]
        self.lib.LeapCreateConnection.restype = ct.c_int32
        self.lib.LeapOpenConnection.argtypes = [ct.c_void_p]
        self.lib.LeapOpenConnection.restype = ct.c_int32
        self.lib.LeapSetTrackingMode.argtypes = [ct.c_void_p, ct.c_int32]
        self.lib.LeapSetTrackingMode.restype = ct.c_int32
        self.lib.LeapPollConnection.argtypes = [
            ct.c_void_p,
            ct.c_uint32,
            ct.POINTER(LEAP_CONNECTION_MESSAGE),
        ]
        self.lib.LeapPollConnection.restype = ct.c_int32
        self.lib.LeapCloseConnection.argtypes = [ct.c_void_p]
        self.lib.LeapCloseConnection.restype = ct.c_int32
        self.lib.LeapDestroyConnection.argtypes = [ct.c_void_p]
        self.lib.LeapDestroyConnection.restype = ct.c_int32
        self.lib.LeapGetNow.argtypes = []
        self.lib.LeapGetNow.restype = ct.c_int64


class LeapConnection:
    def __init__(self, tracking_mode: str = "desktop"):
        self._lib = LeapCLibrary()
        self._handle = ct.c_void_p()
        result = self._lib.lib.LeapCreateConnection(None, ct.byref(self._handle))
        if result != 0:
            raise LeapError(f"LeapCreateConnection failed: {result}")
        result = self._lib.lib.LeapOpenConnection(self._handle)
        if result != 0:
            raise LeapError(f"LeapOpenConnection failed: {result}")
        self._tracking_mode = tracking_mode.lower()
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._lib.lib.LeapCloseConnection(self._handle)
        self._lib.lib.LeapDestroyConnection(self._handle)

    def poll(self, timeout_ms: int = 50) -> LowLevelMessage | None:
        msg = LEAP_CONNECTION_MESSAGE()
        msg.size = ct.sizeof(LEAP_CONNECTION_MESSAGE)
        result = self._lib.lib.LeapPollConnection(self._handle, timeout_ms, ct.byref(msg))
        code = result & 0xFFFFFFFF
        if code == 0xE2010004:  # Timeout
            return None
        if code != 0:
            raise LeapError(f"LeapPollConnection failed: {result} (0x{code:08X})")
        return self._convert_message(msg)

    def _convert_message(self, msg: LEAP_CONNECTION_MESSAGE) -> LowLevelMessage:
        if msg.type == EVENT_TRACKING and bool(msg.event.tracking_event):
            frame = self._frame_from_tracking(msg.event.tracking_event.contents, msg.device_id)
            return LowLevelMessage(
                event_type=msg.type,
                name="tracking",
                payload={},
                frame=frame,
            )
        if msg.type == EVENT_CONNECTION:
            return LowLevelMessage(msg.type, "connection", {}, None)
        if msg.type == EVENT_CONNECTION_LOST:
            return LowLevelMessage(msg.type, "connection_lost", {}, None)
        if msg.type == EVENT_DEVICE and bool(msg.event.device_event):
            payload = {
                "device_id": int(msg.event.device_event.contents.device.id),
                "status": int(msg.event.device_event.contents.status),
            }
            return LowLevelMessage(msg.type, "device", payload, None)
        if msg.type == EVENT_DEVICE_LOST:
            return LowLevelMessage(msg.type, "device_lost", {}, None)
        if msg.type == EVENT_POLICY and bool(msg.event.policy_event):
            payload = {"current_policy": int(msg.event.policy_event.contents.current_policy)}
            return LowLevelMessage(msg.type, "policy", payload, None)
        if msg.type == EVENT_TRACKING_MODE and bool(msg.event.tracking_mode_event):
            payload = {
                "tracking_mode": int(msg.event.tracking_mode_event.contents.current_tracking_mode)
            }
            return LowLevelMessage(msg.type, "tracking_mode", payload, None)
        return LowLevelMessage(msg.type, "other", {}, None)

    def _frame_from_tracking(
        self, tracking: LEAP_TRACKING_EVENT, device_id: int
    ) -> FrameSnapshot:
        chosen = None
        if tracking.nHands > 0 and bool(tracking.pHands):
            hand = tracking.pHands[0]
            chosen = self._hand_metrics_from_struct(hand)
        return FrameSnapshot(
            monotonic_time=time.monotonic(),
            service_timestamp_us=int(tracking.info.timestamp),
            frame_id=int(tracking.info.frame_id),
            tracking_frame_id=int(tracking.tracking_frame_id),
            framerate=float(tracking.framerate),
            device_id=int(device_id),
            hand=chosen,
        )

    @staticmethod
    def _vec3(vector: LEAP_VECTOR) -> Vector3:
        return Vector3(float(vector.x), float(vector.y), float(vector.z))

    def _hand_metrics_from_struct(self, hand: LEAP_HAND) -> HandMetrics:
        finger_count = 0
        for digit in hand.digits:
            if digit.is_extended:
                finger_count += 1
        hand_name = "left" if int(hand.type) == 0 else "right"
        return HandMetrics(
            hand=hand_name,
            confidence=float(hand.confidence),
            flags=int(hand.flags),
            pinch_strength=float(hand.pinch_strength),
            pinch_distance=float(hand.pinch_distance),
            grab_strength=float(hand.grab_strength),
            grab_angle=float(hand.grab_angle),
            finger_count=finger_count,
            visible_time_us=int(hand.visible_time),
            palm_position=self._vec3(hand.palm.position),
            palm_velocity=self._vec3(hand.palm.velocity),
            palm_normal=self._vec3(hand.palm.normal),
            palm_direction=self._vec3(hand.palm.direction),
            palm_width=float(hand.palm.width),
        )


def low_level_to_sensor_event(message: LowLevelMessage) -> SensorEvent:
    if message.frame is not None:
        return SensorEvent(kind="frame", frame=message.frame)
    return SensorEvent(kind="system", system_name=message.name, payload=message.payload)
