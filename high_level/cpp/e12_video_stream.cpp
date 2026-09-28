// =============================================================================
// Example: wireless camera video stream (robot.video)
//
// Usage:
//   ./e12_video_stream [ip[:port]] [--camera front|rear] [--seconds N] [--pull]
//
// Demonstrates:
//   * open(): one class, no stream handle, **returns the RTSP address**
//   * on_state_change(): notice drops / external stop / automatic recovery
//   * get_stream_info(): self-check state / owner / bitrate
//   * close(): only stops the stream when nobody else is watching
//   * --pull: shell out to ffmpeg/ffplay with the returned address, showing that
//     media handling is entirely the user's business
//
// Build:
//   include "robot_client.h" plus "video/video_client.h" and link threads
//   (`proto_lib` + `Threads::Threads` in CMake); the video code itself is
//   header-only, there is no library to link.
//
// Notes:
//   * The SDK opens no media connection: open() returns an address and your own
//     player shows the picture.
//   * open() guarantees that the camera is streaming and carrying data. It
//     cannot promise that your decoder will produce frames.
//   * The phone app and this SDK can watch the same camera; close() leaves the
//     stream running while somebody else is watching.
// =============================================================================

#include "video/video_client.h"

#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

namespace {

struct Options {
    std::string address = "192.168.5.2:50051";
    robot::video::CameraId camera = robot::video::CameraId::FrontRgb;
    double seconds = 6.0;
    bool pull = false; ///< also pull the address once with ffmpeg
};

void print_usage()
{
    std::cout << "Usage: e12_video_stream [ip[:port]] [--camera front|rear] [--seconds N] [--pull]\n";
}

bool parse_args(int argc, char** argv, Options* options)
{
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            print_usage();
            return false;
        }
        if (arg == "--camera" && i + 1 < argc) {
            const std::string value = argv[++i];
            if (value == "front") {
                options->camera = robot::video::CameraId::FrontRgb;
            } else if (value == "rear") {
                options->camera = robot::video::CameraId::RearRgb;
            } else {
                std::cerr << "Unknown camera: " << value << " (use front or rear)\n";
                return false;
            }
        } else if (arg == "--seconds" && i + 1 < argc) {
            options->seconds = std::atof(argv[++i]);
        } else if (arg == "--pull") {
            options->pull = true;
        } else if (!arg.empty() && arg[0] == '-') {
            std::cerr << "Unknown option: " << arg << "\n";
            print_usage();
            return false;
        } else {
            options->address = arg;
        }
    }
    return true;
}

/// Opens the returned address with an external player: media handling is
/// completely outside the SDK (ffprobe when available, ffplay otherwise).
///
/// \return true when the address could be opened, i.e. it is usable as delivered
bool pull_once(const std::string& uri, double seconds)
{
    std::string command;
    if (std::system("command -v ffprobe >/dev/null 2>&1") == 0) {
        command = "ffprobe -v error -rtsp_transport tcp -select_streams v:0 "
                  "-show_entries stream=codec_name,width,height -of default=nw=1 \""
            + uri + "\"";
    } else if (std::system("command -v ffplay >/dev/null 2>&1") == 0) {
        command = "ffplay -hide_banner -rtsp_transport tcp -fflags nobuffer -flags low_delay "
                  "-framedrop -autoexit -t " + std::to_string(static_cast<int>(seconds))
            + " \"" + uri + "\"";
    } else {
        std::cout << "[pull] no ffprobe / ffplay on this machine; open the address with\n"
                     "       your own player\n";
        return false;
    }
    std::cout << "[pull] $ " << command << std::endl;
    return std::system(command.c_str()) == 0;
}

} // namespace

int main(int argc, char** argv)
{
    Options options;
    if (!parse_args(argc, argv, &options)) {
        return 1;
    }

    try {
        robot::Client client(options.address);
        robot::video::Manager& video = client.video();

        // Stream events: drops, stops from outside this program, recoveries.
        const std::function<void()> unsubscribe = video.on_state_change(
            [](const robot::video::StreamEvent& event) {
                std::cout << "[state] " << event.to_string() << std::endl;
            });

        std::cout << "=== cameras: ";
        const std::vector<robot::video::CameraId> cameras = video.list_cameras();
        for (size_t i = 0; i < cameras.size(); ++i) {
            std::cout << (i > 0 ? ", " : "") << robot::video::camera_name(cameras[i]);
        }
        std::cout << " ===\n";

        std::cout << "=== open(" << robot::video::camera_name(options.camera)
                  << ") (blocks until data is flowing) ===\n";
        const double started = robot::video::monotonic_s();
        const std::string uri = video.open(options.camera);
        std::cout << std::fixed << std::setprecision(2)
                  << "open() took " << (robot::video::monotonic_s() - started) << " s\n";
        std::cout << "RTSP address: " << uri << "\n";
        std::cout << "State: " << video.get_stream_info(options.camera).to_string() << "\n";

        if (options.pull) {
            pull_once(uri, options.seconds);
        } else {
            std::cout << "Open the address with your own player, for example\n"
                         "  ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay "
                      << uri << "\n";
        }

        // Watch for a while: stream events and bitrate.
        const double deadline = robot::video::monotonic_s() + options.seconds;
        while (robot::video::monotonic_s() < deadline) {
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
            const robot::video::CameraStreamInfo info = video.get_stream_info(options.camera);
            std::cout << "[watch] state=" << robot::video::to_string(info.state)
                      << " owner=" << robot::video::to_string(info.owner) << " bitrate="
                      << static_cast<long long>(info.bitrate_kbps) << " kbps\n";
        }

        unsubscribe();

        // close() checks whether anyone else is watching before stopping anything.
        video.close(options.camera);
        std::cout << "State after close(): "
                  << video.get_stream_info(options.camera).to_string() << "\n";
    } catch (const robot::video::VideoError& exc) {
        // Video works even when the gRPC side is unavailable: this error is about
        // the video path only, and its message says what to try next.
        std::cerr << "[error] " << exc.what() << std::endl;
        return 1;
    } catch (const std::exception& exc) {
        std::cerr << "[error] " << exc.what() << std::endl;
        return 1;
    }

    std::cout << "=== done ===\n";
    return 0;
}
