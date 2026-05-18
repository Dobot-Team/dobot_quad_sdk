// Example 9: Combo sequence — Arduino-style sequential calls.
// Each function blocks until the motion completes (scenario done signal).
// You can add sleeps between calls and even run them in a loop.
// Usage: ./e9_combo_sequence [server_address]

#include "robot_client.h"

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);

    if (client.is_quad_wheel()) {
        std::cout << "\n=== Combo Sequence Demo (Wheel) ===" << std::endl;

        // 1) 基础状态切换 + 构型切换
        client.passive();
        client.ready();
        client.wheel_loco();
        client.change_mode();
        client.change_mode();

        // 2) 前后左右各 1 米
        client.walk_forward(1.0f);
        client.walk_backward(1.0f);
        client.move_left(1.0f);
        client.move_right(1.0f);

        // 3) 左右转：90° 和 180°
        client.rotate_left(90.0f);
        client.rotate_right(90.0f);

        // 4) 转圈 1 圈
        client.circle("left", 1);

        // 5) 轮足专用状态切换
        client.drift();
        client.wheel_loco();
        client.handstand();

        // 6) 结束
        client.stand_down();

        std::cout << "Done." << std::endl;
        return 0;
    }

    std::cout << "\n=== Combo Sequence Demo (Full) ===" << std::endl;

    // 1) 基础状态切换 + 构型切换
    client.passive();
    client.ready();
    client.balance_stand();
    client.walk();
    client.rl();
    client.change_mode();
    client.change_mode();

    // 2) 前后左右各 1 米
    client.walk_forward(1.0f);
    client.walk_backward(1.0f);
    client.move_left(1.0f);
    client.move_right(1.0f);

    // 3) 左右转：90° 和 180°
    client.rotate_left(90.0f);
    client.rotate_left(180.0f);
    client.rotate_right(90.0f);
    client.rotate_right(180.0f);

    // 4) 转圈 1 圈
    client.circle("left", 1);

    // 5) 单轴平衡动作（dynamic + static）
    client.balance_stand();
    client.balance_pitch(15.0f, 2.0f, "dynamic");
    client.balance_pitch(-15.0f, 2.5f, "static");
    client.balance_yaw(20.0f, 2.0f, "dynamic");
    client.balance_yaw(-20.0f, 2.5f, "static");
    client.balance_roll(15.0f, 2.0f, "dynamic");
    client.balance_roll(-15.0f, 2.5f, "static");
    client.balance_height(-0.05f, 2.0f, "dynamic");
    client.balance_height(-0.08f, 2.5f, "static");

    // 6) 两个复合平衡动作
    client.dynamic_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.static_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.balance_neutral();

    // 7) 其他基础动作切换
    client.wave();
    client.dance();
    client.recovery();
    client.stand_down();

    std::cout << "Done." << std::endl;
    return 0;
}
