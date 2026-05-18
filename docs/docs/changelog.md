# Changelog

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
