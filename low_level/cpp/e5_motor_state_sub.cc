#include <iostream>
#include <memory>
#include <thread>
#include <chrono>
#include <functional>
#include "dds_middleware.hpp"
#include "lower_state.hpp"

using namespace dobotmh4::msg::dds_;

void lowerStateCallback(const LowerState_& state) {
    static int count = 0;
    static auto last_time = std::chrono::steady_clock::now();
    count++;
    
    auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration_cast<std::chrono::milliseconds>(now - last_time).count() < 500) {
        return;  // Only output every 500ms
    }
    last_time = now;
    
    std::cout << "\r\033[K";
    std::cout << "Received Motor States #" << count << std::endl;
    for (int i = 0; i < 16; ++i) {
        const MotorState_& motor = state.motor_state()[i];
        std::cout << "Motor[" << i << "]: mode=" << static_cast<int>(motor.mode()) 
                  << ", q(rad)=" << motor.q() 
                  << ", dq(rad/s)=" << motor.dq() 
                  << ", ddq(rad/s²)=" << motor.ddq() 
                  << ", tau_est(N·m)=" << motor.tau_est() 
                  << ", q_raw(rad)=" << motor.q_raw() 
                  << ", dq_raw(rad/s)=" << motor.dq_raw() 
                  << ", ddq_raw(rad/s²)=" << motor.ddq_raw() 
                  << ", motor_temp(°C)=" << static_cast<int>(motor.motor_temp()) 
                  << std::endl;
    }
    std::cout << std::flush;
}

int main() {
    std::shared_ptr<dds_middleware::DDSMiddleware> middleware = 
        std::make_shared<dds_middleware::DDSMiddleware>(0);

    auto lower_state_sub = middleware->create_subscription<LowerState_>(
        "rt/lower/state", 
        lowerStateCallback,
        dds_middleware::QoSProfile::SensorData()
    );

    while (true) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    return 0;
}
