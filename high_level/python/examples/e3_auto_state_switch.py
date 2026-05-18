#!/usr/bin/env python3
"""Example 3: Switch robot to a target state (interactive or CLI).
Usage: python e3_auto_state_switch.py [server_address] [state_name]
"""
import sys
from dobot_quad import RobotClient

STATES = [
    "emergency",
    "ready",
    "stand_down",
    "balance_stand",
    "walk",
    "rl",
    "flying_trot",
    "wave",
    "dance0",
    "jump",
    "recovery",
    "change_mode",
]

WHEEL_STATES = [
    "emergency",
    "ready",
    "stand_down",
    "wheel_loco",
    "drift",
    "handstand",
    "change_mode",
]


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    robot.enable_safety_ready()

    states = WHEEL_STATES if robot.is_quad_wheel() else STATES

    if len(sys.argv) > 2:
        target = sys.argv[2].lower()
    else:
        print("Available states:")
        for i, s in enumerate(states):
            print(f"  {i}. {s}")

        while True:
            try:
                choice = int(input(f"Select [0-{len(states)-1}]: "))
                if 0 <= choice < len(states):
                    break
                print(f"Invalid choice. Please select [0-{len(states)-1}].")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return 0

        target = states[choice]

    print(f"Switching to: {target}")
    if target == "change_mode":
        res = robot.change_mode()
    else:
        res = robot.set_target_state(target)

    if res and res.success:
        return 0
    print(f"Failed: {res.message if res else 'cancelled'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
