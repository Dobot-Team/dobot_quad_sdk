// Example 3: Switch robot to a target state or trigger an atomic action.
// Usage: ./e3_auto_state_switch [server_address] [state_or_action_name]
//
// Simplified API:
//   client.set_balance_stand();          // direct call
//   client.set_target_state("walk");     // by name
//   client.atomic_action("twirl_jump");  // choreography atomic action
//
// Atomic actions (choreography moves) are executed directly by name — the
// server transparently handles any state switching they need; there is no
// user-visible "choreo" state.

#include "robot_client.h"
#include <algorithm>
#include <limits>

// 编舞原子动作: server 端按需自动完成状态切换, 用户只见动作本身。
static const char* kAtomicActions[] = {
    "twirl_jump",  // 跳跃转体
    "diag_step",   // 对角迈步(step_full 前段)
    "hop_step",    // 前腿蹦跳迈步(step_full 后段)
    "groove",      // 摇摆律动
    "bounce",      // 点头弹跳
    "body_wave",   // 身体波浪
    "hip_circle",  // 扭屁股(臀画圆)
    "head_circle", // 扭头(头画圆)
};
static constexpr int kNumAtomicActions = static_cast<int>(sizeof(kAtomicActions) / sizeof(kAtomicActions[0]));

static bool is_atomic_action(const std::string& name)
{
    for (const char* a : kAtomicActions) {
        if (name == a)
            return true;
    }
    return false;
}

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);

    auto run_action = [&client](const std::string& target) {
        if (is_atomic_action(target)) {
            std::cout << "Executing action: " << target << std::endl;
            return client.atomic_action(target);
        }
        std::cout << "Switching to: " << target << std::endl;
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
        "gongxi", "wave", "dance0", "jump", "recovery", "change_mode"};
    const char* wheel_states[]
        = {"emergency", "ready", "stand_down", "wheel_loco", "drift", "handstand", "change_mode"};

    const char** states = is_wheel ? wheel_states : quad_states;
    const int n_states = is_wheel ? static_cast<int>(sizeof(wheel_states) / sizeof(wheel_states[0]))
                                  : static_cast<int>(sizeof(quad_states) / sizeof(quad_states[0]));
    const int n_actions = is_wheel ? 0 : kNumAtomicActions;
    const int n = n_states + n_actions;

    std::cout << "Available states:" << std::endl;
    for (int i = 0; i < n_states; ++i)
        std::cout << "  " << i << ". " << states[i] << std::endl;
    if (n_actions > 0) {
        std::cout << "Atomic actions:" << std::endl;
        for (int i = 0; i < n_actions; ++i)
            std::cout << "  " << n_states + i << ". " << kAtomicActions[i] << std::endl;
    }

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

    std::string target = choice < n_states ? states[choice] : kAtomicActions[choice - n_states];

    return run_action(target) ? 0 : 1;
}
