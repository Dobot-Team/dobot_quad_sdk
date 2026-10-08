#pragma once
// =============================================================================
// Public types of the camera video streaming API (robot::video) - C++ side.
//
// Nothing media-related lives here: no frame type, no decoder, no RTP.
// open() hands you an RTSP address and your own player does the rest:
//
//   std::string uri = client.video().open(robot::video::CameraId::FrontRgb);
//   // hand uri to ffmpeg / OpenCV / GStreamer / VLC
//
// Day-to-day you only touch CameraId, CameraStreamInfo, StreamEvent and the
// exception types below (robot::video::Manager is declared in video_manager.h).
// =============================================================================

#include <chrono>
#include <cstdint>
#include <functional>
#include <ostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace robot {
namespace video {

// -----------------------------------------------------------------------------
// State / ownership / reasons
// -----------------------------------------------------------------------------

/// Lifecycle of one camera stream.
enum class StreamState {
    Stopped,    ///< Never opened, or closed again (no address yet)
    Preparing,  ///< open() is waiting for the camera to really stream
    Ready,      ///< open() returned an address you can play
    Recovering, ///< The stream dropped or stalled; the SDK is bringing it back
    Stopping,   ///< Last user released it, the SDK is closing it down
    Error,      ///< Automatic recovery gave up; call open() to try again
};

inline const char* to_string(StreamState state)
{
    switch (state) {
    case StreamState::Stopped:
        return "stopped";
    case StreamState::Preparing:
        return "preparing";
    case StreamState::Ready:
        return "ready";
    case StreamState::Recovering:
        return "recovering";
    case StreamState::Stopping:
        return "stopping";
    case StreamState::Error:
        return "error";
    }
    return "unknown";
}

/// Who started this stream, as far as the SDK can tell.
enum class StreamOwner {
    Unknown,
    Sdk,      ///< This SDK started it
    External, ///< It was already running (phone app, another program)
};

inline const char* to_string(StreamOwner owner)
{
    switch (owner) {
    case StreamOwner::Sdk:
        return "sdk";
    case StreamOwner::External:
        return "external";
    case StreamOwner::Unknown:
        return "unknown";
    }
    return "unknown";
}

/// Why a stream could not be used, or stopped being usable.
enum class LossReason {
    None,
    External,        ///< Nothing is being pushed any more
    Stall,           ///< Data stopped flowing while the stream was up
    PortUnreachable, ///< The robot's streaming service cannot be reached
    NoData,          ///< open() timed out before any data arrived
    Closed,          ///< You closed it
};

inline const char* to_string(LossReason reason)
{
    switch (reason) {
    case LossReason::None:
        return "none";
    case LossReason::External:
        return "external";
    case LossReason::Stall:
        return "stall";
    case LossReason::PortUnreachable:
        return "port_unreachable";
    case LossReason::NoData:
        return "no_data";
    case LossReason::Closed:
        return "closed";
    }
    return "none";
}

/// What the SDK did to bring a stream back.
enum class RecoveredBy {
    None,
    L1Resume,  ///< Asked the robot to resume pushing
    L2Restart, ///< Restarted the stream (used when data had stalled)
};

inline const char* to_string(RecoveredBy by)
{
    switch (by) {
    case RecoveredBy::L1Resume:
        return "L1_resume";
    case RecoveredBy::L2Restart:
        return "L2_restart";
    case RecoveredBy::None:
        return "none";
    }
    return "none";
}

/// Kind of change reported to ``on_state_change()`` callbacks.
enum class StreamEventKind {
    Ready,
    Lost,
    Reconnected,
    Closed,
    Error,
};

inline const char* event_name(StreamEventKind kind)
{
    switch (kind) {
    case StreamEventKind::Ready:
        return "StreamReady";
    case StreamEventKind::Lost:
        return "StreamLost";
    case StreamEventKind::Reconnected:
        return "StreamReconnected";
    case StreamEventKind::Closed:
        return "StreamClosed";
    case StreamEventKind::Error:
        return "StreamError";
    }
    return "StreamEvent";
}

// -----------------------------------------------------------------------------
// Exceptions
//
// VideoError / VideoConnectionError / VideoTimeoutError / UnsupportedCameraError
// are declared in video_error.h.
// -----------------------------------------------------------------------------

// -----------------------------------------------------------------------------

/// Base class of every exception thrown by this module.
class VideoError : public std::runtime_error
{
public:
    explicit VideoError(const std::string& message, LossReason reason = LossReason::None)
        : std::runtime_error(message)
        , reason_(reason)
    {
    }

    /// Machine-readable reason, for callers that branch on it.
    LossReason reason() const { return reason_; }

private:
    LossReason reason_ = LossReason::None;
};

/// The robot or its streaming service could not be reached.
class VideoConnectionError : public VideoError
{
public:
    explicit VideoConnectionError(const std::string& message,
        LossReason reason = LossReason::PortUnreachable)
        : VideoError(message, reason)
    {
    }
};

/// The operation did not finish in time.
class VideoTimeoutError : public VideoError
{
public:
    explicit VideoTimeoutError(const std::string& message, LossReason reason = LossReason::NoData)
        : VideoError(message, reason)
    {
    }
};

/// The camera does not exist or is not available on this robot.
class UnsupportedCameraError : public VideoError
{
public:
    explicit UnsupportedCameraError(const std::string& message)
        : VideoError(message)
    {
    }
};

/// Throws the exception type that matches the failure reason.
///
/// Callers can catch the base class (``VideoError``, which still works because
/// everything derives from it) *or* the type the documentation mentions:
/// ``VideoConnectionError`` when the robot cannot be reached,
/// ``VideoTimeoutError`` when the stream produced no data in time. Anything
/// else (a stall, an external stop, a cancelled open, ...) keeps the base type.
[[noreturn]] inline void throw_video_error(const std::string& message, LossReason reason)
{
    switch (reason) {
    case LossReason::PortUnreachable:
        throw VideoConnectionError(message, reason);
    case LossReason::NoData:
        throw VideoTimeoutError(message, reason);
    default:
        throw VideoError(message, reason);
    }
}

// -----------------------------------------------------------------------------
// Cameras
// -----------------------------------------------------------------------------

/// Camera identifier.
///
/// Values are stable across releases: new cameras are appended.
enum class CameraId {
    FrontRgb = 0, ///< Front RGB camera
    RearRgb = 1,  ///< Rear RGB camera
};

/// Cameras available on this robot (front and rear RGB).
inline std::vector<CameraId> all_cameras()
{
    return {CameraId::FrontRgb, CameraId::RearRgb};
}

/// Stream name used inside the RTSP address; internal.
inline std::string rtsp_name(CameraId camera)
{
    return camera == CameraId::FrontRgb ? "camera1" : "camera2";
}

/// Topic index used by the DDS layer; internal.
inline std::string dds_name(CameraId camera)
{
    return camera == CameraId::FrontRgb ? "camera0" : "camera1";
}

/// Short readable name, used in messages.
inline std::string camera_label(CameraId camera)
{
    return camera == CameraId::FrontRgb ? "Front RGB" : "Rear RGB";
}

/// Enum name (``FRONT_RGB`` / ``REAR_RGB``).
inline std::string camera_name(CameraId camera)
{
    return camera == CameraId::FrontRgb ? "FRONT_RGB" : "REAR_RGB";
}

inline std::ostream& operator<<(std::ostream& os, CameraId camera)
{
    return os << camera_name(camera);
}

/// Codec of the stream (fixed by the robot; the SDK does not transcode).
constexpr const char* kStreamCodec = "H.264";

// -----------------------------------------------------------------------------
// Read-only data objects
// -----------------------------------------------------------------------------

/// Snapshot returned by ``Manager::get_stream_info()``.
struct CameraStreamInfo {
    CameraId camera = CameraId::FrontRgb;
    StreamState state = StreamState::Stopped;
    StreamOwner owner = StreamOwner::Unknown; ///< Who started it (best guess)
    std::string uri;        ///< Address to play while the stream is up
    std::string codec = kStreamCodec;
    double bitrate_kbps = -1.0; ///< Recent bitrate in kbit/s; < 0 = unknown
    LossReason reason = LossReason::None;
    std::string message; ///< Extra detail, e.g. whether the stream was stopped

    bool is_streaming() const { return state == StreamState::Ready; }

    /// Whether ``uri`` can be played right now.
    bool available() const { return state == StreamState::Ready && !uri.empty(); }

    std::string to_string() const;
};

/// Payload passed to ``on_state_change()`` callbacks.
struct StreamEvent {
    StreamEventKind kind = StreamEventKind::Ready;
    CameraId camera = CameraId::FrontRgb;
    StreamState old_state = StreamState::Stopped;
    StreamState new_state = StreamState::Stopped;
    LossReason reason = LossReason::None;
    RecoveredBy recovered_by = RecoveredBy::None;
    std::string uri;
    std::string message;
    int64_t timestamp_ns = 0;

    /// One of StreamReady / StreamLost / StreamReconnected / StreamClosed / StreamError.
    std::string name() const { return event_name(kind); }

    std::string to_string() const;
};

// -----------------------------------------------------------------------------
// Internal tuning - deliberately not exposed to users
// -----------------------------------------------------------------------------

/// How often the SDK samples the stream state.
struct ObserveConfig {
    double tick = 0.25;           ///< Supervisor loop period (s)
    double sample_interval = 2.0; ///< Sampling period while streaming (s)
    int stall_samples = 2;        ///< Flat samples in a row that count as stalled
    double ready_timeout = 8.0;   ///< How long open() waits for the stream (s)
    double probe_timeout = 1.0;   ///< Timeout of one state request (s)
    double prepare_poll = 0.25;   ///< Sampling period while starting up (s)
    double settle_seconds = 0.3;  ///< Gap between the two samples taken when closing (s)
    /// While starting up: how long "the stream exists but carries no new
    /// data" is tolerated before it is treated as stalled (s).
    double prepare_stall_seconds = 2.5;
};

/// How the SDK recovers a broken stream (built in, not configurable).
struct RecoveryPolicy {
    std::vector<double> backoff {0.5, 1.0, 2.0}; ///< Delays between retries (s)
    int max_attempts = 3;                        ///< Give up after this many tries
    double restart_cooldown = 60.0;              ///< Minimum gap between two restarts (s)
    int restart_max_per_window = 2;              ///< Restarts allowed per window
    double restart_window = 600.0;               ///< Restart counting window (s)
    double act_timeout = 3.0;                    ///< Wait for evidence after a recovery action (s)
};

/// Monotonic clock in nanoseconds.
inline int64_t monotonic_ns()
{
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

/// Monotonic clock in seconds.
inline double monotonic_s()
{
    return std::chrono::duration<double>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}


// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

inline std::string CameraStreamInfo::to_string() const
{
    std::ostringstream os;
    os << camera_name(camera) << ": " << video::to_string(state)
       << " | owner=" << video::to_string(owner);
    if (!uri.empty()) {
        os << " | " << uri;
    }
    if (bitrate_kbps >= 0.0) {
        os << " | " << static_cast<long long>(bitrate_kbps + 0.5) << " kbps";
    }
    if (reason != LossReason::None) {
        os << " | reason=" << video::to_string(reason);
    }
    if (!message.empty()) {
        os << " | " << message;
    }
    return os.str();
}

inline std::string StreamEvent::to_string() const
{
    std::ostringstream os;
    os << name() << " " << camera_name(camera) << ": "
       << video::to_string(old_state) << " -> " << video::to_string(new_state);
    if (recovered_by != RecoveredBy::None) {
        os << " (recovered_by=" << video::to_string(recovered_by) << ")";
    } else if (reason != LossReason::None) {
        os << " (" << video::to_string(reason) << ")";
    }
    if (!message.empty()) {
        os << " - " << message;
    }
    return os.str();
}


} // namespace video
} // namespace robot
