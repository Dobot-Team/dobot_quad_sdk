#!/usr/bin/env python3
"""Example 9: Combo sequence — Arduino-style sequential calls.
Each function blocks until the motion completes (scenario done signal).
You can add sleeps between calls and even run them in a loop.
Usage: python e9_combo_sequence.py [server_address]
"""
import sys
from dobot_quad import RobotClient


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    robot.enable_safety_ready()

    if robot.is_quad_wheel():
        print("\n=== Combo Sequence Demo (Wheel) ===")

        # 1) 基础状态切换 + 构型切换
        robot.passive()
        robot.ready()
        robot.wheel_loco()
        robot.change_mode()
        robot.change_mode()

        # 2) 前后左右各 1 米
        robot.walk_forward(1.0)
        robot.walk_backward(1.0)
        robot.move_left(1.0)
        robot.move_right(1.0)

        # 3) 左右转：90° 和 180°
        robot.rotate_left(90)
        robot.rotate_right(90)

        # 4) 转圈 1 圈
        robot.circle("left", 1)

        # 5) 轮足专用状态切换
        robot.drift()
        robot.wheel_loco()
        robot.handstand()

        # 6) 结束
        robot.stand_down()

        print("Done.")
        return
    else:
        print("\n=== Combo Sequence Demo (Full) ===")

        # 1) 构型切换
        robot.change_mode()
        robot.change_mode()

        # 2) 前后左右各 1 米
        robot.walk_forward(1.0)
        robot.walk_backward(1.0)
        robot.move_left(1.0)
        robot.move_right(1.0)

        # 3) 左右转：90° 和 180°
        robot.rotate_left(90)
        robot.rotate_left(180)
        robot.rotate_right(90)
        robot.rotate_right(180)

        # 4) 转圈 1 圈
        robot.circle("left", 1)

        # 5) 单轴平衡动作（dynamic + static）
        robot.balance_stand()
        robot.balance_pitch(15.0, 2.0, "dynamic")
        robot.balance_pitch(-15.0, 2.5, "static")
        robot.balance_yaw(20.0, 2.0, "dynamic")
        robot.balance_yaw(-20.0, 2.5, "static")
        robot.balance_roll(15.0, 2.0, "dynamic")
        robot.balance_roll(-15.0, 2.5, "static")
        robot.balance_height(-0.05, 2.0, "dynamic")
        robot.balance_height(-0.08, 2.5, "static")

        # 6) 两个复合平衡动作
        robot.dynamic_pose(
            3.0, roll_deg=10.0, pitch_deg=10.0, yaw_deg=15.0, height_m=-0.05
        )
        robot.static_pose(
            3.0, roll_deg=10.0, pitch_deg=10.0, yaw_deg=15.0, height_m=-0.05
        )
        robot.balance_neutral()

        # 7) 其他基础动作切换
        robot.ready()
        robot.balance_stand()
        robot.walk()
        robot.wave_hand()
        robot.dance()
        robot.rl()
        # robot.recovery()
        robot.stand_down()
        robot.passive()

        print("Done.")


if __name__ == "__main__":
    main()
