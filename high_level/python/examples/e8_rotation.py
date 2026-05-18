#!/usr/bin/env python3
"""Example 8: Rotate in place.
Usage: python e8_rotation.py [server_address] [direction] [angle]
  direction: 0=left/CCW (default), 1=right/CW
  angle:     degrees (default 90)
"""
import sys
from dobot_quad import RobotClient


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    robot.enable_safety_ready()
    direction = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    angle = float(sys.argv[3]) if len(sys.argv) > 3 else 90.0
    direction = 1 if direction == 1 else 0

    print(f"Rotation: {'left (CCW)' if direction == 0 else 'right (CW)'} {angle} deg")
    res = robot.rotate(direction, angle)
    res = robot.circle(direction="right", turns=3)
    return 0 if res and res.success else 1


if __name__ == "__main__":
    sys.exit(main())
