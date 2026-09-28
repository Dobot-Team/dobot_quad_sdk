#pragma once
// =============================================================================
// Camera state as reported by the robot (GET http://<ip>:1984/api/streams).
//
// It answers two questions:
//   * is this camera pushing at all, and is data still flowing (that is, do the
//     pushed byte counts keep growing)?
//   * who else is watching, which decides whether closing may stop the stream.
//
// Limits worth remembering:
//   1. it only sees watchers that connect through the robot's video service;
//   2. it cannot tell who started a stream - that stays a guess;
//   3. it cannot prove that a user has stopped watching, only whether the robot
//      is still pushing;
//   4. a camera missing from the answer means "no information", which is not
//      the same as "nobody is watching".
//
// The class owns no thread: Manager's supervisor loop calls it periodically.
// =============================================================================

#include <cctype>
#include <chrono>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "video_http.h"
#include "video_json.h"
#include "video_types.h"

namespace robot {
namespace video {

/// One watcher of the stream: the phone app, a player, another program.
struct Consumer {
    std::string remote_addr;
    std::string user_agent;

    /// Whether the user agent looks like the phone app; informational only.
    bool is_app_like() const;
    std::string to_string() const;
};

/// One camera as seen at one moment.
struct StreamStatus {
    CameraId camera = CameraId::FrontRgb;
    std::string stream;
    int producer_count = 0;
    long long bytes_recv = 0; ///< Bytes pushed by the camera so far
    std::vector<Consumer> consumers;
    double fetched_at = 0.0;
    bool available = false; ///< false = no information this time (not "nobody watching")
    std::string error;

    bool has_producer() const { return available && producer_count > 0; }
    int consumer_count() const { return static_cast<int>(consumers.size()); }

    /// Whether anyone else is watching this camera.
    /// \return 1 = yes, 0 = no, -1 = unknown
    int others_watching() const;

    std::string to_string() const;
};

/// Reads the camera state, reusing the last answer for a short while.
class StatusProbe
{
public:
    StatusProbe(const std::string& host, int port = 1984);

    StatusProbe(const StatusProbe&) = delete;
    StatusProbe& operator=(const StatusProbe&) = delete;

    void set_timeout(double timeout_s) { timeout_s_ = timeout_s; }
    void set_observe(const ObserveConfig& observe) { observe_ = observe; }

    /// Snapshot of one camera.
    ///
    /// \param force ask now, ignoring the cache and never falling back to an
    ///              older answer
    StreamStatus status(CameraId camera, bool force) const;

    /// Snapshots of every camera. Closing always looks at all of them.
    std::vector<StreamStatus> snapshot(bool force) const;

    /// Used when closing: 1 if any camera still has another watcher, 0 if none
    /// has, -1 if unknown (never a reason to stop a stream).
    ///
    /// \p samples fresh samples in a row must agree, because watchers come and
    /// go asynchronously.
    int all_watching(int samples, double interval_s) const;

    /// Asks for a fresh answer now; returns whether it worked.
    bool refresh() const;

    /// Drops the cached answer.
    void invalidate() const;

    const std::string& last_error() const { return error_; }

private:
    /// Fetches if needed; returns whether usable data is available.
    ///
    /// \param force ask now and do not fall back to an older answer
    bool fetch(bool force) const;

    /// Parses the last successful answer.
    StreamStatus parse(CameraId camera, double fetched_at) const;

    /// How long the last answer stays good enough to reuse.
    double stale_ttl() const;

    std::string host_;
    int port_;
    double timeout_s_ = 1.0;
    ObserveConfig observe_;

    mutable std::mutex mutex_;
    mutable std::string raw_json_;   ///< Body of the last successful answer
    mutable double success_at_ = 0.0; ///< Time of the last success
    mutable double attempt_at_ = 0.0; ///< Time of the last attempt
    mutable bool reachable_ = false;  ///< Whether the last attempt succeeded
    mutable std::string error_;
};


// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

// -----------------------------------------------------------------------------
// Consumer / StreamStatus
// -----------------------------------------------------------------------------

inline bool Consumer::is_app_like() const
{
    if (user_agent.empty()) {
        return false;
    }
    std::string ua = user_agent;
    for (char& ch : ua) {
        ch = static_cast<char>(::tolower(static_cast<unsigned char>(ch)));
    }
    return ua.find("uni-app") != std::string::npos || ua.find("webrtc") != std::string::npos
        || ua.find("mozilla") != std::string::npos;
}

inline std::string Consumer::to_string() const
{
    if (user_agent.empty()) {
        return remote_addr;
    }
    const std::string ua = user_agent.size() > 24 ? user_agent.substr(0, 24) + "..." : user_agent;
    return remote_addr + "(" + ua + ")";
}

inline int StreamStatus::others_watching() const
{
    if (!available) {
        return -1; // unknown is not "nobody"
    }
    return consumers.empty() ? 0 : 1;
}

inline std::string StreamStatus::to_string() const
{
    std::ostringstream os;
    os << (stream.empty() ? camera_name(camera) : stream) << ": ";
    if (!available) {
        os << "unavailable(" << (error.empty() ? "no data" : error) << ")";
        return os.str();
    }
    os << "producers=" << producer_count << " consumers=" << consumers.size()
       << " bytes_recv=" << bytes_recv;
    return os.str();
}

// -----------------------------------------------------------------------------
// StatusProbe
// -----------------------------------------------------------------------------

inline StatusProbe::StatusProbe(const std::string& host, int port)
    : host_(host)
    , port_(port)
{
}

inline double StatusProbe::stale_ttl() const
{
    const double ttl = observe_.sample_interval * 2.0;
    return ttl > 3.0 ? ttl : 3.0;
}

inline void StatusProbe::invalidate() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    success_at_ = 0.0;
    attempt_at_ = 0.0;
    reachable_ = false;
    raw_json_.clear();
}

inline bool StatusProbe::refresh() const
{
    return fetch(true);
}

inline bool StatusProbe::fetch(bool force) const
{
    const double now = monotonic_s();
    bool need_request = false;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        need_request = force || (now - attempt_at_) >= observe_.sample_interval;
    }

    if (need_request) {
        HttpResponse response;
        std::string error;
        const bool ok = http_request(
                            host_, port_, "GET", "/api/streams", "", timeout_s_, &response, &error)
            && response.status == 200 && !response.body.empty();

        std::lock_guard<std::mutex> lock(mutex_);
        attempt_at_ = now;
        if (ok) {
            raw_json_ = response.body;
            success_at_ = now;
            reachable_ = true;
            error_.clear();
        } else {
            reachable_ = false;
            error_ = error.empty()
                ? (response.status != 0 ? "http " + std::to_string(response.status) : "empty response")
                : error;
            // keep raw_json_: the previous answer is still usable for a while
        }
    }

    std::lock_guard<std::mutex> lock(mutex_);
    if (reachable_) {
        return true;
    }
    if (force) {
        return false; // a failed refresh means "unknown"
    }
    return !raw_json_.empty() && success_at_ > 0.0 && (now - success_at_) < stale_ttl();
}

inline StreamStatus StatusProbe::parse(CameraId camera, double fetched_at) const
{
    StreamStatus status;
    status.camera = camera;
    status.stream = rtsp_name(camera);
    status.fetched_at = fetched_at;

    // fetch() guarantees a body when it returns true; an empty one fails to parse
    std::string body;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        body = raw_json_;
    }

    json::Value root;
    std::string error;
    if (!json::parse(body, &root, &error) || !root.is_object()) {
        status.error = "invalid json: " + error;
        return status;
    }

    const json::Value* entry = root.find(status.stream);
    if (entry == nullptr) {
        // camera missing from the answer: unknown, not "nobody watching"
        status.error = "stream not present in go2rtc response";
        return status;
    }
    if (!entry->is_object()) {
        status.error = "invalid stream entry";
        return status;
    }

    if (const json::Value* producers = entry->find("producers")) {
        if (producers->is_array()) {
            for (size_t i = 0; i < producers->size(); ++i) {
                const json::Value& producer = producers->at(i);
                if (!producer.is_object()) {
                    continue;
                }
                ++status.producer_count;
                if (const json::Value* bytes = producer.find("bytes_recv")) {
                    status.bytes_recv += static_cast<long long>(bytes->as_number());
                }
            }
        }
    }
    if (const json::Value* consumers = entry->find("consumers")) {
        if (consumers->is_array()) {
            for (size_t i = 0; i < consumers->size(); ++i) {
                const json::Value& raw = consumers->at(i);
                if (!raw.is_object()) {
                    continue;
                }
                Consumer consumer;
                if (const json::Value* addr = raw.find("remote_addr")) {
                    consumer.remote_addr = addr->as_string();
                } else if (const json::Value* addr2 = raw.find("addr")) {
                    consumer.remote_addr = addr2->as_string();
                }
                if (const json::Value* ua = raw.find("user_agent")) {
                    consumer.user_agent = ua->as_string();
                }
                status.consumers.push_back(consumer);
            }
        }
    }
    status.available = true;
    return status;
}

inline StreamStatus StatusProbe::status(CameraId camera, bool force) const
{
    const bool usable = fetch(force);
    double fetched_at = 0.0;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        fetched_at = success_at_ > 0.0 ? success_at_ : attempt_at_;
    }
    if (!usable) {
        StreamStatus status;
        status.camera = camera;
        status.stream = rtsp_name(camera);
        status.fetched_at = fetched_at;
        std::lock_guard<std::mutex> lock(mutex_);
        status.error = error_.empty() ? "unreachable" : error_;
        return status;
    }
    return parse(camera, fetched_at);
}

inline std::vector<StreamStatus> StatusProbe::snapshot(bool force) const
{
    std::vector<StreamStatus> out;
    for (CameraId camera : all_cameras()) {
        out.push_back(status(camera, force));
    }
    return out;
}

inline int StatusProbe::all_watching(int samples, double interval_s) const
{
    if (samples < 1) {
        samples = 1;
    }
    int result = -1;
    bool first = true;
    for (int i = 0; i < samples; ++i) {
        if (i > 0 && interval_s > 0.0) {
            std::this_thread::sleep_for(std::chrono::duration<double>(interval_s));
        }
        bool seen = false;
        bool unknown = false;
        for (const StreamStatus& status : snapshot(true)) {
            const int watching = status.others_watching();
            if (watching < 0) {
                unknown = true;
            } else if (watching > 0) {
                seen = true;
            }
        }
        const int sample = unknown ? -1 : (seen ? 1 : 0);
        if (first) {
            result = sample;
            first = false;
        } else if (sample != result) {
            // samples disagree: keep the "there may be a watcher" answer
            return (result > 0 || sample > 0) ? 1 : -1;
        }
    }
    return result;
}


} // namespace video
} // namespace robot
