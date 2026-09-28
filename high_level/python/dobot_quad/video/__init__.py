"""Camera video streaming.

One entry point is all you need:

```python
from dobot_quad import RobotClient, CameraId

robot = RobotClient("192.168.5.2:50051")
uri = robot.video.open(CameraId.FRONT_RGB)   # returns the RTSP address
# hand the address to your own player or vision code
robot.video.close(CameraId.FRONT_RGB)
```

The SDK switches the stream on and watches it for you. It never opens a media
connection itself: no frames, no decoding, no muxing - pulling the address is
up to OpenCV / ffmpeg / VLC / GStreamer or whatever you prefer.
"""

from .arbiter import StreamArbiter
from .controller import StreamingController
from .manager import Endpoints, VideoStreamManager
from .probe import Consumer, StatusProbe, StreamStatus
from .types import (
    CAMERA_SPECS,
    STREAM_CODEC,
    CameraId,
    CameraSpec,
    CameraStreamInfo,
    LossReason,
    ObserveConfig,
    RecoveredBy,
    RecoveryPolicy,
    StreamEvent,
    StreamEventKind,
    StreamOwner,
    StreamState,
    VideoConnectionError,
    VideoError,
    VideoTimeoutError,
)

__all__ = [
    # Public
    "VideoStreamManager",
    "CameraId",
    "CameraSpec",
    "CAMERA_SPECS",
    "CameraStreamInfo",
    "StreamEvent",
    "StreamEventKind",
    "StreamState",
    "StreamOwner",
    "LossReason",
    "RecoveredBy",
    "VideoError",
    "VideoConnectionError",
    "VideoTimeoutError",
    "STREAM_CODEC",
    # Internals (tests and advanced use)
    "StreamArbiter",
    "StreamingController",
    "StatusProbe",
    "StreamStatus",
    "Consumer",
    "Endpoints",
    "ObserveConfig",
    "RecoveryPolicy",
]
