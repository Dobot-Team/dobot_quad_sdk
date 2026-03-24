// Example 5: Get full robot state telemetry.
// Usage: ./e5_robot_state [server_address]

#include "robot_client.h"
#include <iomanip>

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    auto res = client.get_state();

    if (!res.success()) {
        std::cerr << "Failed: " << res.message() << std::endl;
        return 1;
    }

    std::cout << "Current state: " << res.current_state() << "\n" << std::endl;
    std::cout << "Speed ratio: " << res.current_speed_ratio() << std::endl;
    std::cout << "Obstacle avoidance: " << (res.obstacle_avoidance_enabled() ? "enabled" : "disabled") << "\n"
              << std::endl;

    const auto& s = res.robot_state();
    auto print = [](const google::protobuf::RepeatedField<float>& a, const std::string& label) {
        std::cout << label << ": [";
        for (int i = 0; i < a.size(); ++i) {
            if (i)
                std::cout << ", ";
            std::cout << std::fixed << std::setprecision(2) << a[i];
        }
        std::cout << "]" << std::endl;
    };

    std::cout << "Leg Joints:" << std::endl;
    print(s.jpos_leg(), "  pos [rad]");
    print(s.jpos_leg_des(), "  pos_des [rad]");
    print(s.jvel_leg(), "  vel [rad/s]");
    print(s.jvel_leg_des(), "  vel_des [rad/s]");
    print(s.jtau_leg(), "  tau [Nm]");
    print(s.jtau_leg_des(), "  tau_des [Nm]");

    std::cout << "\nBody:" << std::endl;
    print(s.pos_body(), "  pos [m]");
    print(s.vel_body(), "  vel [m/s]");
    print(s.acc_body(), "  acc [m/s^2]");
    print(s.omega_body(), "  omega [rad/s]");
    print(s.ori_body(), "  rpy [rad]");

    std::cout << "\nContact:" << std::endl;
    print(s.grf_left(), "  left [N]");
    print(s.grf_right(), "  right [N]");
    print(s.grf_vertical_filtered(), "  vertical [N]");

    return 0;
}
