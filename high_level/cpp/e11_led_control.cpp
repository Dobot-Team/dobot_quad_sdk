// Example 11: Leg LED control demo.
// Usage: ./e11_led_control [server_address]
//
// Demonstrates:
//   - Single-leg predefined color (set_leg_color)
//   - Batch per-leg RGB via set_legs_rgb (one RPC)
//   - All four main legs same color (set_all_legs_color)
//   - Brightness adjustment without changing hue (set_leg_brightness)
//   - Turn off a leg while keeping user control (turn_off_leg)
//   - Release control back to robot default logic (reset_legs)
//   Note: fill lights (FILL_FRONT/FILL_BACK) are not supported by leg LED set APIs.

#include "robot_client.h"
#include <chrono>
#include <iostream>
#include <thread>

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);

    const auto pause = [] { std::this_thread::sleep_for(std::chrono::seconds(2)); };

    // --- Single Leg Color ---
    std::cout << std::string(50, '=') << std::endl;
    std::cout << "Single Leg Color" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    std::cout << "\n--- Set FL to RED ---" << std::endl;
    client.set_leg_color(robot::Leg::FL, robot::Color::RED, true);
    pause();

    // --- Batch Per-Leg RGB ---
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "Batch Per-Leg RGB" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    std::cout << "\n--- Four legs, four colors (one RPC) ---" << std::endl;
    std::vector<robot::LegLedConfig> rainbow = {
        {robot::Leg::FL, 255, 0, 0, 255},
        {robot::Leg::FR, 0, 255, 0, 255},
        {robot::Leg::RL, 0, 0, 255, 255},
        {robot::Leg::RR, 255, 255, 0, 255},
    };
    client.set_legs_rgb(rainbow, -1, true);
    pause();

    // --- All Legs Same Color ---
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "All Legs Same Color" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    std::cout << "\n--- All main legs CYAN, brightness=128 ---" << std::endl;
    client.set_all_legs_color(robot::Color::CYAN, 128, true);
    pause();

    // --- Brightness Only ---
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "Brightness Adjustment" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    std::cout << "\n--- Dim FR to brightness=32 (hue unchanged) ---" << std::endl;
    client.set_leg_brightness(robot::Leg::FR, 32, true);
    pause();

    // --- Turn Off ---
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "Turn Off Single Leg" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    std::cout << "\n--- Turn off RL (RGB=0, user control kept) ---" << std::endl;
    client.turn_off_leg(robot::Leg::RL, true);
    pause();

    // --- Reset ---
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "Reset Control" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    std::cout << "\n--- Reset FL only ---" << std::endl;
    client.reset_legs({robot::Leg::FL}, true);
    pause();

    std::cout << "\n--- Reset all leg lights ---" << std::endl;
    client.reset_legs({}, true);

    std::cout << "\nDemo complete." << std::endl;
    return 0;
}
