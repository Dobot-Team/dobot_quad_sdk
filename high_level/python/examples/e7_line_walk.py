#!/usr/bin/env python3
"""Example 7: Walk in a straight line.
Usage: python e7_line_walk.py [server_address] [direction] [distance]
  direction: 0=front (default), 1=back, 2=left, 3=right
  distance:  meters (default 3.0)
"""
import sys
from dobot_quad import RobotClient

DIRECTION_NAMES = ["front", "back", "left", "right"]


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    robot.enable_safety_ready()
    direction = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    distance = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

    print(f"Line Walk: {DIRECTION_NAMES[direction]} {distance}m")
    # res = robot.line_walk(direction, distance)
    # rotate_walk convention: left is negative angle, right is positive angle.
    res = robot.rotate_walk(angle=-45, distance=1.0, speed_ratio=10)
    return 0 if res and res.success else 1


if __name__ == "__main__":
    sys.exit(main())
