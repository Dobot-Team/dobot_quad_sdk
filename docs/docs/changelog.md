# Changelog

## v1.3.0 — LED Control, Atomic Choreography Actions & Doc Fixes

### New Features

#### High-Level Leg LED Control
Users can now control the robot's four leg LED lights independently from the high-level API. Setting any leg light overrides the robot's built-in lighting logic; calling `reset_legs()` restores default lighting behavior.

- `set_legs_rgb(legs, color)` — Set multiple leg lights with a named color (OFF, RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, PURPLE, WHITE)
- `set_leg_rgb(leg, r, g, b)` — Set a single leg light with raw RGB values
- `set_leg_color(leg, color)` — Set a single leg light with a named color
- `set_leg_brightness(leg, brightness)` — Adjust brightness of a single leg light (0–255)
- `set_all_legs_rgb(r, g, b)` / `set_all_legs_color(color)` — Convenience wrappers for all four legs
- `reset_legs()` — Restore all leg lights to default lighting

Supported leg identifiers: `Leg.FL`, `Leg.FR`, `Leg.RL`, `Leg.RR`.  
See `high_level/python/examples/e11_led_control.py` / `high_level/cpp/e11_led_control.cpp`.

#### Atomic Choreography Actions (MINI_QUAD only)
Eight new choreography actions: `twirl_jump()`, `diag_step()`, `hop_step()`, `groove()`, `bounce()`, `body_wave()`, `hip_circle()`, `head_circle()`. Each action handles state transitions automatically and returns the robot to `WALK` when finished. Also available via `atomic_action("name")`.

#### Camera Video Streaming (`robot.video`)

Both cameras (front / rear RGB) can now be watched from your own player or
vision code. The SDK switches the stream on, watches it and returns an RTSP
address; it never decodes frames, so no media dependency is added.

- `video.open(camera)` — blocks until the camera is really streaming, then
  returns `rtsp://<ip>:8554/camera1` (front) or `.../camera2` (rear). Opening a
  camera that is already running is cheap and returns the same address.
- `video.is_streaming(camera)` / `video.get_stream_info(camera)` — state,
  address, who started the stream, current bitrate.
- `video.on_state_change(cb)` — stream events (lost / stopped elsewhere /
  recovered).
- `video.close(camera)` / `close_all()` — stops the stream only when nobody else
  is watching, so the phone app keeps working.
- `video.stop_stream(camera)` — force the robot to stop pushing.
- A dropped stream is resumed automatically, a stalled one is restarted; nothing
  to configure.
- C++: header-only (`robot_client.h` plus `video/video_client.h`), no extra
  library to link and no gRPC dependency. Python: `robot.video` on the existing
  client, no extra dependency.
- Examples: `high_level/python/examples/e12_video_stream.py` and
  `high_level/cpp/e12_video_stream.cpp`.

### Changes

- **Renamed `choreo()` → `gongxi()`**: The `choreo` state has been renamed to `gongxi` to better reflect the motion semantics. Added 11.5s post-trigger delay. **The old name keeps working for backward compatibility**: Python `RobotClient.choreo()`, C++ `Client::choreo()` and `Client::set_choreo()` now forward to `gongxi()` and emit a deprecation warning; `set_target_state("choreo")` is also accepted and mapped to `gongxi`.
- **URDF model files**: Updated robot model definitions for legged and wheel-legged variants.

### Documentation Fixes

- Added a **Typical Scenarios** page with copy-and-paste examples (both cameras on
  your PC, frames for your own algorithm)
- Documented the video headers and link requirements in the high-level API
  reference (section 2.15)
- Fixed broken README links pointing to non-existent `doc/` directory
- Updated project structure in README to reflect actual directories
- Fixed balance value ranges and rotate angle range in API docs to match actual code limits
- Fixed `clamp_angle_signed` direction sign error in code comments
- Removed non-existent `fill_light2` entry from low-level LED table
- Fixed formatting error in Chinese low-level API doc
- Fixed incomplete sentence in v1.0.9 changelog entry

### Example Fixes

- E7 voice publish (Python/C++): removed hardcoded audio file path `/root/test2.flac`, now accepts file path as command-line argument
- E8 voice subscribe (Python): fixed WAV file recording functionality (was declared but not implemented)
- E8 voice subscribe (Python/C++): corrected example numbering in comments from `e9` to `E8`; removed unused imports

## v1.2.0 — Robot Bow / Choreo Action & DDS Middleware Update

- Added `choreo` state support for quadruped robots.
- Added Python `RobotClient.choreo()` and C++ `RobotClient::choreo()` / `RobotClient::set_choreo()` APIs.
- Added `choreo` to the auto state-switching examples and state-switching tests.
- Updated bundled DDS middleware packages from `0.22.10` to `0.23.3` for `amd64` and `arm64`.
- Updated C++ and Python `e7_voice_pub` examples for the `VoiceCmd` schema used by `dds-middleware >= 0.23.x`.
- Regenerated English and Chinese API documentation and static site pages.

## v1.1.0 — Documentation Migration & DDS Middleware Update

- Migrated doc-related documentation to `docs` directory, added static webpage generation
- `dist` directory package updated to v0.22.10
- Added rear camera data acquisition topic in low_level documentation

## v1.0.9 — Balance Parameter Refactor & Composite Pose & Safety Handler

- `dynamic_pose(duration, roll_deg, pitch_deg, yaw_deg, height_m)` — Composite sine pose
- `static_pose(duration, roll_deg, pitch_deg, yaw_deg, height_m)` — Composite hold pose
- `ready()` — Slow stand down (safe stop) state
- `emergency()` — Alias for `passive()`
- `change_mode()` — Walk ⇄ Run smooth switch
- `enable_safety_ready()` — Auto `ready()` on Ctrl+C
- Balance action parameters: `amplitude/beats` → `value (degrees/meters), duration (seconds), mode ("dynamic"/"static")`
- `set_bpm()` / `bpm()` — BPM no longer used, timing based on seconds
- `bpm` parameter in constructor and `execute()`

## v1.0.8 — Speed Ratio Local Tracking & Optional Override

- `speed_ratio` parameter default changed from `80` to `None` (Python) / `-1` (C++), uses current base value when omitted
- `get_speed_ratio()` and `get_obstacle_avoidance()` now return local tracked values, no longer query server
- Constructor gets initial speed ratio via `get_state()`, stores locally

## v1.0.6 — Requirement Interface Specification Alignment

- `walk_left()` → `move_left()`
- `walk_right()` → `move_right()`
- Walk distance limit 10m → **3m**
- circle turns limit 5 → **10**
- rotate_walk distance limit 10m → **3m**
- `x_leg("std"/"x")` leg configuration switch
- Reusable parameter validation utilities (`clamp_distance`, `clamp_angle`, etc.)
- C++ `set_` prefix (`set_balance_stand()` → `balance_stand()`)
- `rl` gait
- C++ constructor `set_speed_ratio(0)` changed to `get_speed_ratio()`

## v1.0.0 — Initial Release

- Python `set_` prefix removal, `rl` gait removal
- Parameter range validation, direction string support
- ARM field removal
- Complete test suite (230 tests)
