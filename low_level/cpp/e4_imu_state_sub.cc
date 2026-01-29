#include <iostream>
#include <memory>
#include <thread>
#include <chrono>
#include "dds_middleware.hpp"
#include "lower_state.hpp"

using namespace dobotmh4::msg::dds_;

void lowerStateCallback(const LowerState_& state) {
    static int count = 0;
    static auto last_time = std::chrono::steady_clock::now();
    count++;
    
    auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration_cast<std::chrono::milliseconds>(now - last_time).count() < 500) {
        return;  // print per 500ms
    }
    last_time = now;
    
    const IMUState_& imu = state.imu_state();
    
    std::cout << "\r\033[K";
    std::cout << "Received LowerState #" << count << std::endl
              << "Quaternion (dimensionless): [" << imu.quaternion()[0] << ", " << imu.quaternion()[1] << ", " << imu.quaternion()[2] << ", " << imu.quaternion()[3] << "]" << std::endl
              << "Gyroscope (rad/s): [" << imu.gyroscope()[0] << ", " << imu.gyroscope()[1] << ", " << imu.gyroscope()[2] << "]" << std::endl
              << "Accelerometer (m/s²): [" << imu.accelerometer()[0] << ", " << imu.accelerometer()[1] << ", " << imu.accelerometer()[2] << "]" << std::endl
              << "RPY (rad): [" << imu.rpy()[0] << ", " << imu.rpy()[1] << ", " << imu.rpy()[2] << "]" << std::endl
              << std::endl
              << std::endl
              << std::flush;
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
