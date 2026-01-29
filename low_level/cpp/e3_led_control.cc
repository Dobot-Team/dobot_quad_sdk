#include "dds_middleware.hpp" // Need this header
#include "leds_cmd.hpp"       // Also include IDL message type header
#include <thread>
#include <chrono>
#include <iostream>
#include <vector>
#include <cmath>

using namespace dds_middleware;
using namespace dobotmh4::msg::dds_;

int main()
{
    try {
        DDSMiddleware middleware(0); // Construct DDSMiddleware instance

        dds_middleware::QoSProfile custom_qos;
        custom_qos.reliability = dds_middleware::ReliabilityPolicy::RELIABLE;
        custom_qos.durability = dds_middleware::DurabilityPolicy::VOLATILE;
        custom_qos.history = dds_middleware::HistoryPolicy::KEEP_LAST;
        custom_qos.history_depth = 1;
        // Create publisher
        auto publisher = middleware.create_publisher<LedsCmd_>("rt/leds/cmd", custom_qos);

        // Breathing effect parameters
        const int breath_period_ms = 5000;                       // Breathing period 5 seconds
        const int update_interval_ms = 100;                      // Update every 100ms
        const int steps = breath_period_ms / update_interval_ms; // Total steps
        const int program_duration_ms = 15000;                   // Program runs for 15 seconds

        auto program_start = std::chrono::steady_clock::now();

        while (true) {
            // Check if program has run for 5 seconds
            auto current_time = std::chrono::steady_clock::now();
            auto elapsed_ms
                = std::chrono::duration_cast<std::chrono::milliseconds>(current_time - program_start).count();

            if (elapsed_ms >= program_duration_ms) {
                std::cout << "Program finished after " << program_duration_ms << "ms" << std::endl;
                break;
            }

            for (int i = 0; i <= steps; i++) {
                // Calculate current intensity value (sine wave for breathing effect)
                float phase = static_cast<float>(i) / steps * 2 * M_PI;
                float intensity = (std::sin(phase) + 1) / 2; // Range 0 to 1

                // Create LED control message - using mode0 rgb mode, breathing effect via RGB values
                LedControl_ led1;
                led1.name("leg_light1");                       // LED ID
                led1.mode(0);                                  // Mode: 0=rgb mode
                led1.brightness(255);                          // Brightness fixed at 255 (function not implemented)
                led1.r(static_cast<uint8_t>(255 * intensity)); // Red intensity modulation
                led1.g(0);                                     // Green
                led1.b(0);                                     // Blue
                led1.priority(0);                              // Priority

                LedControl_ led2;
                led2.name("leg_light2");
                led2.mode(0);
                led2.brightness(255);
                led2.r(0);
                led2.g(static_cast<uint8_t>(255 * intensity)); // Green intensity modulation
                led2.b(0);
                led2.priority(0);

                LedControl_ led3;
                led3.name("leg_light3");
                led3.mode(0);
                led3.brightness(255);
                led3.r(0);
                led3.g(0);
                led3.b(static_cast<uint8_t>(255 * intensity)); // Blue intensity modulation
                led3.priority(0);

                LedControl_ led4;
                led4.name("leg_light4");
                led4.mode(0);
                led4.brightness(255);
                led4.r(static_cast<uint8_t>(255 * intensity)); // White RGB all modulated
                led4.g(static_cast<uint8_t>(255 * intensity));
                led4.b(static_cast<uint8_t>(255 * intensity));
                led4.priority(0);

                LedControl_ led5;
                led5.name("fill_light1");
                led5.mode(0);
                if (i > 25) {
                    led5.brightness(0);
                } else {
                    led5.brightness(255);
                }

                led5.priority(0);

                LedControl_ led6;
                led6.name("fill_light3");
                led6.mode(0);
                if (i > 25) {
                    led6.brightness(0);
                } else {
                    led6.brightness(255);
                }
                led6.priority(0);

                // Create LED command message
                LedsCmd_ cmd;
                std::vector<LedControl_> leds {led1, led2, led3, led4, led5, led6};
                cmd.leds(leds);

                // Execute message publish action
                publisher->publish(cmd);

                std::cout << "Published LED control command: "
                          << "Intensity: " << static_cast<int>(intensity * 100) << "%"
                          << " LED1 (R:" << (int)led1.r() << " G:" << (int)led1.g() << " B:" << (int)led1.b()
                          << ") LED2 (R:" << (int)led2.r() << " G:" << (int)led2.g() << " B:" << (int)led2.b()
                          << ") LED3 (R:" << (int)led3.r() << " G:" << (int)led3.g() << " B:" << (int)led3.b()
                          << ") LED4 (R:" << (int)led4.r() << " G:" << (int)led4.g() << " B:" << (int)led4.b()
                          << ") LED5 (Brightness:" << (int)led5.brightness()
                          << ") LED6 (Brightness:" << (int)led6.brightness() << ")" << std::endl;

                std::this_thread::sleep_for(std::chrono::milliseconds(update_interval_ms));
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
