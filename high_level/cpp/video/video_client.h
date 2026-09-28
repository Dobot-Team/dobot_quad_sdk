#pragma once
// =============================================================================
// robot::Client::video() - include this header to drive the camera through the
// robot client.
//
//   #include "robot_client.h"         // motion control
//   #include "video/video_client.h"   // plus camera video streaming
//
//   robot::Client client("192.168.5.2:50051");
//   std::string uri = client.video().open(robot::video::CameraId::FrontRgb);
//
// Everything else of the video API stays in "video/video.h", which has no gRPC
// dependency: programs that only need the camera (and want to manage the camera
// themselves) include that header instead of this one.
// =============================================================================

#include "robot_client.h"

#include "video/video.h"

namespace robot {

inline video::Manager& Client::video()
{
    if (!video_manager_) {
        video_manager_.reset(new video::Manager(video_host_));
    }
    return *video_manager_;
}

} // namespace robot
