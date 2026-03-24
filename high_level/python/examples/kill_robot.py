#!/usr/bin/env python3
"""Emergency shutdown: switch to PASSIVE then kill controller processes."""
import sys
from dobot_quad import RobotClient


def main():
    confirm = input("Kill robot controller? (y/N): ")
    if confirm.lower() != "y":
        print("Aborted.")
        return 0

    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    try:
        robot.execute("kill_robot")
    except Exception:
        print("Kill command sent (server shut down).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
