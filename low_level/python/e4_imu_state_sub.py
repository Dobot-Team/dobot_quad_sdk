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

    sys.stdout.write("\r")
    sys.stdout.write(f"Received LowerState #{count}\n")

    # Output complete IMU information
    imu_state = state.imu_state()
    sys.stdout.write(f"IMU State:\n")
    sys.stdout.write(f"  Quaternion: {list(imu_state.quaternion())}\n")
    sys.stdout.write(f"  Gyroscope (rad/s): {list(imu_state.gyroscope())}\n")
    sys.stdout.write(f"  Accelerometer (m/s²): {list(imu_state.accelerometer())}\n")
    sys.stdout.write(f"  RPY (roll, pitch, yaw in rad): {list(imu_state.rpy())}\n")
    sys.stdout.flush()


def main():
    middleware = dds.PyDDSMiddleware("config/dds_config.yaml")

    middleware.subscribeLowerState("rt/lower/state", lower_state_callback)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
