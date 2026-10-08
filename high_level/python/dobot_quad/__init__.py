"""Dobot Quad High-Level Python SDK.

Provides a Pythonic gRPC client for controlling the Dobot quadruped robot.

Quick start::

    from dobot_quad import RobotClient, CameraId

    robot = RobotClient("192.168.5.2:50051")
    robot.balance_stand()
    robot.walk_forward(3.0)

    # Camera video streaming (robot.video, SDK v1.3.0)
    #   open() 阻塞到「流在推且有数据」，然后返回 RTSP 地址；
    #   媒体连接由你自己的播放器 / 算法建立（SDK 不取帧、不解码）。
    uri = robot.video.open(CameraId.FRONT_RGB)
    print(uri)                                    # rtsp://192.168.5.2:8554/camera1
    robot.video.close(CameraId.FRONT_RGB)
"""

from dobot_quad.robot_client import (
    RobotClient,
    Leg,
    Color,
    LegLedConfig,
    VALID_STATES,
    VALID_BALANCE_MOTIONS,
    VALID_GAITS,
    VALID_WHEEL_STATES,
    VALID_WHEEL_GAITS,
    VALID_ATOMIC_ACTIONS,
)
from dobot_quad.video import (
    CameraId,
    CameraStreamInfo,
    StreamEvent,
    StreamState,
    VideoConnectionError,
    VideoError,
    VideoTimeoutError,
)


__all__ = [
    "RobotClient",
    "Leg",
    "Color",
    "LegLedConfig",
    "VALID_STATES",
    "VALID_BALANCE_MOTIONS",
    "VALID_GAITS",
    "VALID_WHEEL_STATES",
    "VALID_WHEEL_GAITS",
    "VALID_ATOMIC_ACTIONS",
    # video
    "CameraId",
    "CameraStreamInfo",
    "StreamEvent",
    "StreamState",
    "VideoConnectionError",
    "VideoError",
    "VideoTimeoutError",
]
