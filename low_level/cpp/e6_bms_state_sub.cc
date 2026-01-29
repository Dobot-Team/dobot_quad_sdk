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
        return;  // Only output every 500ms
    }
    last_time = now;
    
    const BmsState_& bms = state.bms_state();
    
    std::cout << "\r\033[K";
    std::cout << "Received BMS State #" << count << std::endl
              << "Battery Level: " << bms.battery_level() << std::endl
              << "Battery ID: " << bms.bat_id() << std::endl
              << "BMS work time: " << bms.bms_work_time() << std::endl
              << "BMS current: " << bms.battery_now_current() << std::endl
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