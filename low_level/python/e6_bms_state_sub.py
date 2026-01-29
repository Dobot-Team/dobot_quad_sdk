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

    bms = state.bms_state()

    sys.stdout.write("\r")
    sys.stdout.write(f"Received BMS State #{count}\n")
    sys.stdout.write(f"Battery Level: {bms.battery_level()}\n")
    sys.stdout.write("\n")
    sys.stdout.flush()


def main():
    middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
    middleware.subscribeLowerState("rt/lower/state", lower_state_callback)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
