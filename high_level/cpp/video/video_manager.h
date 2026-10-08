#pragma once
// =============================================================================
// robot::video::Manager - the only class of this module that you need.
//
//   list_cameras()              cameras available on this robot
//   open(camera)                start (or adopt) a stream, returns its RTSP address
//   is_streaming(camera)        is that stream playable right now?
//   get_stream_info(camera)     snapshot: state, address, owner, bitrate
//   on_state_change(cb)         subscribe to stream events
//   close(camera)               stop using a camera
//   close_all()                 stop using every camera
//   stop_stream(camera)         force the robot to stop pushing
//
// The SDK never opens a media connection: open() returns an address and your own
// player pulls it, which is why there is no frame type, no read() and no
// on_frame() here.
//
// Internally Manager owns the camera registry plus a single supervisor thread;
// the per-camera decisions live in StreamArbiter and the state is read by
// StatusProbe.
// =============================================================================

#include <chrono>
#include <condition_variable>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "video_arbiter.h"
#include "video_error.h"
#include "video_controller.h"
#include "video_http.h"
#include "video_probe.h"
#include "video_types.h"

namespace robot {
namespace video {

/// Service ports (defaults match the robot; tests inject their own).
struct Endpoints {
    int gcontroll_port = 22000; ///< Robot streaming switch (HTTP)
    int rtsp_port = 8554;       ///< RTSP media port (your player connects here)
    int go2rtc_port = 1984;     ///< Camera state API (HTTP)
};

/// Implementation behind ``client.video()``; do not instantiate it yourself.
class Manager
{
public:
    /// \param address robot address, e.g. ``"192.168.5.2:50051"`` (port ignored)
    /// \param endpoints service ports; leave them at their defaults
    explicit Manager(const std::string& address, const Endpoints& endpoints = Endpoints());
    ~Manager();

    Manager(const Manager&) = delete;
    Manager& operator=(const Manager&) = delete;

    // -- Cameras ---------------------------------------------------------

    /// Cameras available on this robot.
    std::vector<CameraId> list_cameras() const;
    // -- open -------------------------------------------------------------

    /// Starts this camera's stream, or adopts one that is already running, and
    /// blocks until data is really flowing. Returns the address to play.
    ///
    /// Opening a camera that is already open is cheap: it only raises a
    /// reference count and returns the same address.
    ///
    /// \return RTSP address to hand to your player / OpenCV / ffmpeg
    /// \throws VideoError / VideoTimeoutError（reason=NoData / PortUnreachable）
    std::string open(CameraId camera);

    // -- is_streaming / get_stream_info ---------------------------------

    /// Whether this camera's stream is ready to play right now.
    bool is_streaming(CameraId camera) const;

    /// Snapshot of this camera (state is Stopped before the first open()).
    ///
    /// After close() the last known state stays readable, including the address
    /// and whether the stream was left running.
    CameraStreamInfo get_stream_info(CameraId camera) const;

    // -- Events --------------------------------------------------

    /// Subscribes to stream events; the returned function unsubscribes.
    ///
    /// Callbacks run on the SDK's own thread: do not call blocking methods from
    /// one (open() in particular).
    std::function<void()> on_state_change(std::function<void(const StreamEvent&)> callback);

    // -- close / close_all ------------------------------------------------

    /// Stops using this camera (idempotent). The stream is stopped only when the
    /// last user releases it and nobody else is watching (phone app, player).
    void close(CameraId camera);

    /// Releases every camera (idempotent, never touches the robot). Use it on
    /// your way out of the program.
    void close_all();

    // -- stop_stream ------------------------------------------------------

    /// Stops pushing without asking anyone: the robot is told to stop even while
    /// another app is watching.
    ///
    ///   * close()       - "I am done watching": the stream is left alone while
    ///                     somebody else is still watching;
    ///   * stop_stream() - "stop pushing now": always stops, interrupting others.
    ///
    /// \note The robot has one switch for both cameras, so this also clears the
    ///       local state of the other camera.
    void stop_stream(CameraId camera);

    // -- Helpers ---------------------------------------------------------------

    /// RTSP address of this camera; does not touch the robot.
    std::string uri(CameraId camera) const;

    /// Stops the supervisor thread and drops all local state (no HTTP call).
    void shutdown();

    /// Tweaks the sampling parameters (tests only; keep the defaults in real
    /// use, see video_types.h).
    void set_observe(const ObserveConfig& observe);

    /// Tweaks the recovery policy (tests only; keep the defaults in real use).
    void set_policy(const RecoveryPolicy& policy);

    const std::string& host() const { return host_; }
    const Endpoints& endpoints() const { return endpoints_; }

private:
    struct Entry {
        std::shared_ptr<StreamArbiter> arbiter;
        int refcount = 1;
    };

    std::shared_ptr<Entry> find_entry(int key) const;
    std::shared_ptr<StreamArbiter> make_arbiter(CameraId camera);
    void abort_open(CameraId camera, const std::shared_ptr<Entry>& entry);
    void dispatch_event(const StreamEvent& event);

    /// Rejects an out-of-range ``CameraId`` before any work happens.
    ///
    /// Without this, ``camera_label()`` / ``rtsp_name()`` fall back to the rear
    /// camera for any unknown value, so a bogus id would silently open the rear
    /// camera, send HTTP calls and leave state behind.
    void require_supported_camera(CameraId camera) const;

    void ensure_supervisor();
    void maybe_stop_supervisor();
    void stop_supervisor();
    void supervise();

    std::string host_;
    Endpoints endpoints_;
    ObserveConfig observe_;
    RecoveryPolicy policy_;

    std::unique_ptr<StreamingController> controller_;
    std::unique_ptr<StatusProbe> probe_;

    mutable std::mutex mutex_;
    std::map<int, std::shared_ptr<Entry>> entries_;
    /// Cameras being closed right now: no longer usable but still releasing
    /// (which may include telling the robot to stop). open() waits for them.
    std::map<int, std::shared_ptr<Entry>> closing_;
    std::condition_variable teardown_cv_;
    std::map<int, CameraStreamInfo> history_; ///< Last state of every camera, kept after close()
    /// Streams this process has ever started: adopting our own earlier stream
    /// must still count as ours when it is released later.
    std::map<int, bool> sdk_owned_;
    std::map<int, std::function<void(const StreamEvent&)>> state_callbacks_;
    int next_callback_id_ = 1;
    bool closed_ = false;

    std::thread supervisor_;
    std::mutex supervisor_mutex_;
    std::condition_variable supervisor_cv_;
    bool supervisor_stop_ = true;
    bool supervisor_running_ = false;
};


// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

inline Manager::Manager(const std::string& address, const Endpoints& endpoints)
    : endpoints_(endpoints)
{
    int ignored = 0;
    split_host_port(address, endpoints_.gcontroll_port, &host_, &ignored);
    observe_.probe_timeout = observe_.probe_timeout > 0.0 ? observe_.probe_timeout : 1.0;
    controller_.reset(new StreamingController(host_, endpoints_.gcontroll_port, observe_.probe_timeout));
    probe_.reset(new StatusProbe(host_, endpoints_.go2rtc_port));
    probe_->set_timeout(observe_.probe_timeout);
    probe_->set_observe(observe_);
}

inline Manager::~Manager()
{
    shutdown();
}

// -----------------------------------------------------------------------------
// Cameras
// -----------------------------------------------------------------------------

inline std::vector<CameraId> Manager::list_cameras() const
{
    return all_cameras();
}

inline std::string Manager::uri(CameraId camera) const
{
    require_supported_camera(camera);
    return "rtsp://" + host_ + ":" + std::to_string(endpoints_.rtsp_port) + "/" + rtsp_name(camera);
}

inline void Manager::require_supported_camera(CameraId camera) const
{
    for (CameraId known : all_cameras()) {
        if (camera == known) {
            return;
        }
    }
    throw UnsupportedCameraError(std::string("Camera #")
        + std::to_string(static_cast<int>(camera))
        + " is not available on this robot (FRONT_RGB / REAR_RGB)");
}

inline void Manager::set_observe(const ObserveConfig& observe)
{
    observe_ = observe;
    if (probe_) {
        probe_->set_timeout(observe_.probe_timeout);
        probe_->set_observe(observe_);
    }
    if (controller_) {
        controller_.reset(
            new StreamingController(host_, endpoints_.gcontroll_port, observe_.probe_timeout));
    }
}

inline void Manager::set_policy(const RecoveryPolicy& policy)
{
    policy_ = policy;
}

// -----------------------------------------------------------------------------
// ② open
// -----------------------------------------------------------------------------

inline std::shared_ptr<StreamArbiter> Manager::make_arbiter(CameraId camera)
{
    return std::make_shared<StreamArbiter>(camera, uri(camera), probe_.get(), controller_.get(),
        [this](const StreamEvent& event) { dispatch_event(event); }, observe_, policy_);
}

inline std::string Manager::open(CameraId camera)
{
    require_supported_camera(camera);   // 非法值：立刻拒绝，不发任何请求
    std::shared_ptr<Entry> entry;
    {
        std::unique_lock<std::mutex> lock(mutex_);
        if (closed_) {
            throw VideoError(camera_label(camera) + ": the video manager was shut down");
        }
        // A close() that is still running may be about to stop the robot's
        // stream: wait for it, or it would kill the stream we are opening now.
        double waited = 0.0;
        while (closing_.find(static_cast<int>(camera)) != closing_.end() && waited < 5.0) {
            teardown_cv_.wait_for(lock, std::chrono::milliseconds(50));
            waited += 0.05;
        }
        auto it = entries_.find(static_cast<int>(camera));
        if (it == entries_.end()) {
            entry = std::make_shared<Entry>();
            entry->arbiter = make_arbiter(camera);
            entry->refcount = 0;
            entries_[static_cast<int>(camera)] = entry;
        } else {
            entry = it->second;
        }
        ++entry->refcount;
    }

    ensure_supervisor();
    entry->arbiter->begin();
    try {
        const std::string uri = entry->arbiter->wait_ready(observe_.ready_timeout);
        if (entry->arbiter->sdk_started()) {
            std::lock_guard<std::mutex> lock(mutex_);
            sdk_owned_[static_cast<int>(camera)] = true;
        }
        return uri;
    } catch (...) {
        abort_open(camera, entry);
        throw;
    }
}

inline void Manager::abort_open(CameraId camera, const std::shared_ptr<Entry>& entry)
{
    {
        std::lock_guard<std::mutex> lock(mutex_);
        --entry->refcount;
        if (entry->refcount > 0) {
            return;
        }
        auto it = entries_.find(static_cast<int>(camera));
        if (it != entries_.end() && it->second == entry) {
            entries_.erase(it);
        }
        closing_[static_cast<int>(camera)] = entry;
    }
    entry->arbiter->release(LossReason::Closed, "open() failed; local state released");
    {
        std::lock_guard<std::mutex> lock(mutex_);
        history_[static_cast<int>(camera)] = entry->arbiter->info();
        auto it = closing_.find(static_cast<int>(camera));
        if (it != closing_.end() && it->second == entry) {
            closing_.erase(it);
        }
    }
    teardown_cv_.notify_all();
    maybe_stop_supervisor();
}

// -----------------------------------------------------------------------------
// Queries
// -----------------------------------------------------------------------------

/// Looks a camera up in the live registry first, then among the streams that
/// are still being released. Callers must hold ``mutex_``.
inline std::shared_ptr<Manager::Entry> Manager::find_entry(int key) const
{
    auto it = entries_.find(key);
    if (it != entries_.end()) {
        return it->second;
    }
    auto closing = closing_.find(key);
    if (closing != closing_.end()) {
        return closing->second;
    }
    return std::shared_ptr<Entry>();
}

inline bool Manager::is_streaming(CameraId camera) const
{
    require_supported_camera(camera);
    std::lock_guard<std::mutex> lock(mutex_);
    const std::shared_ptr<Entry> entry = find_entry(static_cast<int>(camera));
    if (!entry || !entry->arbiter) {
        return false;
    }
    return entry->arbiter->state() == StreamState::Ready;
}

inline CameraStreamInfo Manager::get_stream_info(CameraId camera) const
{
    require_supported_camera(camera);
    {
        std::lock_guard<std::mutex> lock(mutex_);
        const std::shared_ptr<Entry> entry = find_entry(static_cast<int>(camera));
        if (entry && entry->arbiter) {
            return entry->arbiter->info();
        }
        auto hit = history_.find(static_cast<int>(camera));
        if (hit != history_.end()) {
            return hit->second;
        }
    }
    CameraStreamInfo info;
    info.camera = camera;
    info.state = StreamState::Stopped;
    return info;
}

// -----------------------------------------------------------------------------
// Events
// -----------------------------------------------------------------------------

inline std::function<void()> Manager::on_state_change(std::function<void(const StreamEvent&)> callback)
{
    if (!callback) {
        throw VideoError("on_state_change() requires a callback");
    }
    int id = 0;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        id = next_callback_id_++;
        state_callbacks_[id] = std::move(callback);
    }
    return [this, id]() {
        std::lock_guard<std::mutex> lock(mutex_);
        state_callbacks_.erase(id);
    };
}

inline void Manager::dispatch_event(const StreamEvent& event)
{
    std::vector<std::function<void(const StreamEvent&)>> callbacks;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto& kv : state_callbacks_) {
            callbacks.push_back(kv.second);
        }
    }
    for (auto& callback : callbacks) {
        try {
            callback(event);
        } catch (...) {
            // a callback that throws must not disturb the state machine
        }
    }
}

// -----------------------------------------------------------------------------
// close / stop_stream
// -----------------------------------------------------------------------------

inline void Manager::close(CameraId camera)
{
    require_supported_camera(camera);
    std::shared_ptr<Entry> entry;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = entries_.find(static_cast<int>(camera));
        if (it == entries_.end()) {
            return; // idempotent
        }
        entry = it->second;
        --entry->refcount;
        if (entry->refcount > 0) {
            return; // other users are still around
        }
        // Out of entries_ right away: a concurrent open() must not adopt a stream
        // that is being released (it would be cancelled halfway through).
        entries_.erase(it);
        closing_[static_cast<int>(camera)] = entry;
    }

    bool sdk_started = entry->arbiter->sdk_started();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        // adopting a stream we started earlier: sdk_started is false this time
        if (sdk_owned_[static_cast<int>(camera)]) {
            sdk_started = true;
        }
    }
    // Only stop when no other watcher is known to exist on any camera.
    const int watching = probe_->all_watching(2, observe_.settle_seconds);
    std::string message;
    bool keep = true;
    if (watching > 0) {
        message = "Stream left running: another watcher (app or player) is using it";
    } else if (watching < 0) {
        message = "Stream left running: could not confirm that nobody else is watching";
    } else if (sdk_started) {
        message = "Stream stopped, resources released";
        keep = false;
    } else {
        message = "Stream left running: it was not started by this SDK";
        keep = false;
    }

    entry->arbiter->release(LossReason::Closed, message);
    if (!keep && sdk_started) {
        try {
            controller_->stop();
        } catch (const std::exception&) {
            // a failed stop does not change close()'s contract: local state is gone
        }
    }

    {
        std::lock_guard<std::mutex> lock(mutex_);
        history_[static_cast<int>(camera)] = entry->arbiter->info();
        if (!keep) {
            sdk_owned_[static_cast<int>(camera)] = false; // stopped now, no longer ours
        }
        auto it = closing_.find(static_cast<int>(camera));
        if (it != closing_.end() && it->second == entry) {
            closing_.erase(it);
        }
    }
    teardown_cv_.notify_all();
    maybe_stop_supervisor();
}

inline void Manager::close_all()
{
    std::vector<std::pair<CameraId, std::shared_ptr<Entry>>> entries;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto& kv : entries_) {
            entries.emplace_back(static_cast<CameraId>(kv.first), kv.second);
        }
        entries_.clear();
    }
    for (auto& item : entries) {
        item.second->refcount = 0;
        item.second->arbiter->release(LossReason::Closed,
            "manager shut down; local state released");
        std::lock_guard<std::mutex> lock(mutex_);
        history_[static_cast<int>(item.first)] = item.second->arbiter->info();
    }
    maybe_stop_supervisor();
}

inline void Manager::stop_stream(CameraId camera)
{
    require_supported_camera(camera);
    std::vector<std::shared_ptr<Entry>> entries;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto& kv : entries_) {
            entries.push_back(kv.second);
        }
    }
    const std::string message = "Stopped by stop_stream(" + camera_name(camera) + ")";
    for (auto& entry : entries) {
        entry->arbiter->force_stopped(message);
        std::lock_guard<std::mutex> lock(mutex_);
        history_[static_cast<int>(entry->arbiter->camera())] = entry->arbiter->info();
    }
    try {
        controller_->stop();
    } catch (const std::exception&) {
        // never throws: local state is already gone and the user can retry
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        sdk_owned_.clear(); // one switch for both cameras: nothing is ours any more
    }
    maybe_stop_supervisor();
}

inline void Manager::shutdown()
{
    close_all();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        closed_ = true;
        state_callbacks_.clear();
        closing_.clear();
    }
    stop_supervisor();
}

// -----------------------------------------------------------------------------
// Supervisor thread (one per Manager)
// -----------------------------------------------------------------------------

inline void Manager::ensure_supervisor()
{
    std::lock_guard<std::mutex> lock(supervisor_mutex_);
    if (supervisor_running_) {
        return;
    }
    supervisor_stop_ = false;
    supervisor_running_ = true;
    if (supervisor_.joinable()) {
        supervisor_.join();
    }
    supervisor_ = std::thread([this]() { supervise(); });
}

inline void Manager::maybe_stop_supervisor()
{
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!entries_.empty()) {
            return;
        }
    }
    stop_supervisor();
}

inline void Manager::stop_supervisor()
{
    bool should_join = false;
    {
        std::lock_guard<std::mutex> lock(supervisor_mutex_);
        if (!supervisor_running_) {
            return;
        }
        supervisor_stop_ = true;
        supervisor_running_ = false;
        should_join = supervisor_.joinable() && supervisor_.get_id() != std::this_thread::get_id();
        supervisor_cv_.notify_all();
    }
    if (should_join) {
        supervisor_.join();
    }
}

inline void Manager::supervise()
{
    std::unique_lock<std::mutex> lock(supervisor_mutex_);
    while (!supervisor_stop_) {
        lock.unlock();
        std::vector<std::shared_ptr<StreamArbiter>> arbiters;
        {
            std::lock_guard<std::mutex> guard(mutex_);
            for (auto& kv : entries_) {
                arbiters.push_back(kv.second->arbiter);
            }
        }
        const double now = monotonic_s();
        for (auto& arbiter : arbiters) {
            arbiter->tick(now);
        }
        lock.lock();
        if (supervisor_stop_) {
            break;
        }
        supervisor_cv_.wait_for(lock, std::chrono::duration<double>(observe_.tick));
    }
}


} // namespace video
} // namespace robot
