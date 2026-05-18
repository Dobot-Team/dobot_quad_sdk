#!/usr/bin/env python3
"""Example 4: Velocity Sequence Demo (walk / flying trot).
Usage: python e4_velocity_sequence.py [server_address] [1|2]
  1 = Walk demo (default)    2 = Flying trot demo
"""
import sys
from dobot_quad import RobotClient

WALK_STEPS = [
    (0.8, 0, 0, 2),  # forward
    (0, 0, 0, 1),  # stop
    (-0.8, 0, 0, 2),  # backward
    (0, 0, 0, 1),  # stop
    (0, 0.8, 0, 2),  # strafe left
    (0, 0, 0, 1),  # stop
    (0, -0.8, 0, 2),  # strafe right
    (0, 0, 0, 1),  # stop
    (0, 0, 0.8, 2),  # turn left
    (0, 0, 0, 1),  # stop
    (0, 0, -0.8, 2),  # turn right
    (0, 0, 0, 1),  # stop
]

FLYING_TROT_STEPS = [
    (0.8, 0, 0, 2),  # sprint forward
    (0, 0, 0, 1),  # stop
    (-0.6, 0, 0, 2),  # backward
    (0, 0, 0, 1),  # stop
    (0, 0.3, 0, 2),  # strafe left
    (0, 0, 0, 1),  # stop
    (0, -0.3, 0, 2),  # strafe right
    (0, 0, 0, 1),  # stop
    (0, 0, 0.6, 2),  # turn left
    (0, 0, 0, 1),  # stop
    (0, 0, -0.6, 2),  # turn right
    (0, 0, 0, 1),  # stop
]

WHEEL_LOCO_STEPS = [
    (0.8, 0, 0, 2),  # forward
    (0, 0, 0, 1),  # stop
    (-0.6, 0, 0, 2),  # backward
    (0, 0, 0, 1),  # stop
    (0, 0.3, 0, 2),  # strafe left
    (0, 0, 0, 1),  # stop
    (0, -0.3, 0, 2),  # strafe right
    (0, 0, 0, 1),  # stop
    (0, 0, 0.4, 2),  # turn left
    (0, 0, 0, 1),  # stop
    (0, 0, -0.4, 2),  # turn right
    (0, 0, 0, 1),  # stop
]


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    robot.enable_safety_ready()

    is_wheel = robot.is_quad_wheel()

    if is_wheel:
        # 轮足只有 wheel_loco gait
        gait = "wheel_loco"
        steps = WHEEL_LOCO_STEPS
        print("\n=== Wheel Loco Velocity Sequence ===")
    else:
        if len(sys.argv) > 2:
            choice = sys.argv[2]
        else:
            print("Gait mode:\n  1. Walk (default)\n  2. Flying Trot")
            try:
                choice = input("Select [1-2] (Enter=Walk): ").strip() or "1"
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return 0

        flying_trot = choice == "2"
        gait = "flying_trot" if flying_trot else "walk"
        steps = FLYING_TROT_STEPS if flying_trot else WALK_STEPS
        print(f"\n=== {'Flying Trot' if flying_trot else 'Walk'} Velocity Sequence ===")

    res = robot.velocity_sequence(steps, gait=gait, speed_ratio=60)
    return 0 if res and res.success else 1


if __name__ == "__main__":
    sys.exit(main())
