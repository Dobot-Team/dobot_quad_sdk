#!/usr/bin/env python3
"""Example 3: Switch robot to a target state or trigger an atomic action.
Usage: python e3_auto_state_switch.py [server_address] [state_or_action_name]

Atomic actions (choreography moves) are executed directly by name — the
server transparently handles any state switching they need; there is no
user-visible "choreo" state.
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
    "gongxi",
    "wave",
    "dance0",
    "jump",
    "recovery",
    "change_mode",
]

# 编舞原子动作: server 端按需自动完成状态切换, 用户只见动作本身。
ATOMIC_ACTIONS = [
    "twirl_jump",   # 跳跃转体
    "diag_step",    # 对角迈步(step_full 前段)
    "hop_step",     # 前腿蹦跳迈步(step_full 后段)
    "groove",       # 摇摆律动
    "bounce",       # 点头弹跳
    "body_wave",    # 身体波浪
    "hip_circle",   # 扭屁股(臀画圆)
    "head_circle",  # 扭头(头画圆)
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

    is_wheel = robot.is_quad_wheel()
    states = WHEEL_STATES if is_wheel else STATES
    actions = [] if is_wheel else ATOMIC_ACTIONS
    entries = states + actions

    if len(sys.argv) > 2:
        target = sys.argv[2].lower()
    else:
        print("Available states:")
        for i, s in enumerate(states):
            print(f"  {i}. {s}")
        if actions:
            print("Atomic actions:")
            for i, a in enumerate(actions):
                print(f"  {i + len(states)}. {a}")

        while True:
            try:
                choice = int(input(f"Select [0-{len(entries)-1}]: "))
                if 0 <= choice < len(entries):
                    break
                print(f"Invalid choice. Please select [0-{len(entries)-1}].")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return 0

        target = entries[choice]

    if target in ATOMIC_ACTIONS:
        print(f"Executing action: {target}")
        res = robot.atomic_action(target)
    elif target == "change_mode":
        print(f"Switching to: {target}")
        res = robot.change_mode()
    else:
        print(f"Switching to: {target}")
        res = robot.set_target_state(target)

    if res and res.success:
        return 0
    print(f"Failed: {res.message if res else 'cancelled'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
