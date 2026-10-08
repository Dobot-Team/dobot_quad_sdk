"""Public types of the camera video streaming API.

Nothing media-related lives here: no frame type, no decoder, no RTP. `open()`
returns an RTSP address string and your own player opens it.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, NoReturn, Optional, Tuple

__all__ = [
    "CameraId",
    "CameraSpec",
    "CAMERA_SPECS",
    "StreamState",
    "StreamOwner",
    "LossReason",
    "RecoveredBy",
    "StreamEventKind",
    "CameraStreamInfo",
    "StreamEvent",
    "ObserveConfig",
    "RecoveryPolicy",
    "VideoError",
    "VideoConnectionError",
    "VideoTimeoutError",
    "STREAM_CODEC",
    "monotonic_s",
    "monotonic_ns",
]


def monotonic_s() -> float:
    """Monotonic clock in seconds."""
    return time.monotonic()


def monotonic_ns() -> int:
    """Monotonic clock in nanoseconds."""
    return time.monotonic_ns()


# --------------------------------------------------------------------------
# Cameras
# --------------------------------------------------------------------------
class CameraId(enum.IntEnum):
    """Camera identifier.

    Values are stable across releases: new cameras are appended.
    """

    FRONT_RGB = 0  # Front RGB camera
    REAR_RGB = 1   # Rear RGB camera

    @property
    def spec(self) -> "CameraSpec":
        return CAMERA_SPECS[self]

    @property
    def rtsp_name(self) -> str:
        """Stream name used inside the RTSP address."""
        return CAMERA_SPECS[self].rtsp_name

    @property
    def dds_index(self) -> int:
        """Topic index used by the DDS layer."""
        return CAMERA_SPECS[self].dds_index

    @property
    def description(self) -> str:
        return CAMERA_SPECS[self].description

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.name


@dataclass(frozen=True)
class CameraSpec:
    """Static description of a camera (internal mapping)."""

    rtsp_name: str
    dds_index: int
    description: str
    codec: str = "H.264"
    resolution: str = "1280x720"


#: Camera -> transport parameters.
CAMERA_SPECS: Dict[CameraId, CameraSpec] = {
    CameraId.FRONT_RGB: CameraSpec("camera1", 0, "Front RGB"),
    CameraId.REAR_RGB: CameraSpec("camera2", 1, "Rear RGB"),
}

#: Codec of the stream (fixed by the robot; the SDK does not transcode).
STREAM_CODEC = "H.264"


# --------------------------------------------------------------------------
# State / ownership / reasons
# --------------------------------------------------------------------------
class StreamState(enum.Enum):
    """Life cycle of one camera stream."""

    STOPPED = "stopped"        # Never opened, or closed again
    PREPARING = "preparing"    # open() is waiting for the camera to really stream
    READY = "ready"            # open() returned an address you can play
    RECOVERING = "recovering"  # The stream dropped or stalled; the SDK is bringing it back
    STOPPING = "stopping"      # Last user released it, the SDK is closing it down
    ERROR = "error"            # Automatic recovery gave up; call open() to try again

    def __str__(self) -> str:
        return self.value


class StreamOwner(enum.Enum):
    """Who started this stream, as far as the SDK can tell."""

    UNKNOWN = "unknown"
    SDK = "sdk"            # This SDK started it
    EXTERNAL = "external"  # It was already running (phone app, another program)

    def __str__(self) -> str:
        return self.value


class LossReason(enum.Enum):
    """Why a stream could not be used, or stopped being usable."""

    NONE = "none"
    EXTERNAL = "external"                  # Nothing is being pushed any more
    STALL = "stall"                        # Data stopped flowing while the stream was up
    PORT_UNREACHABLE = "port_unreachable"  # The streaming service cannot be reached
    NO_DATA = "no_data"                    # open() timed out before any data arrived
    CLOSED = "closed"                      # You closed it

    def __str__(self) -> str:
        return self.value


class RecoveredBy(enum.Enum):
    """What the SDK did to bring a stream back."""

    NONE = "none"
    L1_RESUME = "L1_resume"    # Asked the robot to resume pushing
    L2_RESTART = "L2_restart"  # Restarted the stream

    def __str__(self) -> str:
        return self.value


class StreamEventKind(enum.Enum):
    """Kind of change reported to on_state_change() callbacks."""

    READY = "StreamReady"
    LOST = "StreamLost"
    RECONNECTED = "StreamReconnected"
    CLOSED = "StreamClosed"
    ERROR = "StreamError"


# --------------------------------------------------------------------------
# Read-only data objects
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CameraStreamInfo:
    """Snapshot returned by `get_stream_info()`.

    Attributes:
        camera: which camera this is about.
        state: current life-cycle state.
        owner: who started the stream, as far as the SDK can tell.
        uri: address to play while the stream is up; empty when `STOPPED`.
        codec: stream codec (always ``H.264``).
        bitrate_kbps: recent bitrate estimate, ``None`` when unknown.
        reason: why the stream stopped working, if it did.
        message: extra detail, e.g. whether the stream was stopped.
    """

    camera: CameraId
    state: StreamState = StreamState.STOPPED
    owner: StreamOwner = StreamOwner.UNKNOWN
    uri: str = ""
    codec: str = STREAM_CODEC
    bitrate_kbps: Optional[float] = None
    reason: LossReason = LossReason.NONE
    message: str = ""

    @property
    def available(self) -> bool:
        """Whether `uri` can be played right now."""
        return self.state == StreamState.READY and bool(self.uri)

    @property
    def is_streaming(self) -> bool:
        """Whether the stream is ready to play."""
        return self.state == StreamState.READY

    def to_dict(self) -> Dict[str, object]:
        return {
            "camera": self.camera.name,
            "state": self.state.value,
            "owner": self.owner.value,
            "uri": self.uri,
            "codec": self.codec,
            "bitrate_kbps": self.bitrate_kbps,
            "reason": self.reason.value,
            "message": self.message,
        }

    def __str__(self) -> str:  # pragma: no cover - display only
        parts = [f"{self.camera.name}: {self.state.value}", f"owner={self.owner.value}"]
        if self.uri:
            parts.append(self.uri)
        if self.bitrate_kbps is not None:
            parts.append(f"{self.bitrate_kbps:.0f} kbps")
        if self.reason is not LossReason.NONE:
            parts.append(f"reason={self.reason.value}")
        if self.message:
            parts.append(self.message)
        return " | ".join(parts)


@dataclass(frozen=True)
class StreamEvent:
    """Event passed to on_state_change() callbacks."""

    kind: StreamEventKind
    camera: CameraId
    old_state: StreamState
    new_state: StreamState
    reason: LossReason = LossReason.NONE
    recovered_by: RecoveredBy = RecoveredBy.NONE
    uri: str = ""
    message: str = ""
    timestamp: float = field(default_factory=monotonic_s)

    @property
    def name(self) -> str:
        """One of StreamReady / StreamLost / StreamReconnected / StreamClosed / StreamError."""
        return self.kind.value

    def to_dict(self) -> Dict[str, object]:
        return {
            "event": self.name,
            "camera": self.camera.name,
            "old_state": self.old_state.value,
            "new_state": self.new_state.value,
            "reason": self.reason.value,
            "recovered_by": self.recovered_by.value,
            "uri": self.uri,
            "message": self.message,
            "timestamp": self.timestamp,
        }

    def __str__(self) -> str:  # pragma: no cover - display only
        extra = f" ({self.reason.value})" if self.reason is not LossReason.NONE else ""
        if self.recovered_by is not RecoveredBy.NONE:
            extra = f" (recovered_by={self.recovered_by.value})"
        tail = f" - {self.message}" if self.message else ""
        return (
            f"{self.name} {self.camera.name}: "
            f"{self.old_state.value} -> {self.new_state.value}{extra}{tail}"
        )


# --------------------------------------------------------------------------
# Internal tuning - deliberately not exposed to users
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ObserveConfig:
    """How often the SDK samples the stream state."""

    tick: float = 0.25              # Supervisor loop period (s)
    sample_interval: float = 2.0    # Sampling period while streaming (s)
    stall_samples: int = 2          # Flat samples in a row that count as stalled
    ready_timeout: float = 8.0      # How long open() waits for the stream (s)
    probe_timeout: float = 1.0      # Timeout of one state request (s)
    prepare_poll: float = 0.25      # Sampling period while starting up (s)
    settle_seconds: float = 0.3     # Gap between the two samples taken when closing (s)
    #: While starting up: how long "the stream exists but carries no new data"
    #: is tolerated before it is treated as stalled (s).
    prepare_stall_seconds: float = 2.5


@dataclass(frozen=True)
class RecoveryPolicy:
    """How the SDK recovers a broken stream (built in, not configurable)."""

    backoff: Tuple[float, ...] = (0.5, 1.0, 2.0)  # Delays between retries (s)
    max_attempts: int = 3                          # Give up after this many tries
    restart_cooldown: float = 60.0                 # Minimum gap between two restarts (s)
    restart_max_per_window: int = 2                # Restarts allowed per window
    restart_window: float = 600.0                  # Restart counting window (s)
    act_timeout: float = 3.0                       # Wait for evidence after a recovery action (s)


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------
class VideoError(RuntimeError):
    """Base class of every exception raised by this module.

    Attributes:
        reason: machine-readable reason, for callers that branch on it.
        camera: camera involved, when known.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: LossReason = LossReason.NONE,
        camera: Optional[CameraId] = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.camera = camera


class VideoConnectionError(VideoError):
    """The robot or its streaming service could not be reached."""


class VideoTimeoutError(VideoError):
    """The operation did not finish in time."""


def raise_video_error(
    message: str,
    *,
    reason: LossReason,
    camera: Optional[CameraId] = None,
) -> "NoReturn":
    """Raise the exception type that matches the failure reason.

    ``except VideoError`` keeps working (everything derives from it), and
    callers can now also catch the type the docs mention:

    * :class:`VideoConnectionError` -- the robot cannot be reached
      (``LossReason.PORT_UNREACHABLE``);
    * :class:`VideoTimeoutError` -- the stream produced no data in time
      (``LossReason.NO_DATA``);
    * anything else (stall / external stop / cancelled open) keeps the base
      class :class:`VideoError`, with ``reason`` telling them apart.
    """
    if reason is LossReason.PORT_UNREACHABLE:
        raise VideoConnectionError(message, reason=reason, camera=camera)
    if reason is LossReason.NO_DATA:
        raise VideoTimeoutError(message, reason=reason, camera=camera)
    raise VideoError(message, reason=reason, camera=camera)
