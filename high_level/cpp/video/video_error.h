#pragma once
// =============================================================================
// Errors reported by the camera video streaming API (robot::video).
//
// Every error carries a machine-readable reason, so callers can react to the
// cause instead of parsing the text:
//
//   try {
//       client.video().open(robot::video::CameraId::FrontRgb);
//   } catch (const robot::video::VideoError& error) {
//       std::cerr << error.what() << std::endl;     // says what to try next
//       if (error.reason() == robot::video::LossReason::PortUnreachable) { ... }
//   }
// =============================================================================

#include <stdexcept>
#include <string>

#include "video_types.h"

namespace robot {
namespace video {

// -----------------------------------------------------------------------------
// Exceptions
} // namespace video
} // namespace robot
