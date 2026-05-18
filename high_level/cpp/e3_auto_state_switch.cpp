// Example 3: Switch robot to a target state (interactive or CLI).
// Usage: ./e3_auto_state_switch [server_address] [state_name]
//
// Simplified API:
//   client.set_balance_stand();          // direct call
//   client.set_target_state("walk");     // by name

#include "robot_client.h"
#include <algorithm>
#include <limits>

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);

    auto run_action = [&client](const std::string& target) {
        if (target == "change_mode") {
            return client.change_mode();
        }
        return client.set_target_state(target);
    };

    if (argc > 2) {
        // CLI mode: ./e3 addr balance_stand
        std::string target = argv[2];
        std::transform(target.begin(), target.end(), target.begin(), ::tolower);
        return run_action(target) ? 0 : 1;
    }

    // Interactive mode
    const bool is_wheel = client.is_quad_wheel();

    const char* quad_states[] = {"emergency", "ready", "stand_down", "balance_stand", "walk", "rl", "flying_trot",
        "wave", "dance0", "jump", "recovery", "change_mode"};
    const char* wheel_states[] = {"emergency", "ready", "stand_down", "wheel_loco", "drift", "handstand",
        "change_mode"};

    const char** states = is_wheel ? wheel_states : quad_states;
    const int n = is_wheel ? static_cast<int>(sizeof(wheel_states) / sizeof(wheel_states[0]))
                           : static_cast<int>(sizeof(quad_states) / sizeof(quad_states[0]));

    std::cout << "Available states:" << std::endl;
    for (int i = 0; i < n; ++i)
        std::cout << "  " << i << ". " << states[i] << std::endl;

    int choice = -1;
    while (true) {
        std::cout << "Select [0-" << n - 1 << "]: ";
        if (!(std::cin >> choice)) {
            if (std::cin.eof())
                return 0;
            std::cin.clear();
            std::cin.ignore(std::numeric_limits<std::streamsize>::max(), '\n');
            std::cerr << "Invalid input. Please enter a number." << std::endl;
            continue;
        }
        if (choice < 0 || choice >= n) {
            std::cerr << "Invalid choice " << choice << ". Please select [0-" << n - 1 << "]." << std::endl;
            continue;
        }
        break;
    }

    std::string target = states[choice];
    std::cout << "Switching to: " << target << std::endl;

    return run_action(target) ? 0 : 1;
}
