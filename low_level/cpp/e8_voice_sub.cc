/**
 * VoiceState Subscription Example (e9)
 *
 * Functionality: Subscribe to `rt/voice/state` topic and receive audio stream data.
 *
 * Compilation:
 *   g++ -o e9_voice_sub e9_voice_sub.cc \
 *       -I/path/to/dds/include \
 *       -I/path/to/dds_middleware/include \
 *       -L/path/to/dds/lib \
 *       -lddscxx -lstdc++
 *
 * Usage:
 *   ./e9_voice_sub
 */

#include <iostream>
#include <memory>
#include <thread>
#include <chrono>
#include "dds_middleware.hpp"
#include "voice_state.hpp"

using namespace dds_middleware;
using namespace dobotmh4::msg::dds_;

/**
 * VoiceState message callback function
 * Called when a VoiceState message is received
 */
void voiceStateCallback(const VoiceState_& voice_state)
{
    std::cout << "Received VoiceState message:" << std::endl;
    std::cout << "  Data size: " << voice_state.data_().size() << " bytes" << std::endl;
    std::cout << "  Sound source direction: " << voice_state.angle_() << " degrees" << std::endl;
    std::cout << "---" << std::endl;
}

int main()
{
    try {
        // Create DDS middleware instance
        std::shared_ptr<DDSMiddleware> middleware = std::make_shared<DDSMiddleware>(0);

        // Configure QoS
        dds_middleware::QoSProfile qos_profile;
        qos_profile.reliability = dds_middleware::ReliabilityPolicy::BEST_EFFORT;
        qos_profile.history = dds_middleware::HistoryPolicy::KEEP_LAST;
        qos_profile.history_depth = 1;
        qos_profile.durability = dds_middleware::DurabilityPolicy::VOLATILE;

        // Subscribe to VoiceState topic
        const std::string topic_name = "rt/voice/state";
        std::cout << "Starting DDS C++ VoiceState subscriber..." << std::endl;
        std::cout << "Subscribing to topic: " << topic_name << std::endl;

        auto voice_state_sub
            = middleware->create_subscription<VoiceState_>(topic_name, voiceStateCallback, qos_profile);

        std::cout << "VoiceState subscriber started, waiting for voice state messages..." << std::endl;
        std::cout << "Press Ctrl+C to exit" << std::endl;

        // Keep the program running to receive messages
        while (true) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }

        return 0;

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
}
