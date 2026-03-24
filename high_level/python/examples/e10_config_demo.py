#!/usr/bin/env python3
"""Example 10: Speed Ratio & Obstacle Avoidance configuration demo.
Usage: python e10_config_demo.py [server_address]

Demonstrates:
  - Querying and setting speed ratio (10-100)
  - Toggling obstacle avoidance on/off
  - Walking at different speed ratios to see the difference
"""
import sys
import time
from dobot_quad import RobotClient


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) >
                        1 else "192.168.5.2:50051")
    robot.enable_safety_ready()

    # --- Speed Ratio Demo ---
    print("=" * 50)
    print("Speed Ratio Demo")
    print("=" * 50)

    # Query current speed ratio
    current_sr = robot.get_speed_ratio()
    print(f"Current speed ratio: {current_sr}\n")

    # Walk forward at low speed (ratio=30)
    print("--- Walk forward 2m at speed_ratio=10 (slow) ---")
    robot.set_speed_ratio(10)
    # Query current speed ratio
    current_sr = robot.get_speed_ratio()
    print(f"Current speed ratio: {current_sr}\n")
    robot.walk_forward(1.0)
    time.sleep(1)
    # Query current speed ratio
    robot.walk_forward(1.0, speed_ratio=100)
    current_sr = robot.get_speed_ratio()
    print(f"Current speed ratio: {current_sr}\n")

    # --- Obstacle Avoidance Demo ---
    print("\n" + "=" * 50)
    print("Obstacle Avoidance Demo")
    print("=" * 50)

    # Enable obstacle avoidance
    print("\n--- Enabling obstacle avoidance ---")
    resp = robot.set_obstacle_avoidance("off")
    print(f"  OA enabled: {resp.current_enabled}")
    print(f"  OA get: {robot.get_obstacle_avoidance()}")
    resp = robot.set_obstacle_avoidance(True)
    print(f"  OA enabled: {resp.current_enabled}")
    print(f"  OA get: {robot.get_obstacle_avoidance()}")

    # robot.stand_down()
    print("\nDemo complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
