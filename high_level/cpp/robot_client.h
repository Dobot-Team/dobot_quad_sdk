#pragma once
// =============================================================================
// Robot gRPC Client Library
// Simplifies connection, execution, and cancellation for all examples.
//
// Usage:
//   robot::Client client("192.168.5.2:50051");
//   auto req = robot::make_request("demo");
//   req.mutable_sequence()->add_motions()->set_motion_id("balance_stand");
//   client.execute(req);
// =============================================================================

#include "grpc_service.grpc.pb.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <grpcpp/grpcpp.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <map>
#include <memory>
#include <tuple>

namespace robot {

namespace video {
class Manager; // robot.video (camera video streaming), see video/video_client.h
} // namespace video

class Client; // Forward declaration for detail::g_safety_client

namespace detail {
static std::atomic<bool> g_interrupted {false};
static void signal_handler(int)
{
    g_interrupted.store(true);
}
static Client* g_safety_client = nullptr;
static std::atomic<bool> g_safety_triggered {false};
static void safety_signal_handler(int)
{
    g_safety_triggered.store(true);
    std::signal(SIGINT, SIG_DFL);
    std::exit(130);
}
} // namespace detail

// ---------------------------------------------------------------------------
// Parameter helpers: set typed parameters on a Motion proto
// ---------------------------------------------------------------------------

inline void set_param(grpc_comm::Motion* m, const std::string& key, float v)
{
    auto* p = m->add_parameters();
    p->set_key(key);
    p->set_float_value(v);
}

inline void set_param(grpc_comm::Motion* m, const std::string& key, int v)
{
    auto* p = m->add_parameters();
    p->set_key(key);
    p->set_int_value(v);
}

inline void set_param(grpc_comm::Motion* m, const std::string& key, const std::string& v)
{
    auto* p = m->add_parameters();
    p->set_key(key);
    p->set_string_value(v);
}

// ---------------------------------------------------------------------------
// Build an ExecuteSequenceRequest with sane defaults
// ---------------------------------------------------------------------------

inline grpc_comm::ExecuteSequenceRequest make_request(const std::string& name = "seq", bool loop = false)
{
    grpc_comm::ExecuteSequenceRequest req;
    auto* seq = req.mutable_sequence();
    seq->set_sequence_id(name);
    seq->set_sequence_name(name);
    seq->set_loop(loop);
    req.set_immediate_start(true);
    return req;
}

// ---------------------------------------------------------------------------
// Validation Utilities (reusable across all API methods)
// ---------------------------------------------------------------------------

/// Clamp speed ratio to [10, 100].
inline int clamp_speed_ratio(int ratio)
{
    return std::max(10, std::min(100, ratio));
}

/// Clamp distance to [0, 3] meters.
inline float clamp_distance(float d)
{
    return std::max(0.0f, std::min(3.0f, d));
}

/// Clamp angle to [0, 3600] degrees.
inline float clamp_angle(float a)
{
    return std::max(0.0f, std::min(3600.0f, a));
}

/// Clamp angle to [-180, 180] degrees for rotate_walk.
/// Negative angles represent counter-clockwise (left turn).
/// Positive angles represent clockwise (right turn).
inline float clamp_angle_signed(float a)
{
    return std::max(-180.0f, std::min(180.0f, a));
}

/// Clamp turns to [1, 10].
inline int clamp_turns(int t)
{
    return std::max(1, std::min(10, t));
}

/// Clamp amplitude to [lo, hi].
inline float clamp_amplitude(float a, float lo = -1.0f, float hi = 1.0f)
{
    return std::max(lo, std::min(hi, a));
}

/// Clamp balance value: degrees for rpy, meters for height.
inline float clamp_balance_value(float v, const std::string& axis)
{
    if (axis == "height")
        return std::max(-0.08f, std::min(0.0f, v)); // only downward
    if (axis == "yaw")
        return std::max(-11.5f, std::min(11.5f, v)); // degrees
    if (axis == "roll")
        return std::max(-17.0f, std::min(17.0f, v)); // degrees
    if (axis == "pitch")
        return std::max(-11.5f, std::min(11.5f, v)); // degrees
    return std::max(-11.5f, std::min(11.5f, v));     // fallback
}

/// Clamp single-axis/balance-sequence duration to [0.5, 5] seconds.
inline float clamp_balance_duration(float d)
{
    return std::max(0.5f, std::min(5.0f, d));
}

/// Clamp composite pose duration to [1, 5] seconds.
inline float clamp_pose_duration(float d)
{
    return std::max(1.0f, std::min(5.0f, d));
}

// ---------------------------------------------------------------------------
// VelocityStep: structured velocity command for velocity_sequence()
// ---------------------------------------------------------------------------

struct VelocityStep
{
    float vx = 0;       ///< forward (+) / backward (-) m/s
    float vy = 0;       ///< strafe left (+) / right (-) m/s
    float vyaw = 0;     ///< turn left (+) / right (-) rad/s
    float duration = 1; ///< seconds
};

inline std::string make_velocity_string(const std::vector<VelocityStep>& steps)
{
    std::string result;
    for (const auto& s : steps) {
        result += std::to_string(s.vx) + "," + std::to_string(s.vy) + "," + std::to_string(s.vyaw) + ","
                  + std::to_string(s.duration) + ";";
    }
    return result;
}

// ---------------------------------------------------------------------------
// BalanceMotion: one item in a balance_sequence() batch
// ---------------------------------------------------------------------------

struct BalanceMotion
{
    std::string motion_id;        ///< e.g. "balance_pitch", "balance_neutral"
    float value = 0;              ///< degrees for rpy, meters for height
    float duration = 2.0f;        ///< seconds
    std::string mode = "dynamic"; ///< "dynamic" or "static"
};

/// Leg and fill-light identifiers (maps to proto LegName).
enum class Leg {
    FL = 1,          ///< Front-left leg light
    FR = 2,          ///< Front-right leg light
    RL = 3,          ///< Rear-left leg light
    RR = 4,          ///< Rear-right leg light
    FILL_FRONT = 5,  ///< Front fill light
    FILL_BACK = 6    ///< Rear fill light
};

/// Predefined LED colors for convenience (maps to RGB via color_to_rgb).
enum class Color {
    OFF,
    RED,
    ORANGE,
    YELLOW,
    GREEN,
    CYAN,
    BLUE,
    PURPLE,
    WHITE
};

/// Per-leg RGB and brightness entry for batch SetLeds requests.
struct LegLedConfig {
    Leg leg;
    uint8_t r = 0;         ///< Red channel [0, 255]
    uint8_t g = 0;         ///< Green channel [0, 255]
    uint8_t b = 0;         ///< Blue channel [0, 255]
    int brightness = -1;   ///< Brightness [0, 255]; -1 keeps cached value
};

/// Convert a predefined Color to an (r, g, b) tuple.
inline std::tuple<uint8_t, uint8_t, uint8_t> color_to_rgb(Color color)
{
    switch (color) {
        case Color::RED:    return {255, 0, 0};
        case Color::ORANGE: return {255, 165, 0};
        case Color::YELLOW: return {255, 255, 0};
        case Color::GREEN:  return {0, 255, 0};
        case Color::CYAN:   return {0, 255, 255};
        case Color::BLUE:   return {0, 0, 255};
        case Color::PURPLE: return {128, 0, 128};
        case Color::WHITE:  return {255, 255, 255};
        case Color::OFF:    return {0, 0, 0};
        default: return {0, 0, 0};
    }
}

/// Convert a Leg enum value to the corresponding proto LegName.
inline grpc_comm::LegName leg_to_proto(Leg leg)
{
    switch (leg) {
        case Leg::FL: return grpc_comm::LEG_FL;
        case Leg::FR: return grpc_comm::LEG_FR;
        case Leg::RL: return grpc_comm::LEG_RL;
        case Leg::RR: return grpc_comm::LEG_RR;
        case Leg::FILL_FRONT: return grpc_comm::LEG_FILL_FRONT;
        case Leg::FILL_BACK: return grpc_comm::LEG_FILL_BACK;
        default: throw std::invalid_argument("Invalid Leg");
    }
}

/// Return true if @p leg is one of the four main leg lights (FL/FR/RL/RR).
inline bool is_leg_light(Leg leg)
{
    return leg == Leg::FL || leg == Leg::FR || leg == Leg::RL || leg == Leg::RR;
}

/// Reject fill lights for leg-LED set APIs.
inline void validate_leg_light(Leg leg)
{
    if (!is_leg_light(leg)) {
        throw std::invalid_argument(
            "Leg LED set APIs only support FL, FR, RL, RR; "
            "fill lights (FILL_FRONT/FILL_BACK) are not supported");
    }
}

/// Bake brightness into RGB for hardware that ignores the brightness field.
/// channel' = round(channel * brightness / 255). Logical RGB stays in cache.
inline std::tuple<uint8_t, uint8_t, uint8_t> scale_rgb_by_brightness(
    uint8_t r, uint8_t g, uint8_t b, uint8_t brightness)
{
    if (brightness >= 255)
        return {r, g, b};
    if (brightness == 0)
        return {0, 0, 0};
    auto scale = [brightness](uint8_t c) -> uint8_t {
        return static_cast<uint8_t>((static_cast<unsigned>(c) * brightness + 127u) / 255u);
    };
    return {scale(r), scale(g), scale(b)};
}

// ---------------------------------------------------------------------------
// Client: one-stop wrapper for the gRPC service
// ---------------------------------------------------------------------------

class Client
{
public:
    explicit Client(const std::string& addr = "192.168.5.2:50051")
    {
        stub_ = grpc_comm::gRPCService::NewStub(grpc::CreateChannel(addr, grpc::InsecureChannelCredentials()));
        // Seed local state from server, then ensure OA is on.
        // We track these locally because GetRobotState is eventually
        // consistent and may return stale values right after a Set* RPC.
        // 视频子系统需要裸 IP（RTSP :8554 / go2rtc :1984 / GControll :22000）
        {
            const auto colon = addr.rfind(':');
            video_host_ = colon == std::string::npos ? addr : addr.substr(0, colon);
        }
        auto res = get_state();
        speed_ratio_ = res.success() ? res.current_speed_ratio() : 50;
        obstacle_avoidance_ = true;
        // set_obstacle_avoidance(true);
    }

    // =====================================================================
    // Camera Video Streaming (robot.video)
    // =====================================================================

    /// Camera video streaming (robot.video).
    ///
    /// Independent of motion control: video goes over RTSP, not through the gRPC
    /// channel, so big media packets never hold up your motion commands. The
    /// object is created on first use, so programs that do not use the camera
    /// pay nothing for it.
    ///
    /// The SDK only switches the stream on and watches it: open() blocks until
    /// data is really flowing and returns an RTSP address; pulling, decoding and
    /// muxing are up to your own player.
    ///
    /// \code
    ///   std::string uri = client.video().open(robot::video::CameraId::FrontRgb);
    ///   // hand uri to ffplay / OpenCV / GStreamer
    ///   client.video().close_all();
    /// \endcode
    ///
    /// \note Include ``video/video_client.h`` to call this method; it is the
    ///       only extra header the video feature adds to this one. Programs
    ///       that never call video() do not compile the video code at all.
    ///       Forgetting it fails at link time with
    ///       ``undefined reference to `robot::Client::video()'``.
    video::Manager& video();

    // =====================================================================
    // Core RPC: Query
    // =====================================================================

    /// Get the list of available motions.
    grpc_comm::GetMotionsResponse get_motions()
    {
        grpc_comm::GetMotionsRequest req;
        grpc_comm::GetMotionsResponse res;
        grpc::ClientContext ctx;
        auto st = stub_->GetAvailableMotions(&ctx, req, &res);
        if (!st.ok())
            std::cerr << "RPC error: " << st.error_message() << std::endl;
        return res;
    }

    /// Get the current robot state (joints, body, contact, FSM state name,
    /// speed ratio, obstacle avoidance).
    grpc_comm::GetRobotStateResponse get_state()
    {
        grpc_comm::GetRobotStateRequest req;
        grpc_comm::GetRobotStateResponse res;
        grpc::ClientContext ctx;
        auto st = stub_->GetRobotState(&ctx, req, &res);
        if (!st.ok())
            std::cerr << "RPC error: " << st.error_message() << std::endl;
        return res;
    }

    /// Get the robot type string (e.g. "miniQuad" or "miniQuadW").
    /// Cached after first successful query.
    std::string get_robot_type()
    {
        if (robot_type_.empty()) {
            auto res = get_state();
            if (res.success())
                robot_type_ = res.robot_type();
        }
        return robot_type_;
    }

    /// Check if connected robot is MINI_QUAD (点足).
    bool is_quad() { return get_robot_type() == "miniQuad"; }

    /// Check if connected robot is MINI_QUAD_WHEEL (轮足).
    bool is_quad_wheel() { return get_robot_type() == "miniQuadW"; }

    /// Get just the current FSM state name.
    std::string get_current_state_name()
    {
        auto res = get_state();
        return res.success() ? res.current_state() : "";
    }

    /// Get the current speed ratio.
    int get_speed_ratio() { return speed_ratio_; }

    /// Get the current obstacle avoidance state.
    bool get_obstacle_avoidance() { return obstacle_avoidance_; }

    // =====================================================================
    // Core RPC: Configuration
    // =====================================================================

    /// Set speed ratio [10-100].
    grpc_comm::SetSpeedRatioResponse set_speed_ratio(int ratio)
    {
        ratio = clamp_speed_ratio(ratio);
        grpc_comm::SetSpeedRatioRequest req;
        grpc_comm::SetSpeedRatioResponse res;
        grpc::ClientContext ctx;
        req.set_speed_ratio(ratio);
        auto st = stub_->SetSpeedRatio(&ctx, req, &res);
        if (!st.ok())
            std::cerr << "RPC error: " << st.error_message() << std::endl;
        else
            speed_ratio_ = res.current_speed_ratio();
        return res;
    }

    /// Enable or disable obstacle avoidance.
    grpc_comm::SetObstacleAvoidanceResponse set_obstacle_avoidance(bool enable)
    {
        grpc_comm::SetObstacleAvoidanceRequest req;
        grpc_comm::SetObstacleAvoidanceResponse res;
        grpc::ClientContext ctx;
        req.set_enable(enable);
        auto st = stub_->SetObstacleAvoidance(&ctx, req, &res);
        if (!st.ok())
            std::cerr << "RPC error: " << st.error_message() << std::endl;
        else
            obstacle_avoidance_ = res.current_enabled();
        return res;
    }

    /// Enable/disable obstacle avoidance using "on"/"off".
    grpc_comm::SetObstacleAvoidanceResponse set_obstacle_avoidance(const std::string& enable)
    {
        std::string norm = enable;
        std::transform(norm.begin(), norm.end(), norm.begin(), ::tolower);
        if (norm == "on")
            return set_obstacle_avoidance(true);
        if (norm == "off")
            return set_obstacle_avoidance(false);
        throw std::invalid_argument("set_obstacle_avoidance only accepts bool or \"on\"/\"off\"");
    }

    // =====================================================================
    // Core RPC: Execution
    // =====================================================================

    /// Execute a motion sequence with real-time progress streaming.
    /// Returns true on success. Press Ctrl+C to cancel.
    /// @param show_progress If true, prints each progress update.
    bool execute(grpc_comm::ExecuteSequenceRequest& req, bool show_progress = true)
    {
        // Install signal handler for graceful cancellation during execution
        detail::g_interrupted.store(false);
        std::signal(SIGINT, detail::signal_handler);

        std::cout << "Running... (Ctrl+C to stop)" << std::endl;

        grpc::ClientContext ctx;
        auto reader = stub_->ExecuteSequence(&ctx, req);

        bool success = false;
        bool got_final = false;
        std::atomic<bool> stream_done {false};
        std::string last_printed_state;
        std::string last_error_msg;

        // Read stream in background thread
        std::thread reader_thread([&] {
            grpc_comm::SequenceProgress p;
            while (reader->Read(&p)) {
                if (p.is_final()) {
                    success = p.success();
                    got_final = true;
                    if (!p.success())
                        std::cerr << "Error: " << p.message() << std::endl;
                    break;
                }
                if (show_progress) {
                    // Only print when state changes to avoid spam
                    std::string line = "  [" + std::to_string(p.current_index() + 1) + "/"
                                       + std::to_string(p.total_motions()) + "] " + p.current_motion_id()
                                       + " | state: " + p.current_state();
                    if (!p.message().empty()) {
                        line += " (" + p.message() + ")";
                        // Track error-like messages from server
                        const auto& msg = p.message();
                        if (msg.find("reject") != std::string::npos || msg.find("failed") != std::string::npos
                            || msg.find("error") != std::string::npos || msg.find("not reached") != std::string::npos) {
                            last_error_msg = msg;
                        }
                    }
                    if (line != last_printed_state) {
                        std::cout << line << std::endl;
                        last_printed_state = line;
                    }
                }
            }
            stream_done.store(true);
        });

        // Main thread: poll for Ctrl+C
        while (!stream_done.load()) {
            if (detail::g_interrupted.exchange(false))
                ctx.TryCancel();
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        reader_thread.join();
        auto status = reader->Finish();

        // Restore signal handler (safety handler if enabled, else default)
        if (detail::g_safety_client)
            std::signal(SIGINT, detail::safety_signal_handler);
        else
            std::signal(SIGINT, SIG_DFL);

        if (status.error_code() == grpc::StatusCode::CANCELLED) {
            std::cout << "Cancelled." << std::endl;
            if (detail::g_safety_client) {
                detail::g_safety_triggered.store(true);
                std::exit(130);
            }
            return false;
        }
        if (!status.ok()) {
            std::cerr << "RPC error: " << status.error_message() << std::endl;
            return false;
        }
        if (success) {
            std::cout << "Done." << std::endl;
        } else {
            // Ensure user sees a failure message even if final msg was missing/empty
            if (!got_final && !last_error_msg.empty())
                std::cerr << "Error: " << last_error_msg << std::endl;
            else if (!got_final)
                std::cerr << "Error: execution failed (no final status received)" << std::endl;
        }
        return success;
    }

    // =====================================================================
    // State Switching – one-call wrappers
    // =====================================================================

    /// Switch to any state by name (e.g. "balance_stand").
    bool set_target_state(const std::string& state, bool show_progress = true)
    {
        std::string resolved = (state == "emergency") ? "passive" : state;
        auto req = make_request("switch_to_" + resolved);
        req.mutable_sequence()->add_motions()->set_motion_id(resolved);
        return execute(req, show_progress);
    }

    bool set_passive(bool sp = true) { return set_target_state_with_delay_("passive", 2, sp); }
    bool passive(bool sp = true) { return set_target_state_with_delay_("passive", 2, sp); }
    /// Alias: emergency stop (maps to passive)
    bool emergency(bool sp = true) { return passive(sp); }
    bool set_ready(bool sp = true) { return set_target_state_with_delay_("ready", 2, sp); }
    bool ready(bool sp = true) { return set_target_state_with_delay_("ready", 2, sp); }
    bool set_stand_down(bool sp = true) { return set_target_state_with_delay_("stand_down", 2, sp); }
    bool stand_down(bool sp = true) { return set_target_state_with_delay_("stand_down", 2, sp); }
    bool set_balance_stand(bool sp = true) { return set_target_state_with_delay_("balance_stand", 2, sp); }
    bool balance_stand(bool sp = true) { return set_target_state_with_delay_("balance_stand", 2, sp); }
    bool set_walk(bool sp = true) { return set_target_state_with_delay_("walk", 2, sp); }
    bool walk(bool sp = true) { return set_target_state_with_delay_("walk", 2, sp); }
    bool set_rl(bool sp = true) { return set_target_state_with_delay_("rl", 2, sp); }
    bool rl(bool sp = true) { return set_target_state_with_delay_("rl", 2, sp); }
    bool set_flying_trot(bool sp = true) { return set_target_state_with_delay_("flying_trot", 2, sp); }
    bool flying_trot(bool sp = true) { return set_target_state_with_delay_("flying_trot", 2, sp); }
    bool set_gongxi(bool sp = true) { return set_target_state_with_delay_("gongxi", 11.5, sp); }
    bool gongxi(bool sp = true) { return set_target_state_with_delay_("gongxi", 11.5, sp); }
    /// \deprecated The state was renamed to gongxi() in v1.3.0. Kept as a
    ///             forwarding alias so v1.2.0 client code keeps working.
    [[deprecated("choreo() has been renamed to gongxi(), use gongxi() instead")]]
    bool set_choreo(bool sp = true) { return set_gongxi(sp); }
    [[deprecated("choreo() has been renamed to gongxi(), use gongxi() instead")]]
    bool choreo(bool sp = true) { return gongxi(sp); }
    bool set_dance0(bool sp = true) { return dance0(sp); }
    bool dance0(bool sp = true) { return dance0(13, sp); }
    bool dance0(int duration_sec, bool sp = true)
    {
        duration_sec = validate_dance_duration_(duration_sec);
        return set_target_state_with_delay_("dance0", duration_sec, sp);
    }
    bool dance(bool sp = true) { return dance0(13, sp); }
    bool dance(int duration_sec, bool sp = true) { return dance0(duration_sec, sp); }
    bool set_wave(bool sp = true) { return set_target_state_with_delay_("wave", 2, sp); }
    bool wave(bool sp = true) { return wave(5, sp); }
    bool wave(int duration_sec, bool sp = true)
    {
        duration_sec = validate_non_negative_duration_(duration_sec, "wave duration");

        bool first_ok = set_target_state_with_delay_("wave", duration_sec, sp);
        if (!first_ok)
            return false;

        auto req = make_request("wave_again");
        req.mutable_sequence()->add_motions()->set_motion_id("wave");
        bool second_ok = execute(req, sp);
        if (!second_ok)
            return false;

        std::this_thread::sleep_for(std::chrono::seconds(2));
        return true;
    }
    bool wave_hand(bool sp = true) { return wave(5, sp); }
    bool wave_hand(int duration_sec, bool sp = true) { return wave(duration_sec, sp); }
    bool set_jump(bool sp = true) { return set_target_state_with_delay_("jump", 3, sp); }
    bool jump(bool sp = true) { return set_target_state_with_delay_("jump", 3, sp); }
    bool set_backflip(bool sp = true) { return set_target_state_with_delay_("backflip", 2, sp); }
    bool backflip(bool sp = true) { return set_target_state_with_delay_("backflip", 2, sp); }
    bool set_recovery(bool sp = true) { return set_target_state_with_delay_("recovery", 4, sp); }
    bool recovery(bool sp = true) { return set_target_state_with_delay_("recovery", 4, sp); }
    bool change_mode(bool show_progress = true)
    {
        auto req = make_request("change_mode");
        req.mutable_sequence()->add_motions()->set_motion_id("change_mode");
        return execute(req, show_progress);
    }

    // =====================================================================
    // Choreography Atomic Actions (MINI_QUAD only)
    // =====================================================================

    /// Trigger a choreography atomic action by name (case-insensitive).
    /// The server handles any state switching the action needs and returns
    /// to WALK when the action finishes; on success this call sleeps through
    /// the action duration plus a settle margin.
    /// @throws std::invalid_argument if the action name is unknown.
    bool atomic_action(const std::string& action, bool show_progress = true)
    {
        // Post-trigger sleep: action duration + ~1s settle margin.
        static const std::map<std::string, double> post_sleep_sec = {
            {"twirl_jump", 2.0},  // 跳跃转体 (mimic, 0.7s)
            {"diag_step", 7.0},   // 对角迈步 (mimic, 5.9s)
            {"hop_step", 4.0},    // 前腿蹦跳迈步 (mimic, 3.0s)
            {"groove", 9.0},      // 摇摆律动 (8s)
            {"bounce", 7.0},      // 点头弹跳 (6s)
            {"body_wave", 9.0},   // 身体波浪 (8s)
            {"hip_circle", 9.0},  // 扭屁股/臀画圆 (8s)
            {"head_circle", 9.0}, // 扭头/头画圆 (8s)
        };
        std::string norm = action;
        std::transform(norm.begin(), norm.end(), norm.begin(), ::tolower);
        auto it = post_sleep_sec.find(norm);
        if (it == post_sleep_sec.end())
            throw std::invalid_argument("Unknown atomic action '" + action + "'");
        return set_target_state_with_delay_(norm, it->second, show_progress);
    }

    bool set_twirl_jump(bool sp = true) { return atomic_action("twirl_jump", sp); }
    bool twirl_jump(bool sp = true) { return atomic_action("twirl_jump", sp); }
    bool set_diag_step(bool sp = true) { return atomic_action("diag_step", sp); }
    bool diag_step(bool sp = true) { return atomic_action("diag_step", sp); }
    bool set_hop_step(bool sp = true) { return atomic_action("hop_step", sp); }
    bool hop_step(bool sp = true) { return atomic_action("hop_step", sp); }
    bool set_groove(bool sp = true) { return atomic_action("groove", sp); }
    bool groove(bool sp = true) { return atomic_action("groove", sp); }
    bool set_bounce(bool sp = true) { return atomic_action("bounce", sp); }
    bool bounce(bool sp = true) { return atomic_action("bounce", sp); }
    bool set_body_wave(bool sp = true) { return atomic_action("body_wave", sp); }
    bool body_wave(bool sp = true) { return atomic_action("body_wave", sp); }
    bool set_hip_circle(bool sp = true) { return atomic_action("hip_circle", sp); }
    bool hip_circle(bool sp = true) { return atomic_action("hip_circle", sp); }
    bool set_head_circle(bool sp = true) { return atomic_action("head_circle", sp); }
    bool head_circle(bool sp = true) { return atomic_action("head_circle", sp); }

    // =====================================================================
    // State Switching – MINI_QUAD_WHEEL (轮足) wrappers
    // =====================================================================

    bool wheel_loco(bool sp = true) { return set_target_state_with_delay_("wheel_loco", 2, sp); }
    bool drift(bool sp = true) { return set_target_state_with_delay_("drift", 2, sp); }
    bool climb(bool sp = true) { return set_target_state_with_delay_("climb", 2, sp); }
    bool handstand(bool sp = true) { return set_target_state_with_delay_("handstand", 2, sp); }

    // =====================================================================
    // Velocity Sequence
    // =====================================================================

    /// Execute a velocity sequence.
    /// @param vel_seq  "vx,vy,vyaw,dur;..." format string.
    /// @param gait     "walk" or "flying_trot".
    /// @param speed_ratio  Speed ratio [10-100] or -1 to use current base.
    /// @param stand_down_after  Append stand_down at the end.
    bool velocity_sequence(const std::string& vel_seq, const std::string& gait = "walk", int speed_ratio = -1,
        bool stand_down_after = true, bool show_progress = true)
    {
        int prev_ratio = -1;
        if (speed_ratio >= 0) {
            prev_ratio = speed_ratio_;
            set_speed_ratio(clamp_speed_ratio(speed_ratio));
        }

        bool prev_oa = obstacle_avoidance_;
        // set_obstacle_avoidance(false);

        auto req = make_request("velocity_demo");
        auto* seq = req.mutable_sequence();
        auto* m = seq->add_motions();

        if (gait == "flying_trot")
            m->set_motion_id("flying_trot_velocity_seq");
        else if (gait == "walk")
            m->set_motion_id("walk_velocity_seq");
        else if (gait == "wheel_loco")
            m->set_motion_id("wheel_loco_velocity_seq");
        else
            throw std::invalid_argument("Unknown gait '" + gait + "'. Valid: walk, flying_trot, wheel_loco");

        set_param(m, "velocity_sequence", vel_seq);
        if (stand_down_after)
            seq->add_motions()->set_motion_id("stand_down");

        bool ok = execute(req, show_progress);
        // set_obstacle_avoidance(prev_oa);
        if (prev_ratio >= 0)
            set_speed_ratio(prev_ratio);
        return ok;
    }

    /// Overload accepting a vector of VelocityStep.
    bool velocity_sequence(const std::vector<VelocityStep>& steps, const std::string& gait = "walk",
        int speed_ratio = -1, bool stand_down_after = true, bool show_progress = true)
    {
        return velocity_sequence(make_velocity_string(steps), gait, speed_ratio, stand_down_after, show_progress);
    }

    // =====================================================================
    // Balance Motions (value in degrees/meters, duration in seconds)
    // =====================================================================

    /// Pitch control. value>0 → nod forward, <0 → nod backward. (degrees)
    bool balance_pitch(
        float value, float duration = 2.0f, const std::string& mode = "dynamic", bool show_progress = true)
    {
        return balance_motion_("balance_pitch", value, duration, mode, show_progress);
    }
    /// Yaw control. value>0 → look right, <0 → look left. (degrees)
    bool balance_yaw(float value, float duration = 2.0f, const std::string& mode = "dynamic", bool show_progress = true)
    {
        return balance_motion_("balance_yaw", value, duration, mode, show_progress);
    }
    /// Roll control. value>0 → lean left, <0 → lean right. (degrees)
    bool balance_roll(
        float value, float duration = 2.0f, const std::string& mode = "dynamic", bool show_progress = true)
    {
        return balance_motion_("balance_roll", value, duration, mode, show_progress);
    }
    /// Height control. value<0 → squat (meters, only negative allowed).
    bool balance_height(
        float value, float duration = 2.0f, const std::string& mode = "dynamic", bool show_progress = true)
    {
        return balance_motion_("balance_height", value, duration, mode, show_progress);
    }
    /// Return all balance axes to neutral.
    bool balance_neutral(float duration = 0.5f, bool show_progress = true)
    {
        return balance_motion_("balance_neutral", 0.0f, duration, "dynamic", show_progress);
    }

    /// Execute a batch of balance motions in a single RPC call.
    bool balance_sequence(const std::vector<BalanceMotion>& motions, bool show_progress = true)
    {
        auto req = make_request("balance_seq");
        auto* seq = req.mutable_sequence();
        seq->add_motions()->set_motion_id("balance_stand");
        for (const auto& bm : motions) {
            if (bm.motion_id != "balance_pitch" && bm.motion_id != "balance_yaw" && bm.motion_id != "balance_roll"
                && bm.motion_id != "balance_height" && bm.motion_id != "balance_neutral") {
                throw std::invalid_argument(
                    "Unknown balance motion '" + bm.motion_id
                    + "'. Valid: balance_pitch, balance_yaw, balance_roll, balance_height, balance_neutral");
            }

            std::string axis = "pitch";
            if (bm.motion_id == "balance_height")
                axis = "height";
            else if (bm.motion_id == "balance_roll")
                axis = "roll";
            else if (bm.motion_id == "balance_yaw")
                axis = "yaw";
            else if (bm.motion_id == "balance_neutral")
                axis = "neutral";

            float value = (bm.motion_id == "balance_neutral") ? 0.0f : clamp_balance_value(bm.value, axis);
            if (axis == "yaw")
                value = -value;
            float duration = clamp_balance_duration(bm.duration);

            auto* m = seq->add_motions();
            m->set_motion_id(bm.motion_id);
            set_param(m, "value", value);
            set_param(m, "duration", duration);
            set_param(m, "mode", bm.mode);
        }
        return execute(req, show_progress);
    }

    // =====================================================================
    // Line Walk
    // =====================================================================

    /// Walk in a straight line.
    /// @param direction 0=front, 1=back, 2=left, 3=right
    /// @param distance  meters [0, 3]
    /// @param speed_ratio [10, 100] or -1 to use current base speed ratio.
    bool line_walk(int direction = 0, float distance = 3.0f, int speed_ratio = -1, bool show_progress = true)
    {
        int prev_ratio = -1;
        if (speed_ratio >= 0) {
            prev_ratio = speed_ratio_;
            set_speed_ratio(clamp_speed_ratio(speed_ratio));
        }

        bool prev_oa = obstacle_avoidance_;
        // set_obstacle_avoidance(false);

        auto req = make_request("line_walk");
        auto* m = req.mutable_sequence()->add_motions();
        m->set_motion_id("line_walk");
        set_param(m, "direction", direction);
        set_param(m, "distance", clamp_distance(distance));

        bool ok = execute(req, show_progress);
        // set_obstacle_avoidance(prev_oa);
        if (prev_ratio >= 0)
            set_speed_ratio(prev_ratio);
        return ok;
    }

    bool walk_forward(float dist = 3.0f, int sr = -1, bool sp = true) { return line_walk(0, dist, sr, sp); }
    bool walk_backward(float dist = 3.0f, int sr = -1, bool sp = true) { return line_walk(1, dist, sr, sp); }
    bool move_left(float dist = 3.0f, int sr = -1, bool sp = true) { return line_walk(2, dist, sr, sp); }
    bool move_right(float dist = 3.0f, int sr = -1, bool sp = true) { return line_walk(3, dist, sr, sp); }

    // =====================================================================
    // Rotation
    // =====================================================================

    /// Rotate in place.
    /// @param direction 0=left (CCW), 1=right (CW)
    /// @param angle     degrees
    bool rotate(int direction = 0, float angle = 90.0f, bool show_progress = true)
    {
        direction = (direction == 1) ? 1 : 0;
        angle = clamp_angle(angle);
        auto req = make_request("rotation");
        auto* m = req.mutable_sequence()->add_motions();
        m->set_motion_id("rotation");
        set_param(m, "direction", direction);
        set_param(m, "angle", angle);
        return execute(req, show_progress);
    }

    /// Rotate in place.
    /// @param direction "left"/"right"
    /// @param angle degrees [0-360]
    bool rotate(const std::string& direction, float angle = 90.0f, bool show_progress = true)
    {
        std::string norm = direction;
        std::transform(norm.begin(), norm.end(), norm.begin(), ::tolower);
        if (norm == "left")
            return rotate(0, angle, show_progress);
        if (norm == "right")
            return rotate(1, angle, show_progress);
        throw std::invalid_argument("rotate direction must be \"left\" or \"right\"");
    }

    bool rotate_left(float angle = 90.0f, bool sp = true) { return rotate(0, angle, sp); }
    bool rotate_right(float angle = 90.0f, bool sp = true) { return rotate(1, angle, sp); }

    /// Rotate by turns.
    /// @param direction "left"/"right"
    /// @param turns [1-10]
    bool circle(const std::string& direction = "left", int turns = 1, bool show_progress = true)
    {
        turns = clamp_turns(turns);
        return rotate(direction, 360.0f * turns, show_progress);
    }

    /// Move in given heading angle: rotate first, then walk forward.
    /// @param angle_deg Rotation angle [-180, 180]. Negative = counter-clockwise (left), Positive = clockwise (right).
    /// @param distance_m Distance to walk [0, 3] meters.
    /// @param speed_ratio Speed ratio [10, 100] or -1 to use current base.
    bool rotate_walk(float angle_deg = 0.0f, float distance_m = 0.0f, int speed_ratio = -1, bool show_progress = true)
    {
        angle_deg = clamp_angle_signed(angle_deg);
        distance_m = clamp_distance(distance_m);

        bool ok = (angle_deg >= 0.0f) ? rotate("right", angle_deg, show_progress)
                                      : rotate("left", -angle_deg, show_progress);
        if (!ok)
            return false;
        return walk_forward(distance_m, speed_ratio, show_progress);
    }

    /// Dynamic pose: composite sinusoidal sweep on all axes simultaneously.
    /// @param duration    Duration in seconds [1, 5].
    /// @param roll_deg    Roll target in degrees [-17.0, 17.0], 0 = no motion.
    /// @param pitch_deg   Pitch target in degrees [-11.5, 11.5], 0 = no motion.
    /// @param yaw_deg     Yaw target in degrees [-11.5, 11.5], 0 = no motion.
    /// @param height_m    Height delta in meters [-0.08, 0], 0 = no motion.
    bool dynamic_pose(float duration, float roll_deg = 0, float pitch_deg = 0, float yaw_deg = 0, float height_m = 0,
        bool show_progress = true)
    {
        return pose_motion_("dynamic_pose", duration, roll_deg, pitch_deg, yaw_deg, height_m, show_progress);
    }

    /// Static pose: ramp to target, hold for duration, ramp back.
    /// @param duration    Hold duration in seconds [1, 5].
    /// @param roll_deg    Roll target in degrees [-17.0, 17.0], 0 = no motion.
    /// @param pitch_deg   Pitch target in degrees [-11.5, 11.5], 0 = no motion.
    /// @param yaw_deg     Yaw target in degrees [-11.5, 11.5], 0 = no motion.
    /// @param height_m    Height delta in meters [-0.08, 0], 0 = no motion.
    bool static_pose(float duration, float roll_deg = 0, float pitch_deg = 0, float yaw_deg = 0, float height_m = 0,
        bool show_progress = true)
    {
        return pose_motion_("static_pose", duration, roll_deg, pitch_deg, yaw_deg, height_m, show_progress);
    }


    // =====================================================================
    // Core RPC: Leg LED Control
    // =====================================================================

    /// Batch-set RGB and brightness for leg lights FL/FR/RL/RR (single RPC).
    ///
    /// Current-version rule (all-or-nothing user control): every SetLeds always
    /// carries all four main legs in FL/FR/RL/RR order.
    ///   - Legs present in @p configs use the given RGB/brightness.
    ///   - Legs already in the client cache are resent unchanged (supports
    ///     incremental APIs such as set_leg_brightness).
    ///   - Legs never set in this session are padded as RGB=0 (off).
    ///
    /// Brightness is baked into wire RGB (channel * brightness / 255). Wire
    /// brightness is always sent as 255 (firmware often ignores that field and
    /// may mishandle brightness==0). Client cache keeps logical RGB + bri.
    ///
    /// Fill lights (FILL_FRONT/FILL_BACK) are rejected. Duplicate legs in
    /// @p configs: last entry wins.
    /// @param configs            Per-leg color/brightness entries.
    /// @param default_brightness Fallback when config.brightness == -1; uses
    ///                           cache or 255 if unset.
    /// @param verbose            Dump full command list and status messages.
    /// @return true if the server accepted the request, false on RPC error.
    bool set_legs_rgb(const std::vector<LegLedConfig>& configs,
                      int default_brightness = -1,
                      bool verbose = false)
    {
        if (configs.empty())
            return true;

        static const Leg kMainLegs[] = {
            Leg::FL, Leg::FR, Leg::RL, Leg::RR
        };

        // Resolve explicit overrides (last duplicate wins).
        std::map<Leg, std::tuple<uint8_t, uint8_t, uint8_t, uint8_t>> explicit_cmds;
        for (const auto& cfg : configs) {
            validate_leg_light(cfg.leg);

            if (cfg.r > 255 || cfg.g > 255 || cfg.b > 255) {
                throw std::invalid_argument("RGB values must be 0-255");
            }

            uint8_t final_brightness;
            if (cfg.brightness >= 0) {
                final_brightness = static_cast<uint8_t>(std::max(0, std::min(255, cfg.brightness)));
            } else if (default_brightness >= 0) {
                final_brightness = static_cast<uint8_t>(std::max(0, std::min(255, default_brightness)));
            } else {
                auto it = led_cache_.find(cfg.leg);
                if (it != led_cache_.end()) {
                    final_brightness = std::get<0>(it->second);
                } else {
                    final_brightness = 255;
                }
            }

            explicit_cmds[cfg.leg] = std::make_tuple(
                final_brightness, cfg.r, cfg.g, cfg.b);
        }

        grpc_comm::SetLedsRequest req;
        auto leg_label = [](Leg leg) -> const char* {
            switch (leg) {
                case Leg::FL: return "FL";
                case Leg::FR: return "FR";
                case Leg::RL: return "RL";
                case Leg::RR: return "RR";
                default: return "?";
            }
        };

        if (verbose) {
            std::cout << "[LED] SetLeds commands (4):" << std::endl;
        }

        for (Leg leg : kMainLegs) {
            uint8_t bri, r, g, b;
            const char* source;
            auto ex = explicit_cmds.find(leg);
            if (ex != explicit_cmds.end()) {
                bri = std::get<0>(ex->second);
                r = std::get<1>(ex->second);
                g = std::get<2>(ex->second);
                b = std::get<3>(ex->second);
                source = "explicit";
            } else {
                auto it = led_cache_.find(leg);
                if (it != led_cache_.end()) {
                    bri = std::get<0>(it->second);
                    r = std::get<1>(it->second);
                    g = std::get<2>(it->second);
                    b = std::get<3>(it->second);
                    source = "cache";
                } else {
                    bri = 255;
                    r = g = b = 0;
                    source = "pad-off";
                }
            }

            led_cache_[leg] = std::make_tuple(bri, r, g, b);

            auto wire = scale_rgb_by_brightness(r, g, b, bri);
            const uint8_t wire_r = std::get<0>(wire);
            const uint8_t wire_g = std::get<1>(wire);
            const uint8_t wire_b = std::get<2>(wire);
            // Always 255 on the wire: dimming is conveyed solely via scaled RGB.
            const uint8_t wire_brightness = 255;

            auto* cmd = req.add_commands();
            cmd->set_leg(leg_to_proto(leg));
            cmd->set_brightness(wire_brightness);
            cmd->set_r(wire_r);
            cmd->set_g(wire_g);
            cmd->set_b(wire_b);

            if (verbose) {
                std::cout << "  " << leg_label(leg)
                          << ": logical rgb(" << static_cast<int>(r) << ","
                          << static_cast<int>(g) << "," << static_cast<int>(b)
                          << ") bri=" << static_cast<int>(bri)
                          << " -> wire rgb(" << static_cast<int>(wire_r) << ","
                          << static_cast<int>(wire_g) << "," << static_cast<int>(wire_b)
                          << ") brightness=" << static_cast<int>(wire_brightness)
                          << " [" << source << "]" << std::endl;
            }
        }

        grpc::ClientContext ctx;
        grpc_comm::SetLedsResponse res;
        auto st = stub_->SetLeds(&ctx, req, &res);
        if (!st.ok() || !res.accepted()) {
            if (verbose)
                std::cerr << "[LED] SetLeds rejected: " << res.message() << std::endl;
            return false;
        }
        if (verbose) {
            std::cout << "[LED] Batch accepted." << std::endl;
        }
        return true;
    }

    /// Set RGB for a single leg light (FL/FR/RL/RR only).
    /// @param brightness  [0, 255]; -1 keeps the cached brightness (default 255).
    bool set_leg_rgb(Leg leg, uint8_t r, uint8_t g, uint8_t b,
                     int brightness = -1, bool verbose = false)
    {
        return set_legs_rgb({{leg, r, g, b, brightness}}, -1, verbose);
    }

    /// Set a predefined color on a single leg (brightness from cache).
    bool set_leg_color(Leg leg, Color color, bool verbose = false)
    {
        auto rgb = color_to_rgb(color);
        return set_leg_rgb(leg, std::get<0>(rgb), std::get<1>(rgb), std::get<2>(rgb),
                           -1, verbose);
    }

    /// Adjust brightness only; hue is taken from the client cache (white if unset).
    bool set_leg_brightness(Leg leg, uint8_t brightness, bool verbose = false)
    {
        uint8_t r, g, b;
        auto it = led_cache_.find(leg);
        if (it != led_cache_.end()) {
            r = std::get<1>(it->second);
            g = std::get<2>(it->second);
            b = std::get<3>(it->second);
        } else {
            r = g = b = 255;  // default white
        }
        return set_leg_rgb(leg, r, g, b, brightness, verbose);
    }

    /// Set all four main leg lights (FL/FR/RL/RR) to the same RGB.
    bool set_all_legs_rgb(uint8_t r, uint8_t g, uint8_t b,
                          uint8_t brightness = 255, bool verbose = false)
    {
        std::vector<LegLedConfig> configs = {
            {Leg::FL, r, g, b, static_cast<int>(brightness)},
            {Leg::FR, r, g, b, static_cast<int>(brightness)},
            {Leg::RL, r, g, b, static_cast<int>(brightness)},
            {Leg::RR, r, g, b, static_cast<int>(brightness)}
        };
        return set_legs_rgb(configs, -1, verbose);
    }

    /// Set all four main leg lights to a predefined color.
    bool set_all_legs_color(Color color, uint8_t brightness = 255, bool verbose = false)
    {
        auto rgb = color_to_rgb(color);
        return set_all_legs_rgb(std::get<0>(rgb), std::get<1>(rgb), std::get<2>(rgb),
                                brightness, verbose);
    }

    /// Turn a leg light off (RGB=0) while keeping user control and cached brightness.
    bool turn_off_leg(Leg leg, bool verbose = false)
    {
        uint8_t brightness = 255;
        auto it = led_cache_.find(leg);
        if (it != led_cache_.end())
            brightness = std::get<0>(it->second);
        return set_leg_rgb(leg, 0, 0, 0, brightness, verbose);
    }

    /// Release LED control to the robot's default logic.
    /// @param legs  Legs to reset; empty vector resets all legs and fill lights.
    bool reset_legs(const std::vector<Leg>& legs = {}, bool verbose = false)
    {
        grpc_comm::ResetLedsRequest req;
        for (auto leg : legs) {
            req.add_legs(leg_to_proto(leg));
        }
        // empty legs => server resets all

        grpc::ClientContext ctx;
        grpc_comm::ResetLedsResponse res;
        auto st = stub_->ResetLeds(&ctx, req, &res);
        if (!st.ok() || !res.accepted()) {
            if (verbose)
                std::cerr << "ResetLeds rejected: " << res.message() << std::endl;
            return false;
        }

        // Clear cache for reset legs (or all if none specified)
        if (legs.empty()) {
            led_cache_.clear();
        } else {
            for (auto leg : legs) {
                led_cache_.erase(leg);
            }
        }

        if (verbose) {
            std::cout << "Reset " << (legs.empty() ? "all" : std::to_string(legs.size()))
                      << " leg(s) control." << std::endl;
        }
        return true;
    }

    /// Raw stub access for advanced usage.
    grpc_comm::gRPCService::Stub* operator->() { return stub_.get(); }

private:
    // =====================================================================
    // Internal helpers
    // =====================================================================

    bool set_target_state_with_delay_(const std::string& state, double delay_sec, bool show_progress)
    {
        bool ok = set_target_state(state, show_progress);
        if (ok) {
            std::this_thread::sleep_for(std::chrono::duration<double>(delay_sec));
        }
        return ok;
    }

    int validate_non_negative_duration_(int duration_sec, const std::string& name) const
    {
        if (duration_sec < 0)
            throw std::invalid_argument(name + " must be >= 0");
        return duration_sec;
    }

    int validate_dance_duration_(int duration_sec) const
    {
        if (duration_sec < 1 || duration_sec > 14)
            throw std::invalid_argument("dance duration must be in [1, 14] seconds");
        return duration_sec;
    }

    bool balance_motion_(
        const std::string& motion_id, float value, float duration, const std::string& mode, bool show_progress)
    {
        if (motion_id != "balance_pitch" && motion_id != "balance_yaw" && motion_id != "balance_roll"
            && motion_id != "balance_height" && motion_id != "balance_neutral") {
            throw std::invalid_argument(
                "Unknown balance motion '" + motion_id
                + "'. Valid: balance_pitch, balance_yaw, balance_roll, balance_height, balance_neutral");
        }

        std::string axis = "pitch";
        if (motion_id == "balance_height")
            axis = "height";
        else if (motion_id == "balance_roll")
            axis = "roll";
        else if (motion_id == "balance_yaw")
            axis = "yaw";
        else if (motion_id == "balance_neutral")
            axis = "neutral";

        value = (motion_id == "balance_neutral") ? 0.0f : clamp_balance_value(value, axis);
        if (axis == "yaw")
            value = -value;
        duration = clamp_balance_duration(duration);

        auto req = make_request("balance");
        auto* seq = req.mutable_sequence();
        seq->add_motions()->set_motion_id("balance_stand");
        auto* m = seq->add_motions();
        m->set_motion_id(motion_id);
        set_param(m, "value", value);
        set_param(m, "duration", duration);
        set_param(m, "mode", mode);
        return execute(req, show_progress);
    }

    bool pose_motion_(const std::string& motion_id, float duration, float roll_deg, float pitch_deg, float yaw_deg,
        float height_m, bool show_progress)
    {
        duration = clamp_pose_duration(duration);
        roll_deg = clamp_balance_value(roll_deg, "roll");
        pitch_deg = clamp_balance_value(pitch_deg, "pitch");
        yaw_deg = clamp_balance_value(yaw_deg, "yaw");
        yaw_deg = -yaw_deg;
        height_m = clamp_balance_value(height_m, "height");
        auto req = make_request("pose");
        auto* seq = req.mutable_sequence();
        seq->add_motions()->set_motion_id("balance_stand");
        auto* m = seq->add_motions();
        m->set_motion_id(motion_id);
        set_param(m, "roll", roll_deg);
        set_param(m, "pitch", pitch_deg);
        set_param(m, "yaw", yaw_deg);
        set_param(m, "height", height_m);
        set_param(m, "duration", duration);
        return execute(req, show_progress);
    }

    std::unique_ptr<grpc_comm::gRPCService::Stub> stub_;
    int speed_ratio_ = 50;           ///< Last-known speed ratio from Set RPC response
    bool obstacle_avoidance_ = true; ///< Last-known OA state from Set RPC response
    std::string video_host_;                        ///< 裸 IP（视频子系统用）
    std::shared_ptr<video::Manager> video_manager_; ///< robot.video（懒加载）
    std::string robot_type_;         ///< Cached robot type from GetRobotState
    std::map<Leg, std::tuple<uint8_t, uint8_t, uint8_t, uint8_t>> led_cache_;
};

// =========================================================================
// Safety Ready: automatic ready() on Ctrl+C
// =========================================================================

namespace detail {
static void safety_atexit_handler()
{
    if (!g_safety_triggered.load())
        return;
    Client* c = g_safety_client;
    g_safety_client = nullptr;
    if (c) {
        std::cerr << "\nSafety: returning to ready..." << std::endl;
        c->ready(false);
    }
}
} // namespace detail

/// Call once after constructing Client to enable automatic ready() on Ctrl+C.
/// When Ctrl+C is pressed, the current motion is cancelled and the robot
/// transitions to ready before the process exits.
inline void enable_safety_ready(Client& client)
{
    detail::g_safety_client = &client;
    std::atexit(detail::safety_atexit_handler);
    std::signal(SIGINT, detail::safety_signal_handler);
}

} // namespace robot
