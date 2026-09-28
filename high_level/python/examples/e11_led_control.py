#!/usr/bin/env python3
"""Example 11: Leg LED control demo.
Usage: python e11_led_control.py [server_address]

Demonstrates:
  - Single-leg predefined color (set_leg_color)
  - Batch per-leg RGB via set_legs_rgb (one RPC)
  - All four main legs same color (set_all_legs_color)
  - Brightness adjustment without changing hue (set_leg_brightness)
  - Turn off a leg while keeping user control (turn_off_leg)
  - Release control back to robot default logic (reset_legs)

Note: fill lights (FILL_FRONT/FILL_BACK) are not supported by leg LED set APIs.
"""
import sys
import time

from dobot_quad import RobotClient, Leg, Color, LegLedConfig


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    robot.enable_safety_ready()

    pause = lambda: time.sleep(2)

    # --- Single Leg Color ---
    print("=" * 50)
    print("Single Leg Color")
    print("=" * 50)

    print("\n--- Set FL to RED ---")
    robot.set_leg_color(Leg.FL, Color.RED, verbose=True)
    pause()

    # --- Batch Per-Leg RGB ---
    print("\n" + "=" * 50)
    print("Batch Per-Leg RGB")
    print("=" * 50)

    print("\n--- Four legs, four colors (one RPC) ---")
    rainbow = [
        LegLedConfig(leg=Leg.FL, r=255, g=0, b=0, brightness=255),
        LegLedConfig(leg=Leg.FR, r=0, g=255, b=0, brightness=255),
        LegLedConfig(leg=Leg.RL, r=0, g=0, b=255, brightness=255),
        LegLedConfig(leg=Leg.RR, r=255, g=255, b=0, brightness=255),
    ]
    robot.set_legs_rgb(rainbow, verbose=True)
    pause()

    # --- All Legs Same Color ---
    print("\n" + "=" * 50)
    print("All Legs Same Color")
    print("=" * 50)

    print("\n--- All main legs CYAN, brightness=128 ---")
    robot.set_all_legs_color(Color.CYAN, brightness=128, verbose=True)
    pause()

    # --- Brightness Only ---
    print("\n" + "=" * 50)
    print("Brightness Adjustment")
    print("=" * 50)

    print("\n--- Dim FR to brightness=32 (hue unchanged) ---")
    robot.set_leg_brightness(Leg.FR, 32, verbose=True)
    pause()

    # --- Turn Off ---
    print("\n" + "=" * 50)
    print("Turn Off Single Leg")
    print("=" * 50)

    print("\n--- Turn off RL (RGB=0, user control kept) ---")
    robot.turn_off_leg(Leg.RL, verbose=True)
    pause()

    # --- Reset ---
    print("\n" + "=" * 50)
    print("Reset Control")
    print("=" * 50)

    print("\n--- Reset FL only ---")
    robot.reset_legs([Leg.FL], verbose=True)
    pause()

    print("\n--- Reset all leg lights ---")
    robot.reset_legs(verbose=True)

    print("\nDemo complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
