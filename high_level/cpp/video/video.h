#pragma once
// =============================================================================
// Camera video streaming (robot::video) - C++ API
//
// The SDK switches the stream on, watches it and hands you an RTSP address.
// Pulling, decoding and muxing are up to your own player or vision code.
//
// Headers of this feature:
//   video/video_client.h  client.video() - include this one when you drive the
//                         camera through the robot client (needs gRPC)
//   video/video.h         this file: the whole module, gRPC-free
//   video/video_error.h   the exception types thrown by the module
//
// Usage (through the robot client):
//   #include "robot_client.h"
//   #include "video/video_client.h"
//
//   robot::Client client("192.168.5.2:50051");
//
//   // Blocking: returns as soon as the stream is running and carrying data.
//   std::string uri = client.video().open(robot::video::CameraId::FrontRgb);
//   std::cout << uri << std::endl;             // rtsp://192.168.5.2:8554/camera1
//
//   // Open it with whatever you like, for example:
//   //   ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay <uri>
//   //   cv::VideoCapture cap(uri, cv::CAP_FFMPEG);
//
//   // Optional: get told about stream events (lost / stopped elsewhere / back).
//   client.video().on_state_change([](const robot::video::StreamEvent& e) {
//       std::cout << e.to_string() << std::endl;
//   });
//
//   // Finished watching. The stream is only stopped if nobody else is watching.
//   client.video().close(robot::video::CameraId::FrontRgb);
//
// Programs that do not use the robot client can include this header instead and
// use robot::video::Manager directly: no gRPC, no third-party library, POSIX
// sockets plus the C++ standard library only. The Python API (robot.video) has
// the same shape.
// =============================================================================

#include "video_arbiter.h"
#include "video_error.h"
#include "video_controller.h"
#include "video_http.h"
#include "video_json.h"
#include "video_manager.h"
#include "video_probe.h"
#include "video_types.h"
