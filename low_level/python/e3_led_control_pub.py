import dds_middleware_python as dds
import time
import math


def main():
    # Create DDS middleware instance
    middleware = dds.PyDDSMiddleware(0)

    # Configure QoS parameters, matching C++ publisher config
    qos_config = {
        "reliability": "reliable",
        "history_kind": "keep_last",
        "history_depth": 1,
        "durability": "volatile"
    }

    # Create LedsCmd publisher
    middleware.createLedsCmdWriter("rt/leds/cmd", qos_config)

    # Breathing effect parameters
    breath_period_ms = 5000  # Breathing period 5 seconds
    update_interval_ms = 100  # Update every 100ms
    steps = breath_period_ms // update_interval_ms  # Total steps
    program_duration_ms = 15000  # Program runs for 15 seconds

    print("LED control publisher started, press Ctrl+C to exit...")

    program_start = time.time()

    try:
        while True:
            # Check if program has run for 15 seconds
            current_time = time.time()
            elapsed_ms = (current_time - program_start) * 1000

            if elapsed_ms >= program_duration_ms:
                print(f"Program finished after {program_duration_ms}ms")
                break

            for i in range(steps + 1):
                # Calculate current intensity value (sine wave for breathing effect)
                phase = (i / steps) * 2 * math.pi
                intensity = (math.sin(phase) + 1) / 2  # Range 0 to 1

                # Create LED control command
                led_cmd = dds.LedsCmd()
                leds = []

                # LED1 - Red breathing
                led1 = dds.LEDControl()
                led1.name("leg_light1")
                led1.mode(0)  # RGB mode
                led1.brightness(255)
                led1.r(int(255 * intensity))
                led1.g(0)
                led1.b(0)
                led1.priority(0)
                leds.append(led1)

                # LED2 - Green breathing
                led2 = dds.LEDControl()
                led2.name("leg_light2")
                led2.mode(0)
                led2.brightness(255)
                led2.r(0)
                led2.g(int(255 * intensity))
                led2.b(0)
                led2.priority(0)
                leds.append(led2)

                # LED3 - Blue breathing
                led3 = dds.LEDControl()
                led3.name("leg_light3")
                led3.mode(0)
                led3.brightness(255)
                led3.r(0)
                led3.g(0)
                led3.b(int(255 * intensity))
                led3.priority(0)
                leds.append(led3)

                # LED4 - White breathing (all RGB modulated)
                led4 = dds.LEDControl()
                led4.name("leg_light4")
                led4.mode(0)
                led4.brightness(255)
                led4.r(int(255 * intensity))
                led4.g(int(255 * intensity))
                led4.b(int(255 * intensity))
                led4.priority(0)
                leds.append(led4)

                # LED5 - Fill light (on/off)
                led5 = dds.LEDControl()
                led5.name("fill_light1")
                led5.mode(0)
                led5.brightness(255 if i <= 25 else 0)
                led5.priority(0)
                leds.append(led5)

                # LED6 - Fill light (on/off)
                led6 = dds.LEDControl()
                led6.name("fill_light3")
                led6.mode(0)
                led6.brightness(255 if i <= 25 else 0)
                led6.priority(0)
                leds.append(led6)

                # Add LED control items to command
                led_cmd.leds(leds)

                # Publish LED control command
                middleware.publishLedsCmd(led_cmd)

                print(
                    f"Published LED control command: Intensity: {int(intensity * 100)}% "
                    f"LED1 (R:{led1.r()} G:{led1.g()} B:{led1.b()}) "
                    f"LED2 (R:{led2.r()} G:{led2.g()} B:{led2.b()}) "
                    f"LED3 (R:{led3.r()} G:{led3.g()} B:{led3.b()}) "
                    f"LED4 (R:{led4.r()} G:{led4.g()} B:{led4.b()}) "
                    f"LED5 (Brightness:{led5.brightness()}) "
                    f"LED6 (Brightness:{led6.brightness()})"
                )

                time.sleep(update_interval_ms / 1000.0)

    except KeyboardInterrupt:
        print("\nExiting program")


if __name__ == "__main__":
    main()
