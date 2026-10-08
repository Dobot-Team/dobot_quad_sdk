#include "dds_middleware.hpp"
#include "voice_cmd.hpp"
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using namespace dds_middleware;
using namespace dobotmh4::msg::dds_;

// Populate the std_msgs Header with the current wall-clock timestamp.
// The refactored VoiceCmd_ IDL (dds-middleware >= 0.23.x) carries a Header,
// matching the canonical voice_cmd_publisher example.
static void fill_header(VoiceCmd_& voice_cmd)
{
    auto now = std::chrono::system_clock::now().time_since_epoch();
    auto sec = std::chrono::duration_cast<std::chrono::seconds>(now).count();
    auto nsec = std::chrono::duration_cast<std::chrono::nanoseconds>(now).count() % 1000000000;
    voice_cmd.header().stamp_().sec_(static_cast<int32_t>(sec));
    voice_cmd.header().stamp_().nanosec_(static_cast<uint32_t>(nsec));
    voice_cmd.header().frame_id_("voice_cmd");
}

// Background thread that continuously captures PCM audio from the microphone
// (24kHz, mono, 16bit) and keeps only the most recent chunk for low latency.
class AudioCaptureThread
{
public:
    explicit AudioCaptureThread(int chunk_duration_ms = 100)
        : chunk_duration_ms_(chunk_duration_ms)
        , running_(true)
    {
    }

    void run()
    {
        FILE* pipe = popen("arecord -q -t raw -f S16_LE -c1 -r24000", "r");
        if (!pipe) {
            std::cerr << "arecord not found or failed to start" << std::endl;
            return;
        }

        // 24kHz * 16bit mono = 2 bytes/sample, e.g. 100ms -> 4800 bytes
        int bytes_per_chunk = (24000 * chunk_duration_ms_ / 1000) * 2;
        std::vector<uint8_t> buffer(bytes_per_chunk);

        while (running_) {
            size_t read_bytes = fread(buffer.data(), 1, bytes_per_chunk, pipe);
            if (read_bytes > 0) {
                std::lock_guard<std::mutex> lock(mutex_);
                latest_.assign(buffer.begin(), buffer.begin() + read_bytes);
                has_data_ = true;
            } else if (feof(pipe)) {
                break;
            }
        }

        pclose(pipe);
    }

    bool get_audio(std::vector<uint8_t>& data)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!has_data_) {
            return false;
        }
        data = std::move(latest_);
        has_data_ = false;
        return true;
    }

    void stop() { running_ = false; }

private:
    int chunk_duration_ms_;
    std::atomic<bool> running_;
    std::mutex mutex_;
    std::vector<uint8_t> latest_;
    bool has_data_ = false;
};

int main(int argc, char** argv)
{
    if (argc < 2) {
        std::cout << "Usage: " << argv[0] << " <mode> [args]" << std::endl;
        std::cout << "  Modes:" << std::endl;
        std::cout << "    file <path_on_robot>            Play an audio file on the robot" << std::endl;
        std::cout << "    streaming                       Stream audio from local microphone" << std::endl;
        std::cout << "  Example:" << std::endl;
        std::cout << "    " << argv[0] << " file /home/dobot/assets/demo.wav" << std::endl;
        std::cout << "    " << argv[0] << " streaming" << std::endl;
        return 1;
    }

    std::string mode = argv[1];

    auto middleware = std::make_shared<DDSMiddleware>(0);

    QoSProfile qos;
    qos.reliability = ReliabilityPolicy::RELIABLE;
    qos.history = HistoryPolicy::KEEP_LAST;
    qos.history_depth = 5;
    qos.durability = DurabilityPolicy::VOLATILE;

    auto publisher = middleware->create_publisher<VoiceCmd_>("rt/voice/cmd", qos);

    std::cout << "Mode: " << mode << ", QoS: RELIABLE, KEEP_LAST(5), VOLATILE" << std::endl;

    if (mode == "file") {
        if (argc < 3) {
            std::cerr << "Error: file mode requires a path argument." << std::endl;
            std::cerr << "  " << argv[0] << " file <path_on_robot>" << std::endl;
            return 1;
        }
        std::string file_path = argv[2];

        VoiceCmd_ voice_cmd;
        fill_header(voice_cmd);
        voice_cmd.priority(VoicePriority_::kNormal); // kNormal: ordinary audio file
        voice_cmd.task_id("e7_voice_pub");
        voice_cmd.type("file");
        voice_cmd.path(file_path);
        voice_cmd.data().clear();
        voice_cmd.flag(false); // stream-end flag, unused in file mode

        std::cout << "Waiting for DDS discovery (1s)..." << std::endl;
        std::this_thread::sleep_for(std::chrono::seconds(1));
        publisher->publish(voice_cmd);
        std::cout << "Published VoiceCmd (file): " << voice_cmd.path() << std::endl;
        std::this_thread::sleep_for(std::chrono::seconds(1)); // let the sample flush before exit
    } else if (mode == "streaming") {
        std::cout << "Streaming mode: capture and publish from microphone (low-latency)" << std::endl;

        AudioCaptureThread capture_thread(100); // 100ms chunks
        std::thread audio_thread(&AudioCaptureThread::run, &capture_thread);

        std::vector<uint8_t> audio;
        while (true) {
            if (!capture_thread.get_audio(audio)) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            VoiceCmd_ voice_cmd;
            fill_header(voice_cmd);
            voice_cmd.priority(VoicePriority_::kNormal); // kNormal: ordinary audio stream
            voice_cmd.task_id("e7_voice_pub");
            voice_cmd.type("streaming");
            voice_cmd.path("");
            voice_cmd.data(audio);
            voice_cmd.flag(false); // false: stream not finished yet

            publisher->publish(voice_cmd);
            std::cout << "Published VoiceCmd (streaming): " << voice_cmd.data().size() << " bytes" << std::endl;
        }

        capture_thread.stop();
        audio_thread.join();
    } else {
        std::cout << "Unknown mode, use 'file' or 'streaming'" << std::endl;
    }

    return 0;
}
