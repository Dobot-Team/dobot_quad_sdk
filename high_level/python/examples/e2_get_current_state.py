#!/usr/bin/env python3
"""Example 2: Get the current FSM state name."""
import sys
from dobot_quad import RobotClient


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    state = robot.get_current_state_name()

    if state:
        print(f"Current state: {state}")
        return 0
    else:
        print("Failed to get state")
        return 1


if __name__ == "__main__":
    sys.exit(main())
