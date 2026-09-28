#pragma once
// =============================================================================
// Streaming switch on the robot (HTTP :22000) - start / stop / reachable.
//
// The switch is idempotent: starting a stream that is already running does not
// disturb whoever is watching it. It cannot be queried, so "is anything being
// pushed right now?" is answered by the camera state endpoint instead
// (see video_probe.h).
//
// The class holds no shared state - one connection per call - so it is safe to
// call from several threads.
// =============================================================================

#include <string>

#include "video_http.h"
#include "video_error.h"
#include "video_types.h"

namespace robot {
namespace video {

/// Sends the start / stop command to the robot.
class StreamingController
{
public:
    StreamingController(const std::string& host, int port = 22000, double timeout_s = 2.0)
        : host_(host)
        , port_(port)
        , timeout_s_(timeout_s)
    {
    }

    /// Start pushing this robot's camera streams (idempotent).
    /// \throws VideoConnectionError when the robot cannot be reached,
    ///         VideoTimeoutError when it does not answer in time
    void start()
    {
        post("start");
    }

    /// Stop pushing the robot's camera streams (idempotent).
    /// \note The switch is global: both cameras stop.
    void stop()
    {
        post("stop");
    }

    /// Whether the switch port accepts a TCP connection (quick "can I reach
    /// the robot" check).
    bool reachable(double timeout_s = -1.0) const
    {
        const double timeout = timeout_s > 0.0 ? timeout_s : (timeout_s_ < 1.0 ? timeout_s_ : 1.0);
        return tcp_reachable(host_, port_, timeout);
    }

    const std::string& host() const { return host_; }
    int port() const { return port_; }

private:
    void post(const std::string& action)
    {
        HttpResponse response;
        std::string error;
        const std::string path = "/settings/streaming/" + action;
        if (!http_request(host_, port_, "POST", path, "{}", timeout_s_, &response, &error)) {
            throw VideoConnectionError("Cannot reach the streaming service at " + host_ + ":"
                    + std::to_string(port_) + " (" + error
                    + "). Check that this host and the robot are on the same network.",
                LossReason::PortUnreachable);
        }
        if (response.status < 200 || response.status >= 300) {
            throw VideoConnectionError("Failed to " + action + " the stream: HTTP "
                    + std::to_string(response.status) + " from " + host_ + ":"
                    + std::to_string(port_),
                LossReason::PortUnreachable);
        }
    }

    std::string host_;
    int port_;
    double timeout_s_;
};

} // namespace video
} // namespace robot
