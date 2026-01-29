import dds_middleware_python as dds
import time
import sys


count = 0
last_time = time.time()


def lower_state_callback(state):
    global count, last_time
    count += 1

    now = time.time()
    if (now - last_time) * 1000 < 500:  # Only output every 500ms
        return
    last_time = now

    motor_states = state.motor_state()

    sys.stdout.write("\r")
    sys.stdout.write(f"Received Motor States #{count}\n")
    for i in range(16):
        motor = motor_states[i]
        sys.stdout.write(
            f"Motor[{i}]: mode={motor.mode()}, q(rad)={motor.q():.6f}, dq(rad/s)={motor.dq():.6f}, "
            f"ddq(rad/s²)={motor.ddq():.6f}, tau_est(N·m)={motor.tau_est():.5f}, q_raw(rad)={motor.q_raw():.6f}, "
            f"dq_raw(rad/s)={motor.dq_raw():.6f}, ddq_raw(rad/s²)={motor.ddq_raw():.6f}, motor_temp(°C)={motor.motor_temp()}\n"
        )
    sys.stdout.write("\n")
    sys.stdout.flush()


def main():
    middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
    middleware.subscribeLowerState("rt/lower/state", lower_state_callback)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
