#!/usr/bin/env python3
"""Example 6: Balance motions demo (pitch, yaw, roll, height).
Usage: python e6_balance_motions.py [server_address]

Two modes:
  "dynamic" — sinusoidal sweep: 0 → value → 0 over duration.
  "static"  — ramp to value, hold for duration, ramp back to 0.
"""
import sys
from dobot_quad import RobotClient


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    robot.enable_safety_ready()

    if robot.is_quad_wheel():
        print("Balance motions are not supported on MINI_QUAD_WHEEL.")
        return 1

    robot.balance_stand()

    print("\n=== Balance Motions Demo ===")
    print("-" * 40)

    # --- Part 1: Single-axis API (dynamic | min duration=0.5s) ---
    print("\n[Single-axis API | dynamic]")
    robot.balance_pitch(15.0, 0.5, "dynamic")
    robot.balance_yaw(20.0, 0.5, "dynamic")
    robot.balance_roll(-30.0, 0.5, "dynamic")
    robot.balance_height(-0.12, 0.5, "dynamic")
    robot.balance_neutral()

    # --- Part 2: Single-axis API (static | max duration=5s) ---
    print("\n[Single-axis API | static]")
    robot.balance_pitch(-15.0, 5.0, "static")
    robot.balance_yaw(-20.0, 5.0, "static")
    robot.balance_roll(30.0, 5.0, "static")
    robot.balance_height(-0.12, 5.0, "static")
    robot.balance_neutral()

    # --- Part 3: balance_sequence (dynamic) ---
    print("\n[balance_sequence | dynamic]")
    robot.balance_sequence(
        [
            ("balance_pitch", 15.0, 0.5, "dynamic"),  # nod forward 15°
            ("balance_pitch", -15.0, 0.5, "dynamic"),  # nod backward 15°
            ("balance_yaw", 20.0, 0.5, "dynamic"),  # look left 20°
            ("balance_yaw", -20.0, 0.5, "dynamic"),  # look right 20°
            ("balance_roll", 30.0, 0.5, "dynamic"),  # lean left 30°
            ("balance_roll", -30.0, 0.5, "dynamic"),  # lean right 30°
            ("balance_height", -0.12, 0.5, "dynamic"),  # squat 12cm
            ("balance_neutral", 0.0, 0.5, "dynamic"),  # return to neutral
        ]
    )

    # --- Part 4: balance_sequence (static) ---
    print("\n[balance_sequence | static]")
    robot.balance_sequence(
        [
            ("balance_pitch", 15.0, 5.0, "static"),  # hold pitch 15° for 5s
            ("balance_neutral", 0.0, 0.5, "dynamic"),  # neutral
            ("balance_yaw", 20.0, 5.0, "static"),  # hold yaw 20° for 5s
            ("balance_neutral", 0.0, 0.5, "dynamic"),  # neutral
            ("balance_height", -0.12, 5.0, "static"),  # hold squat 12cm for 5s
            ("balance_neutral", 0.0, 0.5, "dynamic"),  # neutral
        ]
    )

    # --- Part 5: Different durations ---
    print("\n[Duration comparison]")
    robot.balance_sequence(
        [
            ("balance_pitch", 15.0, 0.5, "dynamic"),  # fast sweep (0.5s)
            ("balance_pitch", 15.0, 5.0, "dynamic"),  # slow sweep (5s)
            ("balance_neutral", 0.0, 0.5, "dynamic"),  # neutral
        ]
    )

    # --- Part 6: Composite pose (all axes simultaneously, duration in [1,5]) ---
    print("\n[Dynamic pose - composite]")
    robot.dynamic_pose(1.0, roll_deg=30.0, pitch_deg=15.0, yaw_deg=20.0, height_m=-0.12)

    print("\n[Static pose - composite]")
    robot.static_pose(
        5.0, roll_deg=-30.0, pitch_deg=-15.0, yaw_deg=-20.0, height_m=-0.12
    )

    robot.balance_neutral()

    # --- Part 7: Composite pose progression (duration sweep and combinations) ---
    print("\n[Composite pose progression with different durations]")
    robot.dynamic_pose(1.0, roll_deg=15.0, pitch_deg=8.0, yaw_deg=10.0, height_m=-0.06)
    robot.dynamic_pose(2.5, roll_deg=22.0, pitch_deg=12.0, yaw_deg=15.0, height_m=-0.09)
    robot.dynamic_pose(5.0, roll_deg=30.0, pitch_deg=15.0, yaw_deg=20.0, height_m=-0.12)
    robot.balance_neutral()

    # --- Part 8: Static pose variations ---
    print("\n[Static pose variations]")
    robot.static_pose(
        1.5, roll_deg=-18.0, pitch_deg=-10.0, yaw_deg=-12.0, height_m=-0.07
    )
    robot.static_pose(
        3.0, roll_deg=-25.0, pitch_deg=-13.0, yaw_deg=-18.0, height_m=-0.10
    )
    robot.static_pose(
        5.0, roll_deg=-30.0, pitch_deg=-15.0, yaw_deg=-20.0, height_m=-0.12
    )
    robot.balance_neutral()

    # --- Part 9: Mixed sequence (single-axis balance then composite pose) ---
    print("\n[Mixed: single-axis balance sequence then composite pose]")
    robot.balance_sequence(
        [
            ("balance_pitch", 12.0, 0.8, "dynamic"),  # pitch 12°
            ("balance_yaw", 15.0, 0.8, "dynamic"),  # yaw 15°
            ("balance_neutral", 0.0, 0.5, "dynamic"),  # reset
        ]
    )
    robot.dynamic_pose(2.0, roll_deg=18.0, pitch_deg=10.0, yaw_deg=12.0, height_m=-0.08)
    robot.balance_neutral()

    # --- Part 10: Rapid composite pose sequence (demonstrate min-to-max range) ---
    print("\n[Rapid composite pose sequence]")
    robot.dynamic_pose(1.0, roll_deg=10.0, pitch_deg=5.0, yaw_deg=8.0, height_m=-0.04)
    robot.static_pose(
        1.5, roll_deg=-15.0, pitch_deg=-8.0, yaw_deg=-10.0, height_m=-0.06
    )
    robot.dynamic_pose(3.0, roll_deg=25.0, pitch_deg=12.0, yaw_deg=18.0, height_m=-0.10)
    robot.static_pose(
        5.0, roll_deg=-30.0, pitch_deg=-15.0, yaw_deg=-20.0, height_m=-0.12
    )
    robot.balance_neutral()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
