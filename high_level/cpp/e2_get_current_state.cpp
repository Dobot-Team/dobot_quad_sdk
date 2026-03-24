// Example 2: Get the current FSM state name.
// Usage: ./e2_get_current_state [server_address]

#include "robot_client.h"

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    auto state = client.get_current_state_name();

    if (state.empty()) {
        std::cerr << "Failed to get state" << std::endl;
        return 1;
    }

    std::cout << "Current state: " << state << std::endl;
    return 0;
}
