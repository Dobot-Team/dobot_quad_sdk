#include "dds_middleware.hpp"
#include "lower_cmd.hpp"
#include "lower_state.hpp"
#include <array>
#include <atomic>
#include <cmath>
#include <iostream>
#include <unistd.h>

using namespace dds_middleware;
using namespace dobotmh4::msg::dds_;

const int NUM_MOTORS = 12;
const std::array<int, 12> abs2Hw = {0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14};
const std::array<double, 16> motor_offset
    = {-0.05, -0.5, 1.17, 0.0, 0.05, -0.5, 1.17, 0.0, -0.05, 0.5, -1.17, 0.0, 0.05, 0.5, -1.17, 0.0};

std::array<double, 16> q_init = {0.0};
std::atomic<int> q_init_count {0};

void lowerStateCallback(const LowerState_& state)
{
    if (q_init_count < 10) {
        // Subtract motor_offset when reading to get real joint angle
        for (int i = 0; i < NUM_MOTORS; ++i) {
            int hw = abs2Hw[i];
            q_init[hw] = state.motor_state()[hw].q() - motor_offset[hw];
        }
        q_init_count++;
        if (q_init_count == 10) {
            std::cout << "Initial position collection completed: ";
            for (int i = 0; i < NUM_MOTORS; ++i)
                std::cout << q_init[abs2Hw[i]] << " ";
            std::cout << std::endl;
        }
    }
}

// Damping mode: protect robot
LowerCmd_ createDampCmd()
{
    LowerCmd_ cmd;
    for (int i = 0; i < NUM_MOTORS; ++i) {
        int hw = abs2Hw[i];
        cmd.motor_cmd()[hw].mode(0);
        cmd.motor_cmd()[hw].q(0.0 + motor_offset[hw]);
        cmd.motor_cmd()[hw].dq(0.0f);
        cmd.motor_cmd()[hw].tau(0.0f);
        cmd.motor_cmd()[hw].kp(0.0f);
        cmd.motor_cmd()[hw].kd(0.5f);
    }
    return cmd;
}

// Swing mode
LowerCmd_ createSwingCmd(double s)
{
    LowerCmd_ cmd;
    for (int i = 0; i < NUM_MOTORS; ++i) {
        int hw = abs2Hw[i];
        // Add motor_offset when sending
        double qdes = q_init[hw] + std::sin(2 * M_PI * s) * 0.2 + motor_offset[hw];
        cmd.motor_cmd()[hw].mode(0);
        cmd.motor_cmd()[hw].q(qdes);
        cmd.motor_cmd()[hw].dq(0.0f);
        cmd.motor_cmd()[hw].tau(0.0f);
        cmd.motor_cmd()[hw].kp(30.0f);
        cmd.motor_cmd()[hw].kd(1.2f);
    }
    return cmd;
}

int main()
{
    auto middleware = std::make_shared<DDSMiddleware>(0);

    dds_middleware::QoSProfile custom_qos;
    custom_qos.reliability = dds_middleware::ReliabilityPolicy::RELIABLE;
    custom_qos.durability = dds_middleware::DurabilityPolicy::VOLATILE;
    custom_qos.history = dds_middleware::HistoryPolicy::KEEP_LAST;
    custom_qos.history_depth = 1;

    auto pub = middleware->create_publisher<LowerCmd_>("rt/lower/cmd", custom_qos);
    auto sub = middleware->create_subscription<LowerState_>(
        "rt/lower/state", lowerStateCallback, dds_middleware::QoSProfile::SensorData());

    std::cout << "Waiting for initial position collection (10 times)..." << std::endl;
    while (q_init_count < 10)
        usleep(1000);

    std::cout << "Starting control loop" << std::endl;

    for (int iter = 0; iter < 6000; ++iter) {
        if (iter < 10) {
            // First 10 iterations: lock initial position (already completed in callback)
            pub->publish(createDampCmd());
            if (iter == 0)
                std::cout << "[" << iter << "] Initialization phase" << std::endl;
        } else if (iter < 5000) {
            // Swing phase: iter 10 to 4999
            double s = double(iter - 1000) / 500.0;
            pub->publish(createSwingCmd(s));
            if (iter == 10)
                std::cout << "[" << iter << "] Starting swing" << std::endl;
        } else {
            // Completion phase: switch to damping mode
            pub->publish(createDampCmd());
            if (iter == 5000)
                std::cout << "[" << iter << "] Swing completed, entering damping mode" << std::endl;
            exit(0);
        }
        usleep(2200);
    }

    std::cout << "Control sequence completed" << std::endl;
    return 0;
}