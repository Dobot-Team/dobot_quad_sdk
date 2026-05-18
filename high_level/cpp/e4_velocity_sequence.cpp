// Example 4: Velocity Sequence Demo (walk / flying trot).
// Usage: ./e4_velocity_sequence [server_address] [1|2]
//   1 = Walk demo (default)    2 = Flying trot demo
//   No arg → interactive selection (Enter = Walk)
//
// Simplified API:
//   client.velocity_sequence("0.5,0,0,2;0,0,0,1;");
//   client.velocity_sequence({{0.5,0,0,2},{0,0,0,1}}, "flying_trot");

#include "robot_client.h"
#include <limits>

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);

    const bool is_wheel = client.is_quad_wheel();

    // --- Select gait mode ---
    int gait_choice = 1;
    if (argc > 2) {
        gait_choice = std::stoi(argv[2]);
    } else {
        if (is_wheel) {
            std::cout << "Gait mode:\n  1. Wheel Loco (default)\n";
            std::cout << "Select [1] (Enter=Wheel Loco): ";
        } else {
            std::cout << "Gait mode:\n  1. Walk (default)\n  2. Flying Trot\n";
            std::cout << "Select [1-2] (Enter=Walk): ";
        }
        std::string line;
        std::getline(std::cin, line);
        if (!line.empty())
            gait_choice = std::stoi(line);
    }

    std::string gait;
    if (is_wheel) {
        gait = "wheel_loco";
    } else {
        gait = (gait_choice == 2) ? "flying_trot" : "walk";
    }

    // Using the structured VelocityStep API
    std::vector<robot::VelocityStep> steps;
    if (is_wheel) {
        std::cout << "\n=== Wheel Loco Velocity Sequence ===" << std::endl;
        steps = {
            {0.8f, 0, 0, 2},  // forward
            {0, 0, 0, 1},     // stop
            {-0.6f, 0, 0, 2}, // backward
            {0, 0, 0, 1},     // stop
            {0, 0.3f, 0, 2},  // strafe left
            {0, 0, 0, 1},     // stop
            {0, -0.3f, 0, 2}, // strafe right
            {0, 0, 0, 1},     // stop
            {0, 0, 0.4f, 2},  // turn left
            {0, 0, 0, 1},     // stop
            {0, 0, -0.4f, 2}, // turn right
            {0, 0, 0, 1},     // stop
        };
    } else if (gait == "flying_trot") {
        std::cout << "\n=== Flying Trot Velocity Sequence ===" << std::endl;
        steps = {
            {0.8f, 0, 0, 2},  // sprint forward
            {0, 0, 0, 1},     // stop
            {-0.6f, 0, 0, 2}, // backward
            {0, 0, 0, 1},     // stop
            {0, 0.3f, 0, 2},  // strafe left
            {0, 0, 0, 1},     // stop
            {0, -0.3f, 0, 2}, // strafe right
            {0, 0, 0, 1},     // stop
            {0, 0, 0.6f, 2},  // turn left
            {0, 0, 0, 1},     // stop
            {0, 0, -0.6f, 2}, // turn right
            {0, 0, 0, 1},     // stop
        };
    } else {
        std::cout << "\n=== Walk Velocity Sequence ===" << std::endl;
        steps = {
            {0.5f, 0, 0, 2},  // forward
            {0, 0, 0, 1},     // stop
            {-0.4f, 0, 0, 2}, // backward
            {0, 0, 0, 1},     // stop
            {0, 0.2f, 0, 2},  // strafe left
            {0, 0, 0, 1},     // stop
            {0, -0.2f, 0, 2}, // strafe right
            {0, 0, 0, 1},     // stop
            {0, 0, 0.5f, 2},  // turn left
            {0, 0, 0, 1},     // stop
            {0, 0, -0.5f, 2}, // turn right
            {0, 0, 0, 1},     // stop
        };
    }

    return client.velocity_sequence(steps, gait, 80) ? 0 : 1;
}
