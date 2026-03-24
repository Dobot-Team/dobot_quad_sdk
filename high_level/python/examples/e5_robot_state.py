#!/usr/bin/env python3
"""Example 5: Get full robot state telemetry."""
import sys
from dobot_quad import RobotClient


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    res = robot.get_state()

    if not res.success:
        print(f"Failed: {res.message}")
        return 1

    print(f"Current state: {res.current_state}\n")
    print(f"Speed ratio: {res.current_speed_ratio}")
    print(f"Obstacle avoidance: {'enabled' if res.obstacle_avoidance_enabled else 'disabled'}\n")

    s = res.robot_state
    fmt = lambda arr: [f"{x:.2f}" for x in arr]

    print("Leg Joints:")
    print(f"  pos [rad]:     {fmt(s.jpos_leg)}")
    print(f"  pos_des [rad]: {fmt(s.jpos_leg_des)}")
    print(f"  vel [rad/s]:   {fmt(s.jvel_leg)}")
    print(f"  vel_des:       {fmt(s.jvel_leg_des)}")
    print(f"  tau [Nm]:      {fmt(s.jtau_leg)}")
    print(f"  tau_des [Nm]:  {fmt(s.jtau_leg_des)}")

    print(f"\nBody:")
    print(f"  pos [m]:       {fmt(s.pos_body)}")
    print(f"  vel [m/s]:     {fmt(s.vel_body)}")
    print(f"  acc [m/s^2]:   {fmt(s.acc_body)}")
    print(f"  omega [rad/s]: {fmt(s.omega_body)}")
    print(f"  rpy [rad]:     {fmt(s.ori_body)}")

    print(f"\nContact:")
    print(f"  left  [N]:     {fmt(s.grf_left)}")
    print(f"  right [N]:     {fmt(s.grf_right)}")
    print(f"  vertical [N]:  {fmt(s.grf_vertical_filtered)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
