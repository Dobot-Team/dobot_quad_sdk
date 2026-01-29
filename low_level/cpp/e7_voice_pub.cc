#include "dds_middleware.hpp"
#include "voice_cmd.hpp"
#include <chrono>
#include <cstdio>
#include <iostream>
#include <string>
#include <thread>
#include <vector>
#include <queue>
#include <mutex>
#include <atomic>

using namespace dds_middleware;
using namespace dobotmh4::msg::dds_;

// Thread-safe queue for audio buffers
class AudioQueue
{
public:
    AudioQueue(size_t max_size = 2)
        : max_size_(max_size)
    {
    }

    void push(std::vector<uint8_t> data)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (queue_.size() >= max_size_) {
            queue_.pop(); // Drop oldest if full
        }
        queue_.push(std::move(data));
    }

    bool try_pop(std::vector<uint8_t>& data)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (queue_.empty()) {
            return false;
        }
        data = std::move(queue_.front());
        queue_.pop();
        return true;
    }

private:
    std::queue<std::vector<uint8_t>> queue_;
    std::mutex mutex_;
    size_t max_size_;
};

// Background thread for continuous low-latency audio capture
class AudioCaptureThread
{
public:
    AudioCaptureThread(int chunk_duration_ms = 100)
        : chunk_duration_ms_(chunk_duration_ms)
        , running_(true)
    {
    }

    void run()
    {
        int duration_sec_factor = chunk_duration_ms_; // e.g., 100 = 0.1 seconds

        FILE* pipe = popen("arecord -q -t raw -f S16_LE -c1 -r24000", "r");
        if (!pipe) {
            std::cerr << "arecord not found or failed to start" << std::endl;
            return;
        }

        // Calculate bytes per chunk (24kHz, 16bit, mono = 2 bytes per sample)
        // For 100ms: 24000 * 0.1 * 2 = 4800 bytes
        int bytes_per_chunk = (24000 * chunk_duration_ms_ / 1000) * 2;

        std::vector<uint8_t> buffer(bytes_per_chunk);
        size_t read_bytes = 0;

        while (running_) {
            read_bytes = fread(buffer.data(), 1, bytes_per_chunk, pipe);
            if (read_bytes > 0) {
                std::vector<uint8_t> chunk(buffer.begin(), buffer.begin() + read_bytes);
                audio_queue_.push(std::move(chunk));
            } else if (feof(pipe)) {
                break;
            }
        }

        pclose(pipe);
    }

    bool get_audio(std::vector<uint8_t>& data) { return audio_queue_.try_pop(data); }

    void stop() { running_ = false; }

private:
    AudioQueue audio_queue_;
    int chunk_duration_ms_;
    std::atomic<bool> running_;
};

// Capture audio chunk from microphone using arecord (24kHz, mono, 16bit PCM)
static std::vector<uint8_t> capture_audio_chunk()
{
    std::vector<uint8_t> data;
    FILE* pipe = popen("arecord -q -t raw -f S16_LE -c1 -r24000 -d0.1", "r");
    if (!pipe) {
        std::cerr << "arecord not found or failed to start, unable to perform streaming" << std::endl;
        return data;
    }

    std::vector<uint8_t> buffer(4096);
    size_t read_bytes = 0;
    while ((read_bytes = fread(buffer.data(), 1, buffer.size(), pipe)) > 0) {
        data.insert(data.end(), buffer.begin(), buffer.begin() + static_cast<long>(read_bytes));
    }
    pclose(pipe);
    return data;
}

int main(int argc, char** argv)
{
    std::string mode = (argc > 1) ? argv[1] : "file"; // "file" or "streaming"

    std::shared_ptr<DDSMiddleware> middleware = std::make_shared<DDSMiddleware>(0);

    QoSProfile qos;
    qos.reliability = ReliabilityPolicy::RELIABLE;
    qos.history = HistoryPolicy::KEEP_LAST;
    qos.history_depth = 5; // Align with dds_publisher.py
    qos.durability = DurabilityPolicy::VOLATILE;

    auto publisher = middleware->create_publisher<VoiceCmd_>("rt/voice/cmd", qos);

    std::cout << "Mode: " << mode << std::endl;
    std::cout << "QoS: RELIABLE, KEEP_LAST(5), VOLATILE" << std::endl;

    if (mode == "file") {
        // std::string file_path = "/root/test1.wav";
        std::string file_path = "/root/test2.flac";
        // std::string file_path = "/root/test3.mp3";

        std::cout << "File mode: publish local file paths cyclically" << std::endl;
        VoiceCmd_ voice_cmd;
        voice_cmd.type("file");
        voice_cmd.path(file_path);
        voice_cmd.data().clear();
        sleep(1);
        publisher->publish(voice_cmd);

        std::cout << "Published VoiceCmd (file)" << std::endl;
        std::cout << "  Path: " << voice_cmd.path() << std::endl;
        std::cout << "  Data size: 0 bytes" << std::endl;
        std::cout << "---------------------------" << std::endl;

        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    if (mode == "streaming") {
        std::cout << "Streaming mode: capture and publish from microphone (low-latency)" << std::endl;

        // Start background audio capture thread
        AudioCaptureThread capture_thread(100); // 100ms chunks
        std::thread audio_thread(&AudioCaptureThread::run, &capture_thread);

        std::vector<uint8_t> audio;
        while (true) {
            // Get audio from capture queue (non-blocking)
            if (capture_thread.get_audio(audio)) {
                VoiceCmd_ voice_cmd;
                voice_cmd.type("streaming");
                voice_cmd.path("");
                voice_cmd.data(audio);

                publisher->publish(voice_cmd);

                std::cout << "Published VoiceCmd (streaming)" << std::endl;
                std::cout << "  Data size: " << voice_cmd.data().size() << " bytes" << std::endl;
                std::cout << "---------------------------" << std::endl;
                // No sleep - publish immediately when audio is available
            } else {
                // No audio available, brief sleep before retry
                std::this_thread::sleep_for(std::chrono::milliseconds(10)); // 10ms instead of 200ms
            }
        }

        capture_thread.stop();
        audio_thread.join();
    }

    std::cout << "Unknown mode, use 'file' or 'streaming'" << std::endl;
    return 0;
}