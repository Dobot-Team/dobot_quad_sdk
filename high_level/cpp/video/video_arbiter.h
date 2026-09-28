#pragma once
// =============================================================================
// Per-camera stream state machine and recovery.
//
// For one camera it:
//   * starts the stream, adopting one that is already running when possible,
//     and only reports success once data really flows;
//   * keeps watching it while it is up;
//   * brings it back after a drop - resume first, restart when data had
//     stalled, then give up with a reason the user can act on.
//
// The class owns no thread: Manager's supervisor loop drives tick(), while
// open() waits on the calling thread.
// =============================================================================

#include <algorithm>
#include <cmath>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <string>
#include <vector>

#include "video_controller.h"
#include "video_error.h"
#include "video_probe.h"
#include "video_types.h"

namespace robot {
namespace video {

/// Result of a restart attempt.
///
/// "Out of attempts" and "the attempt itself failed" are reported separately so
/// that the message shown to the user is accurate.
enum class RestartOutcome {
    Done,        ///< Restarted; now waiting for data
    Cooling,     ///< Too soon after the last restart; will retry later
    Limit,       ///< Restart budget used up; recovery gives up
    Failed,      ///< The attempt failed (network); it will be retried
    Unreachable, ///< The robot cannot be reached; the stream goes to Error
};

inline const char* to_string(RestartOutcome outcome)
{
    switch (outcome) {
    case RestartOutcome::Done:
        return "done";
    case RestartOutcome::Cooling:
        return "cooling";
    case RestartOutcome::Limit:
        return "limit";
    case RestartOutcome::Failed:
        return "failed";
    case RestartOutcome::Unreachable:
        return "unreachable";
    }
    return "unknown";
}

class StreamArbiter
{
public:
    StreamArbiter(CameraId camera, const std::string& uri, const StatusProbe* probe,
        StreamingController* controller, std::function<void(const StreamEvent&)> on_event,
        const ObserveConfig& observe = ObserveConfig(),
        const RecoveryPolicy& policy = RecoveryPolicy());

    StreamArbiter(const StreamArbiter&) = delete;
    StreamArbiter& operator=(const StreamArbiter&) = delete;

    // -- Life cycle -----------------------------------------------------------

    /// Entry point of open(): starts this camera (idempotent).
    void begin();

    /// Waits until the stream is ready, or fails.
    /// \return address your player can open
    /// \throws VideoError / VideoTimeoutError
    std::string wait_ready(double timeout_s = -1.0);

    /// Called periodically by Manager's supervisor thread.
    void tick(double now);

    /// Called by close(): drops this user (idempotent).
    void release(LossReason reason = LossReason::Closed, const std::string& message = "");

    /// Called by stop_stream(): resets to Stopped and stops recovering.
    void force_stopped(const std::string& message = "Stopped by stop_stream()");

    // -- Read-only --------------------------------------------------------------

    CameraId camera() const { return camera_; }
    const std::string& uri() const { return uri_; }
    StreamState state() const;
    bool sdk_started() const;

    /// Whether this stream is in a phase that needs quick sampling.
    bool needs_fast_sample() const;

    CameraStreamInfo info() const;

private:
    // -- Per-state logic --
    void tick_prepare(double now);
    void tick_ready(double now);
    void tick_recover(double now);

    // -- State transitions --
    void become_ready(StreamOwner owner, RecoveredBy recovered_by = RecoveredBy::None);
    void enter_recovering(LossReason reason, const std::string& message);
    void fail(LossReason reason, const std::string& message);

    // -- Actions --
    bool issue_start(double now);
    RestartOutcome try_restart(double now, LossReason reason);
    void do_action(RecoveredBy action, double now, LossReason reason);
    bool controller_reachable() const;
    bool used_l2() const;

    /// Updates the byte counter difference; true when data grew since the
    /// previous sample.
    bool sample(const StreamStatus& status, double now);

    void emit(const StreamEvent& event);

    std::string fail_message(LossReason reason) const;

    CameraId camera_;
    std::string uri_;
    const StatusProbe* probe_;
    StreamingController* controller_;
    std::function<void(const StreamEvent&)> on_event_;
    ObserveConfig observe_;
    RecoveryPolicy policy_;

    mutable std::mutex mutex_;
    std::condition_variable cv_;

    StreamState state_ = StreamState::Stopped;
    StreamOwner owner_ = StreamOwner::Unknown;
    LossReason reason_ = LossReason::None;
    std::string message_;

    // starting up / recovering
    double deadline_ = 0.0;
    bool sdk_started_ = false;
    bool start_issued_ = false;
    RecoveredBy recovered_by_ = RecoveredBy::None;

    // byte counter difference
    long long prev_bytes_ = -1;
    double prev_at_ = -1.0;
    double prev_fetch_at_ = -1.0;
    bool last_grew_ = false;
    int stall_count_ = 0;
    double no_growth_since_ = -1.0;
    double bitrate_kbps_ = -1.0;

    // recovery scheduling
    int attempt_ = 0;
    double next_attempt_at_ = 0.0;
    bool acting_ = false;
    double act_deadline_ = 0.0;
    double recover_started_at_ = 0.0;
    std::vector<double> restart_times_;
};


// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

namespace {
/// Sleeps in small steps (used only on the rare "is anyone watching?" path).
} // namespace

inline StreamArbiter::StreamArbiter(CameraId camera, const std::string& uri, const StatusProbe* probe,
    StreamingController* controller, std::function<void(const StreamEvent&)> on_event,
    const ObserveConfig& observe, const RecoveryPolicy& policy)
    : camera_(camera)
    , uri_(uri)
    , probe_(probe)
    , controller_(controller)
    , on_event_(std::move(on_event))
    , observe_(observe)
    , policy_(policy)
{
}

// -----------------------------------------------------------------------------
// Read-only
// -----------------------------------------------------------------------------

inline StreamState StreamArbiter::state() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return state_;
}

inline bool StreamArbiter::sdk_started() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return sdk_started_;
}

inline bool StreamArbiter::needs_fast_sample() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return state_ == StreamState::Preparing || state_ == StreamState::Recovering;
}

inline CameraStreamInfo StreamArbiter::info() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    CameraStreamInfo info;
    info.camera = camera_;
    info.state = state_;
    info.owner = owner_;
    // the address belongs to the camera and stays valid while it streams
    info.uri = uri_;
    info.codec = kStreamCodec;
    info.bitrate_kbps = bitrate_kbps_;
    info.reason = reason_;
    info.message = message_;
    return info;
}

inline bool StreamArbiter::used_l2() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return recovered_by_ == RecoveredBy::L2Restart;
}

inline bool StreamArbiter::controller_reachable() const
{
    return controller_ != nullptr && controller_->reachable();
}

inline std::string StreamArbiter::fail_message(LossReason reason) const
{
    if (reason == LossReason::PortUnreachable) {
        return "Cannot reach the robot's streaming service. Check that this host and "
               "the robot are on the same network.";
    }
    if (reason == LossReason::Stall) {
        return "The camera is set to stream but sends no picture data; automatic "
               "recovery gave up.";
    }
    return "The camera did not start streaming in time. It may still be starting up: "
           "try again in a few seconds.";
}

// -----------------------------------------------------------------------------
// Life cycle
// -----------------------------------------------------------------------------

inline void StreamArbiter::begin()
{
    const double now = monotonic_s();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (state_ == StreamState::Ready || state_ == StreamState::Preparing) {
            return; // idempotent
        }
        state_ = StreamState::Preparing;
        reason_ = LossReason::None;
        message_.clear();
        deadline_ = now + observe_.ready_timeout;
        start_issued_ = false;
        sdk_started_ = false;
        owner_ = StreamOwner::Unknown;
        recovered_by_ = RecoveredBy::None;
        attempt_ = 0;
        acting_ = false;
        next_attempt_at_ = 0.0;
        restart_times_.clear();
        prev_bytes_ = -1;
        prev_at_ = -1.0;
        prev_fetch_at_ = -1.0;
        last_grew_ = false;
        stall_count_ = 0;
        no_growth_since_ = -1.0;
        bitrate_kbps_ = -1.0;
    }
    cv_.notify_all();
}

inline std::string StreamArbiter::wait_ready(double timeout_s)
{
    const double limit = timeout_s > 0.0 ? timeout_s : observe_.ready_timeout;
    const double end = monotonic_s() + limit;
    std::unique_lock<std::mutex> lock(mutex_);
    while (true) {
        if (state_ == StreamState::Ready) {
            return uri_;
        }
        if (state_ == StreamState::Error) {
            // 按 reason 归类：用户可以 catch VideoConnectionError / VideoTimeoutError，
            // 而不是只能 catch 基类（原有的 catch VideoError 仍然照常工作）。
            throw_video_error(camera_label(camera_) + ": stream is not ready: " +
                                  (message_.empty() ? std::string(to_string(reason_)) : message_),
                reason_);
        }
        if (state_ == StreamState::Stopped) {
            throw VideoError(camera_label(camera_) + ": opening was cancelled",
                LossReason::Closed);
        }
        const double remaining = end - monotonic_s();
        if (remaining <= 0.0) {
            break;
        }
        cv_.wait_for(lock, std::chrono::duration<double>(std::min(remaining, 0.2)));
    }
    std::ostringstream message;
    message << camera_label(camera_) << ": the stream was not ready within " << limit
            << " s. It may still be starting up: try again in a few seconds.";
    throw VideoTimeoutError(message.str(), LossReason::NoData);
}

inline void StreamArbiter::release(LossReason reason, const std::string& message)
{
    StreamState old = StreamState::Stopped;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        old = state_;
        if (old == StreamState::Stopped) {
            return;
        }
        state_ = StreamState::Stopping;
    }

    StreamEvent event;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        state_ = StreamState::Stopped;
        reason_ = reason;
        message_ = message;
        deadline_ = 0.0;
        acting_ = false;
        prev_bytes_ = -1;
        prev_at_ = -1.0;
        prev_fetch_at_ = -1.0;
        stall_count_ = 0;
        bitrate_kbps_ = -1.0;
        event.kind = StreamEventKind::Closed;
        event.camera = camera_;
        event.old_state = old;
        event.new_state = StreamState::Stopped;
        event.reason = reason;
        event.uri = uri_;
        event.message = message;
        event.timestamp_ns = monotonic_ns();
    }
    cv_.notify_all();
    emit(event);
}

inline void StreamArbiter::force_stopped(const std::string& message)
{
    StreamState old = StreamState::Stopped;
    StreamEvent event;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        old = state_;
        state_ = StreamState::Stopped;
        sdk_started_ = false;
        start_issued_ = false;
        reason_ = LossReason::Closed;
        message_ = message;
        acting_ = false;
        prev_bytes_ = -1;
        prev_at_ = -1.0;
        prev_fetch_at_ = -1.0;
        stall_count_ = 0;
        bitrate_kbps_ = -1.0;
        event.kind = StreamEventKind::Closed;
        event.camera = camera_;
        event.old_state = old;
        event.new_state = StreamState::Stopped;
        event.reason = LossReason::Closed;
        event.uri = uri_;
        event.message = message;
        event.timestamp_ns = monotonic_ns();
    }
    cv_.notify_all();
    if (old != StreamState::Stopped) {
        emit(event);
    }
}

// -----------------------------------------------------------------------------
// Supervisor tick
// -----------------------------------------------------------------------------

inline void StreamArbiter::tick(double now)
{
    if (now <= 0.0) {
        now = monotonic_s();
    }
    StreamState state = StreamState::Stopped;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        state = state_;
    }
    if (state == StreamState::Preparing) {
        tick_prepare(now);
    } else if (state == StreamState::Ready) {
        tick_ready(now);
    } else if (state == StreamState::Recovering) {
        tick_recover(now);
    }
}

// ---------------------------------------------------------------- start up

inline void StreamArbiter::tick_prepare(double now)
{
    if (probe_ == nullptr) {
        fail(LossReason::NoData, "The camera state could not be read.");
        return;
    }
    const StreamStatus status = probe_->status(camera_, true);
    const bool grew = sample(status, now);

    double deadline = 0.0;
    bool started = false;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        deadline = deadline_;
        started = sdk_started_;
    }

    if (status.has_producer()) {
        if (grew) {
            become_ready(started ? StreamOwner::Sdk : StreamOwner::External);
            return;
        }
        // A stream that is already running is adopted only once the byte counter
        // really grew between two samples. A non-zero count alone is not
        // evidence: a stream that was just stopped (or one that is stuck) keeps
        // reporting its historical count for a moment, and adopting it hands the
        // caller an address that answers 404.
        // A genuinely running stream grows within one poll interval
        // (prepare_poll); one that never grows falls through to the ready
        // deadline below, and one that disappears is started below as well.
        double since = -1.0;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (no_growth_since_ < 0.0) {
                no_growth_since_ = now;
            }
            since = no_growth_since_;
        }
        if ((now - since) >= observe_.prepare_stall_seconds) {
            if (started) {
                // the stream exists but carries nothing: restart it
                if (try_restart(now, LossReason::Stall) == RestartOutcome::Limit) {
                    fail(LossReason::Stall, fail_message(LossReason::Stall));
                }
                return;
            }
            // Somebody else's stream is sitting there without carrying any data
            // (it was just stopped, or it is stuck). That is not "already
            // running" in any useful sense, and adopting it would hand the
            // caller an address that answers 404, so take it over with an
            // idempotent start() and let the normal stall / restart logic heal
            // it from here.
            if (!issue_start(now)) {
                return;
            }
        }
    } else {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            no_growth_since_ = -1.0;
        }
        if (!started) {
            if (!issue_start(now)) {
                return;
            }
        } else if (now >= deadline) {
            const LossReason reason =
                controller_reachable() ? LossReason::NoData : LossReason::PortUnreachable;
            fail(reason, fail_message(reason));
            return;
        }
    }

    if (now >= deadline) {
        const LossReason reason =
            controller_reachable() ? LossReason::NoData : LossReason::PortUnreachable;
        fail(reason, fail_message(reason));
    }
}

// ---------------------------------------------------------------- observe

inline void StreamArbiter::tick_ready(double now)
{
    if (probe_ == nullptr) {
        return;
    }
    const StreamStatus status = probe_->status(camera_, false);
    const bool grew = sample(status, now);
    if (!status.available) {
        return; // no state at all: change nothing
    }
    if (!status.has_producer()) {
        enter_recovering(LossReason::External, "The stream was stopped outside the SDK.");
        return;
    }
    int stall = 0;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        stall = stall_count_;
    }
    if (stall >= observe_.stall_samples && !grew) {
        enter_recovering(LossReason::Stall,
            "Streaming stalled: no new data in "
                + std::to_string(observe_.stall_samples) + " samples.");
    }
}

// ---------------------------------------------------------------- recover

inline void StreamArbiter::tick_recover(double now)
{
    if (probe_ == nullptr) {
        return;
    }
    const StreamStatus status = probe_->status(camera_, true);
    const bool grew = sample(status, now);

    bool acting = false;
    double act_deadline = 0.0;
    double next_at = 0.0;
    int attempt = 0;
    LossReason reason = LossReason::None;
    double started_at = 0.0;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        acting = acting_;
        act_deadline = act_deadline_;
        next_at = next_attempt_at_;
        attempt = attempt_;
        reason = reason_;
        started_at = recover_started_at_;
    }

    // recovery worked: the stream is back and data is flowing again
    if (status.available && status.has_producer() && grew) {
        become_ready(owner_, used_l2() ? RecoveredBy::L2Restart : RecoveredBy::L1Resume);
        return;
    }

    if (acting) {
        if (now < act_deadline) {
            return;
        }
        {
            std::lock_guard<std::mutex> lock(mutex_);
            acting_ = false;
            attempt_ = attempt + 1;
            attempt = attempt_;
        }
        if (reason == LossReason::PortUnreachable || !controller_reachable()) {
            fail(LossReason::PortUnreachable, fail_message(LossReason::PortUnreachable));
            return;
        }
        if (attempt > policy_.max_attempts) {
            fail(reason, "Automatic recovery failed after "
                + std::to_string(policy_.max_attempts) + " attempts.");
            return;
        }
        const size_t index = static_cast<size_t>(
            std::max(0, std::min(attempt - 1, static_cast<int>(policy_.backoff.size()) - 1)));
        const double backoff = policy_.backoff.empty() ? 0.5 : policy_.backoff[index];
        {
            std::lock_guard<std::mutex> lock(mutex_);
            next_attempt_at_ = now + backoff;
        }
        return;
    }

    if (now < next_at) {
        return;
    }
    if (now - started_at > observe_.ready_timeout * policy_.max_attempts) {
        fail(reason, "Automatic recovery timed out.");
        return;
    }

    if (reason == LossReason::Stall) {
        if (try_restart(now, reason) == RestartOutcome::Limit) {
            fail(reason,
                "The stream keeps stalling and automatic restarts are used up ("
                    + std::to_string(policy_.restart_max_per_window) + " in "
                    + std::to_string(static_cast<int>(policy_.restart_window / 60.0))
                    + " minutes).");
        }
    } else {
        do_action(RecoveredBy::L1Resume, now, reason);
    }
}

inline void StreamArbiter::enter_recovering(LossReason reason, const std::string& message)
{
    StreamState old = StreamState::Stopped;
    StreamEvent event;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        old = state_;
        if (old != StreamState::Ready) {
            return;
        }
        state_ = StreamState::Recovering;
        reason_ = reason;
        message_ = message;
        attempt_ = 0;
        acting_ = false;
        next_attempt_at_ = 0.0;
        recover_started_at_ = monotonic_s();
        stall_count_ = 0;
        no_growth_since_ = -1.0;
        const double window_start = recover_started_at_ - policy_.restart_window;
        std::vector<double> kept;
        for (double t : restart_times_) {
            if (t >= window_start) {
                kept.push_back(t);
            }
        }
        restart_times_.swap(kept);
        event.kind = StreamEventKind::Lost;
        event.camera = camera_;
        event.old_state = old;
        event.new_state = StreamState::Recovering;
        event.reason = reason;
        event.uri = uri_;
        event.message = message;
        event.timestamp_ns = monotonic_ns();
    }
    emit(event);
}

inline RestartOutcome StreamArbiter::try_restart(double now, LossReason reason)
{
    (void)reason;
    double last = -1.0;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        const double window_start = now - policy_.restart_window;
        std::vector<double> kept;
        for (double t : restart_times_) {
            if (t >= window_start) {
                kept.push_back(t);
            }
        }
        restart_times_.swap(kept);
        if (static_cast<int>(restart_times_.size()) >= policy_.restart_max_per_window) {
            return RestartOutcome::Limit; // out of attempts: give up
        }
        if (!restart_times_.empty()) {
            last = restart_times_.back();
        }
    }
    if (last > 0.0 && (now - last) < policy_.restart_cooldown) {
        // still cooling down: not a failure, just wait for the cooldown
        std::lock_guard<std::mutex> lock(mutex_);
        next_attempt_at_ = last + policy_.restart_cooldown;
        return RestartOutcome::Cooling;
    }
    if (!controller_reachable()) {
        fail(LossReason::PortUnreachable, fail_message(LossReason::PortUnreachable));
        return RestartOutcome::Unreachable;
    }
    try {
        controller_->stop();
        controller_->start();
    } catch (const std::exception&) {
        std::lock_guard<std::mutex> lock(mutex_);
        next_attempt_at_ = now + (policy_.backoff.empty() ? 0.5 : policy_.backoff[0]);
        no_growth_since_ = now;
        return RestartOutcome::Failed;
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        restart_times_.push_back(now);
        sdk_started_ = true;
        start_issued_ = true;
        recovered_by_ = RecoveredBy::L2Restart;
        acting_ = true;
        act_deadline_ = now + policy_.act_timeout;
        prev_bytes_ = -1;
        prev_at_ = -1.0;
        prev_fetch_at_ = -1.0;
        last_grew_ = false;
        stall_count_ = 0;
        no_growth_since_ = now;
        if (state_ == StreamState::Preparing) {
            deadline_ = std::max(deadline_, now + observe_.ready_timeout);
        }
    }
    return RestartOutcome::Done;
}

inline void StreamArbiter::do_action(RecoveredBy action, double now, LossReason reason)
{
    (void)reason;
    if (!controller_reachable()) {
        fail(LossReason::PortUnreachable, fail_message(LossReason::PortUnreachable));
        return;
    }
    try {
        // the plain recovery action is "resume"; restarts go through try_restart()
        (void)action;
        controller_->start();
    } catch (const std::exception&) {
        std::lock_guard<std::mutex> lock(mutex_);
        next_attempt_at_ = now + (policy_.backoff.empty() ? 0.5 : policy_.backoff[0]);
        return;
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        sdk_started_ = true;
        start_issued_ = true;
        recovered_by_ = action;
        acting_ = true;
        act_deadline_ = now + policy_.act_timeout;
        prev_bytes_ = -1;
        prev_at_ = -1.0;
        prev_fetch_at_ = -1.0;
        last_grew_ = false;
        stall_count_ = 0;
        no_growth_since_ = -1.0;
    }
}

inline void StreamArbiter::become_ready(StreamOwner owner, RecoveredBy recovered_by)
{
    StreamState old = StreamState::Stopped;
    StreamEvent event;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        old = state_;
        state_ = StreamState::Ready;
        owner_ = owner;
        reason_ = LossReason::None;
        acting_ = false;
        deadline_ = 0.0;
        stall_count_ = 0;
        no_growth_since_ = -1.0;
        message_.clear();
        if (recovered_by == RecoveredBy::None) {
            recovered_by_ = RecoveredBy::None;
        } else {
            recovered_by_ = recovered_by;
        }
        event.kind = recovered_by == RecoveredBy::None ? StreamEventKind::Ready
                                                       : StreamEventKind::Reconnected;
        event.camera = camera_;
        event.old_state = old;
        event.new_state = StreamState::Ready;
        event.reason = LossReason::None;
        event.recovered_by = recovered_by;
        event.uri = uri_;
        event.message = recovered_by == RecoveredBy::None
            ? std::string("Ready to play.")
            : std::string("Recovered (") + to_string(recovered_by)
                + "); watchers may have seen a short interruption.";
        event.timestamp_ns = monotonic_ns();
    }
    cv_.notify_all();
    emit(event);
}

inline void StreamArbiter::fail(LossReason reason, const std::string& message)
{
    StreamState old = StreamState::Stopped;
    StreamEvent event;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        old = state_;
        if (old == StreamState::Error) {
            return;
        }
        state_ = StreamState::Error;
        reason_ = reason;
        message_ = message;
        acting_ = false;
        deadline_ = 0.0;
        event.kind = StreamEventKind::Error;
        event.camera = camera_;
        event.old_state = old;
        event.new_state = StreamState::Error;
        event.reason = reason;
        event.uri = uri_;
        event.message = message;
        event.timestamp_ns = monotonic_ns();
    }
    cv_.notify_all();
    emit(event);
}

// ---------------------------------------------------------------- actions

inline bool StreamArbiter::issue_start(double now)
{
    (void)now;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (start_issued_) {
            return true;
        }
        start_issued_ = true;
    }
    if (!controller_reachable()) {
        fail(LossReason::PortUnreachable, fail_message(LossReason::PortUnreachable));
        return false;
    }
    try {
        controller_->start();
    } catch (const std::exception&) {
        std::lock_guard<std::mutex> lock(mutex_);
        start_issued_ = false;
        return true;
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        sdk_started_ = true;
        owner_ = StreamOwner::Sdk;
        prev_bytes_ = -1;
        prev_at_ = -1.0;
        prev_fetch_at_ = -1.0;
        last_grew_ = false;
        no_growth_since_ = -1.0;
    }
    return true;
}

// ---------------------------------------------------------------- difference

inline bool StreamArbiter::sample(const StreamStatus& status, double now)
{
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (status.fetched_at == prev_fetch_at_) {
            return last_grew_; // same snapshot as before: do not count it twice
        }
        prev_fetch_at_ = status.fetched_at;
    }

    long long prev = -1;
    double prev_at = -1.0;
    bool ready = false;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        prev = prev_bytes_;
        prev_at = prev_at_;
        ready = state_ == StreamState::Ready;
    }

    bool grew = false;
    double bitrate = -1.0;
    if (status.available) {
        if (prev >= 0 && status.bytes_recv > prev) {
            grew = true;
            if (prev_at > 0.0 && now > prev_at) {
                bitrate = static_cast<double>(status.bytes_recv - prev) * 8.0 / (now - prev_at) / 1000.0;
            }
        }
    }

    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (status.available) {
            prev_bytes_ = status.bytes_recv;
            prev_at_ = now;
        }
        if (grew) {
            stall_count_ = 0;
            no_growth_since_ = -1.0;
            if (bitrate >= 0.0) {
                bitrate_kbps_ = bitrate;
            }
        } else if (ready && status.available && status.has_producer()) {
            ++stall_count_;
        }
        last_grew_ = grew;
    }
    return grew;
}

// ---------------------------------------------------------------- events

inline void StreamArbiter::emit(const StreamEvent& event)
{
    if (!on_event_) {
        return;
    }
    try {
        on_event_(event);
    } catch (...) {
        // a callback that throws must not disturb the state machine
    }
}


} // namespace video
} // namespace robot
