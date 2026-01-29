#!/usr/bin/env python3
"""
Motor Command Publisher - Sinusoidal Drive Example
Collects initial joint positions and then sends sinusoidal target positions
"""

import dds_middleware_python as dds
import time
import math

# Configuration parameters
NUM_MOTORS = 12
ABS2HW = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14]
MOTOR_OFFSET = [
    -0.05, -0.5, 1.17, 0.0, 0.05, -0.5, 1.17, 0.0, -0.05, 0.5, -1.17, 0.0, 0.05, 0.5, -1.17, 0.0
]

# Initial joint positions
q_init = [0.0] * 16
q_init_count = 0


def lower_state_callback(state):
    """Joint state callback, collect initial positions for the first 10 times"""
    global q_init_count, q_init

    if q_init_count < 10:
        motor_states = state.motor_state()
        for i in range(NUM_MOTORS):
            hw = ABS2HW[i]
            # Subtract offset when reading to get real joint angle
            q_init[hw] = motor_states[hw].q() - MOTOR_OFFSET[hw]

        q_init_count += 1
        if q_init_count == 10:
            print("Initial position collection completed: ", end="")
            for i in range(NUM_MOTORS):
                print(f"{q_init[ABS2HW[i]]:.4f} ", end="")
            print()


def create_damp_cmd():
    """Create damping mode command - using index accessor"""
    cmd = dds.LowerCmd()
    for i in range(NUM_MOTORS):
        hw = ABS2HW[i]
        cmd[hw].mode(0)
        cmd[hw].q(0.0 + MOTOR_OFFSET[hw])
        cmd[hw].dq(0.0)
        cmd[hw].tau(0.0)
        cmd[hw].kp(0.0)
        cmd[hw].kd(0.5)
    return cmd


def create_swing_cmd(s):
    """Create swing mode command - using index accessor"""
    cmd = dds.LowerCmd()
    for i in range(NUM_MOTORS):
        hw = ABS2HW[i]
        qdes = q_init[hw] + math.sin(2 * math.pi * s) * 0.2 + MOTOR_OFFSET[hw]
        cmd[hw].mode(0)
        cmd[hw].q(qdes)
        cmd[hw].dq(0.0)
        cmd[hw].tau(0.0)
        cmd[hw].kp(30.0)
        cmd[hw].kd(1.2)
    return cmd


def main():
    # Create DDS middleware
    middleware = dds.PyDDSMiddleware("config/dds_config.yaml")

    # QoS configuration
    qos_config = {
        "reliability": "reliable",
        "history_kind": "keep_last",
        "history_depth": 1,
        "durability": "volatile"
    }

    # Create publisher and subscriber
    middleware.createLowerCmdWriter("rt/lower/cmd", qos_config)
    middleware.subscribeLowerState("rt/lower/state", lower_state_callback)

    print("Waiting for initial position collection...")
    while q_init_count < 10:
        time.sleep(0.001)

    print("Starting control loop")

    for iter in range(60000000):
        if iter < 10:
            # Initialization phase
            cmd = create_damp_cmd()
            if iter == 0:
                print(f"[{iter}] Initialization phase")
        elif iter < 5000:
            # Swing phase
            s = (iter - 1000) / 500.0
            cmd = create_swing_cmd(s)
            if iter == 10:
                print(f"[{iter}] Starting swing")
        else:
            # Completion phase
            cmd = create_damp_cmd()
            if iter == 5000:
                print(f"[{iter}] Swing completed, entering damping mode")
                exit(0)
        middleware.publishLowerCmd(cmd)
        time.sleep(0.0022)  # 2.2ms

    print("Control sequence completed")


if __name__ == "__main__":
    main()
