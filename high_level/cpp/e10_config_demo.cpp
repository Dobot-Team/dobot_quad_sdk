// Example 10: Speed Ratio & Obstacle Avoidance configuration demo.
// Usage: ./e10_config_demo [server_address]
//
// Demonstrates:
//   - Querying and setting speed ratio (10-100)
//   - Toggling obstacle avoidance on/off
//   - Walking at different speed ratios to see the difference

#include "robot_client.h"

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);

    // --- Speed Ratio Demo ---
    std::cout << std::string(50, '=') << std::endl;
    std::cout << "Speed Ratio Demo" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    // Query current speed ratio
    int current_sr = client.get_speed_ratio();
    std::cout << "Current speed ratio: " << current_sr << "\n" << std::endl;

    // Set base speed ratio to 10 (slow)
    std::cout << "--- Walk forward 1m at speed_ratio=10 (slow) ---" << std::endl;
    client.set_speed_ratio(10);
    current_sr = client.get_speed_ratio();
    std::cout << "Current speed ratio: " << current_sr << "\n" << std::endl;
    client.walk_forward(1.0);
    std::this_thread::sleep_for(std::chrono::seconds(1));

    // Walk forward with explicit speed_ratio=100 (temporary override, restores after)
    client.walk_forward(1.0, 100);
    current_sr = client.get_speed_ratio();
    std::cout << "Current speed ratio: " << current_sr << "\n" << std::endl;

    // --- Obstacle Avoidance Demo ---
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "Obstacle Avoidance Demo" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    // Disable obstacle avoidance
    std::cout << "\n--- Enabling obstacle avoidance ---" << std::endl;
    auto oa_resp = client.set_obstacle_avoidance("off");
    std::cout << "  OA enabled: " << (oa_resp.current_enabled() ? "true" : "false") << std::endl;
    std::cout << "  OA get: " << (client.get_obstacle_avoidance() ? "true" : "false") << std::endl;

    // Enable obstacle avoidance
    oa_resp = client.set_obstacle_avoidance(true);
    std::cout << "  OA enabled: " << (oa_resp.current_enabled() ? "true" : "false") << std::endl;
    std::cout << "  OA get: " << (client.get_obstacle_avoidance() ? "true" : "false") << std::endl;

    std::cout << "\nDemo complete." << std::endl;
    return 0;
}
