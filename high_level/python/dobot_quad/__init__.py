"""Dobot Quad High-Level Python SDK.

Provides a Pythonic gRPC client for controlling the Dobot quadruped robot.

Quick start::

    from dobot_quad import RobotClient

    robot = RobotClient("192.168.5.2:50051")
    robot.balance_stand()
    robot.walk_forward(3.0)
"""

from dobot_quad.robot_client import (
    RobotClient,
    VALID_STATES,
    VALID_BALANCE_MOTIONS,
    VALID_GAITS,
    VALID_WHEEL_STATES,
    VALID_WHEEL_GAITS,
)


__all__ = [
    "RobotClient",
    "VALID_STATES",
    "VALID_BALANCE_MOTIONS",
    "VALID_GAITS",
    "VALID_WHEEL_STATES",
    "VALID_WHEEL_GAITS",
]
