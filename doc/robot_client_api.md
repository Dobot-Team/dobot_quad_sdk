# Robot Client API Reference

[English](robot_client_api.md) · [简体中文](robot_client_api.zh-CN.md)

Public API reference for the high-level robot client libraries:

| Language | File                                           | Class           |
| -------- | ---------------------------------------------- | --------------- |
| Python   | `high_level/python/dobot_quad/robot_client.py` | `RobotClient`   |
| C++      | `high_level/cpp/robot_client.h`                | `robot::Client` |

> **Scope:** High-level motion / state control via gRPC only.  
> **Transport:** `grpc_service.proto` (`grpc_comm` package).

---

## 1. Constructor / Connection

|               | Python                                  | C++                                |
| ------------- | --------------------------------------- | ---------------------------------- |
| **Signature** | `RobotClient(addr="192.168.5.2:50051")` | `Client(addr="192.168.5.2:50051")` |
| **Returns**   | `RobotClient` instance                  | `Client` instance                  |

| Parameter | Type                  | Default               | Description                       |
| --------- | --------------------- | --------------------- | --------------------------------- |
| `addr`    | `str` / `std::string` | `"192.168.5.2:50051"` | gRPC server address (`host:port`) |

**Behavior on construction:**

1. Opens an insecure gRPC channel to `addr`.
2. Queries the server for the current speed ratio via `get_state()` and stores the result locally.
3. Enables obstacle avoidance (`set_obstacle_avoidance(true)`) and stores the result locally.

**Context manager (Python only):**

```python
with RobotClient("192.168.5.2:50051") as robot:
    robot.balance_stand()
# channel auto-closed on exit
```

---

## 2. Query APIs

### 2.1 `get_state`

Returns the full robot telemetry snapshot from the server.

|               | Python                  | C++                                |
| ------------- | ----------------------- | ---------------------------------- |
| **Signature** | `get_state()`           | `get_state()`                      |
| **Returns**   | `GetRobotStateResponse` | `grpc_comm::GetRobotStateResponse` |

**`GetRobotStateResponse` fields:**

| Field                        | Type         | Description                                     |
| ---------------------------- | ------------ | ----------------------------------------------- |
| `success`                    | `bool`       | Whether the RPC succeeded                       |
| `message`                    | `string`     | Status / error message                          |
| `robot_state`                | `RobotState` | Joint, body, contact telemetry (see §2.1.1)     |
| `current_state`              | `string`     | Current FSM state name (e.g. `"balance_stand"`) |
| `current_speed_ratio`        | `int32`      | Current speed ratio `[10–100]`                  |
| `obstacle_avoidance_enabled` | `bool`       | Whether obstacle avoidance is currently active  |

#### 2.1.1 `RobotState` message

| Field                   | Type      | Length                    | Description                                      |
| ----------------------- | --------- | ------------------------- | ------------------------------------------------ |
| `jpos_leg`              | `float[]` | `num_leg × num_leg_joint` | Leg joint positions (rad)                        |
| `jpos_leg_des`          | `float[]` | same                      | Desired leg joint positions (rad)                |
| `jvel_leg`              | `float[]` | same                      | Leg joint velocities (rad/s)                     |
| `jvel_leg_des`          | `float[]` | same                      | Desired leg joint velocities (rad/s)             |
| `jtau_leg`              | `float[]` | same                      | Leg joint torques (Nm)                           |
| `jtau_leg_des`          | `float[]` | same                      | Desired leg joint torques (Nm)                   |
| `pos_body`              | `float[]` | 3                         | Body position `[x, y, z]` (m)                    |
| `vel_body`              | `float[]` | 3                         | Body linear velocity (m/s)                       |
| `acc_body`              | `float[]` | 3                         | Body linear acceleration (m/s²)                  |
| `omega_body`            | `float[]` | 3                         | Body angular velocity (rad/s)                    |
| `ori_body`              | `float[]` | 3                         | Body orientation `[roll, pitch, yaw]` (rad)      |
| `grf_left`              | `float[]` | 3                         | Left foot ground reaction force (N)              |
| `grf_right`             | `float[]` | 3                         | Right foot ground reaction force (N)             |
| `grf_vertical_filtered` | `float[]` | 2                         | Filtered vertical contact force (N)              |
| `temp`                  | `float[]` | 4                         | `[0–3]`: foot contact force totals & grf_x_total |

### 2.2 `get_motions`

Returns the motion library registered on the server.

|               | Python               | C++                             |
| ------------- | -------------------- | ------------------------------- |
| **Signature** | `get_motions()`      | `get_motions()`                 |
| **Returns**   | `GetMotionsResponse` | `grpc_comm::GetMotionsResponse` |

**`GetMotionsResponse` fields:**

| Field          | Type                  | Description                                       |
| -------------- | --------------------- | ------------------------------------------------- |
| `motions`      | `Motion[]`            | List of available motions with default parameters |
| `descriptions` | `map<string, string>` | `motion_id → description` mapping                 |
| `success`      | `bool`                | Whether the RPC succeeded                         |
| `message`      | `string`              | Status / error message                            |

### 2.3 `get_current_state_name`

Convenience wrapper: returns the FSM state name string only.

|               | Python                             | C++                                       |
| ------------- | ---------------------------------- | ----------------------------------------- |
| **Signature** | `get_current_state_name() -> str`  | `get_current_state_name() -> std::string` |
| **Returns**   | FSM state name, or `""` on failure | same                                      |

### 2.4 `get_speed_ratio`

Returns the locally tracked speed ratio. The value is updated whenever `set_speed_ratio()` is called (from the RPC response). It is **not** re-queried from the server each time, because `GetRobotState` may return stale values immediately after a `SetSpeedRatio` RPC.

|               | Python                     | C++                        |
| ------------- | -------------------------- | -------------------------- |
| **Signature** | `get_speed_ratio() -> int` | `get_speed_ratio() -> int` |
| **Returns**   | Speed ratio `[10–100]`     | same                       |

### 2.5 `get_obstacle_avoidance`

Returns the locally tracked obstacle avoidance state. The value is updated whenever `set_obstacle_avoidance()` is called (from the RPC response). It is **not** re-queried from the server each time.

|               | Python                             | C++                                |
| ------------- | ---------------------------------- | ---------------------------------- |
| **Signature** | `get_obstacle_avoidance() -> bool` | `get_obstacle_avoidance() -> bool` |
| **Returns**   | `True`/`true` if enabled           | same                               |

---

## 3. Configuration APIs

### 3.1 `set_speed_ratio`

Sets the robot speed ratio. Values outside `[10, 100]` are clamped silently.

|               | Python                        | C++                                |
| ------------- | ----------------------------- | ---------------------------------- |
| **Signature** | `set_speed_ratio(ratio: int)` | `set_speed_ratio(int ratio)`       |
| **Returns**   | `SetSpeedRatioResponse`       | `grpc_comm::SetSpeedRatioResponse` |

| Parameter | Type  | Range                | Description       |
| --------- | ----- | -------------------- | ----------------- |
| `ratio`   | `int` | `[10–100]` (clamped) | Speed ratio value |

**`SetSpeedRatioResponse` fields:**

| Field                 | Type     | Description                              |
| --------------------- | -------- | ---------------------------------------- |
| `success`             | `bool`   | Whether the RPC succeeded                |
| `message`             | `string` | Status message                           |
| `current_speed_ratio` | `int32`  | The effective speed ratio after the call |

### 3.2 `set_obstacle_avoidance`

Enables or disables obstacle avoidance.

> Server behavior: when toggled by client RPC, the controller now also triggers
> voice prompts (`avoid_obstacle_on.wav` / `avoid_obstacle_off.wav`) for parity
> with gamepad-triggered toggles.

|               | Python                           | C++                                                 |
| ------------- | -------------------------------- | --------------------------------------------------- |
| **Signature** | `set_obstacle_avoidance(enable)` | `set_obstacle_avoidance(bool enable)`               |
| **Overload**  | —                                | `set_obstacle_avoidance(const std::string& enable)` |
| **Returns**   | `SetObstacleAvoidanceResponse`   | `grpc_comm::SetObstacleAvoidanceResponse`           |

| Parameter | Type           | Accepted Values                | Description                                    |
| --------- | -------------- | ------------------------------ | ---------------------------------------------- |
| `enable`  | `bool` / `str` | `True`/`False`, `"on"`/`"off"` | Enable or disable; invalid string raises error |

**`SetObstacleAvoidanceResponse` fields:**

| Field             | Type     | Description                        |
| ----------------- | -------- | ---------------------------------- |
| `success`         | `bool`   | Whether the RPC succeeded          |
| `message`         | `string` | Status message                     |
| `current_enabled` | `bool`   | The effective state after the call |

---

## 4. Execution API

### 4.1 `execute`

Low-level entry point: sends a motion sequence to the server and streams progress in real time.

|               | Python                                                     | C++                                                             |
| ------------- | ---------------------------------------------------------- | --------------------------------------------------------------- |
| **Signature** | `execute(*motions, loop=False, show_progress=True)`        | `execute(ExecuteSequenceRequest& req, bool show_progress=true)` |
| **Returns**   | Final `SequenceProgress` or `None` (cancelled / RPC error) | `bool` (`true` = success)                                       |

**Python `motions` argument format:**

| Form    | Example                                            | Description                  |
| ------- | -------------------------------------------------- | ---------------------------- |
| `str`   | `"balance_stand"`                                  | Motion ID with no parameters |
| `tuple` | `("line_walk", {"direction": 0, "distance": 3.0})` | Motion ID + parameter dict   |

**Common runtime behavior:**

- Prints real-time progress to stdout when `show_progress=true`.
- `Ctrl+C` gracefully cancels the execution.
- Automatically sends `TryCancel` to the server on interruption.

**`SequenceProgress` fields (streamed):**

| Field               | Type     | Description                                           |
| ------------------- | -------- | ----------------------------------------------------- |
| `current_index`     | `int32`  | Zero-based index of the currently executing motion    |
| `total_motions`     | `int32`  | Total number of motions in the sequence               |
| `current_motion_id` | `string` | ID of the currently executing motion                  |
| `current_state`     | `string` | Current FSM state                                     |
| `is_final`          | `bool`   | `true` on the final progress message                  |
| `success`           | `bool`   | Overall execution result (valid only when `is_final`) |
| `message`           | `string` | Status / error message                                |
| `execution_id`      | `string` | Unique execution identifier                           |

---

## 5. State Switching APIs

All state-switching methods internally call `execute()` with the corresponding motion ID.
Methods use clean names (no `set_` prefix).

| Python Return                | C++ Return |
| ---------------------------- | ---------- |
| `SequenceProgress` or `None` | `bool`     |

### 5.1 Generic entry

| Method                    | Parameter                                         | Description                                                             |
| ------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------- |
| `set_target_state(state)` | `state`: FSM state name string (case-insensitive) | Switch to any named state. Raises `ValueError` for unknown state names. |

**Valid state names:** `passive`, `ready`, `stand_down`, `balance_stand`, `walk`, `flying_trot`, `rl`, `dance0`, `wave`, `jump`, `backflip`, `recovery`.

### 5.2 Predefined states

| Method            | FSM State       | Alias         | Notes                                          |
| ----------------- | --------------- | ------------- | ---------------------------------------------- |
| `passive()`       | `passive`       | `emergency()` | Emergency stop (immediate passive)             |
| `ready()`         | `ready`         | —             | Slow lie-down from any state                   |
| `stand_down()`    | `stand_down`    | —             | Lie down                                       |
| `balance_stand()` | `balance_stand` | —             | Balance stand (prerequisite for many motions)  |
| `walk()`          | `walk`          | —             | Walk state                                     |
| `flying_trot()`   | `flying_trot`   | —             | Running gait                                   |
| `dance0()`        | `dance0`        | `dance()`     | Dance action                                   |
| `wave()`          | `wave`          | `wave_hand()` | Greeting action                                |
| `jump()`          | `jump`          | —             | Jump action                                    |
| `backflip()`      | `backflip`      | —             | Backflip action                                |
| `recovery()`      | `recovery`      | —             | Recovery action                                |
| `change_mode()`   | —               | —             | Toggle leg configuration (parallel ↔ X-shaped) |

### 5.3 Leg configuration

| Method        | Python Signature | C++ Signature   | Description                                                                                            |
| ------------- | ---------------- | --------------- | ------------------------------------------------------------------------------------------------------ |
| `change_mode` | `change_mode()`  | `change_mode()` | Toggle leg configuration (parallel ↔ X-shaped). No parameters, toggles between the two configurations. |

---

## 6. Locomotion APIs

### 6.1 Straight-line walk

When `speed_ratio` is explicitly provided, the method temporarily sets the speed ratio and disables obstacle avoidance, then restores previous values after completion. When `speed_ratio` is omitted (default `None` / `-1`), the current base speed ratio is used and no save/restore occurs.

| Method          | Python Signature                                         | C++ Signature                                                         |
| --------------- | -------------------------------------------------------- | --------------------------------------------------------------------- |
| `line_walk`     | `line_walk(direction=0, distance=3.0, speed_ratio=None)` | `line_walk(int direction=0, float distance=3.0f, int speed_ratio=-1)` |
| `walk_forward`  | `walk_forward(distance=3.0, speed_ratio=None)`           | `walk_forward(float dist=3.0f, int sr=-1)`                            |
| `walk_backward` | `walk_backward(distance=3.0, speed_ratio=None)`          | `walk_backward(float dist=3.0f, int sr=-1)`                           |
| `move_left`     | `move_left(distance=3.0, speed_ratio=None)`              | `move_left(float dist=3.0f, int sr=-1)`                               |
| `move_right`    | `move_right(distance=3.0, speed_ratio=None)`             | `move_right(float dist=3.0f, int sr=-1)`                              |

**`line_walk` parameters:**

| Parameter     | Type               | Range                                                          | Description                                                                                 |
| ------------- | ------------------ | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `direction`   | `int` / `str` (Py) | `0`/`"forward"`, `1`/`"backward"`, `2`/`"left"`, `3`/`"right"` | Walk direction. Raises `ValueError` for invalid values.                                     |
| `distance`    | `float`            | `[0, 3]` m (clamped)                                           | Walk distance in meters                                                                     |
| `speed_ratio` | `int` or `None`    | `None` (use current) or `[10, 100]` (clamped)                  | Optional speed ratio override. When provided, temporarily set and restored after execution. |

### 6.2 Rotation

| Method         | Python Signature                                         | C++ Signature                                                                                            |
| -------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `rotate`       | `rotate(direction="left", angle=90.0)`                   | `rotate(int direction=0, float angle=90.0f)` / `rotate(const std::string& direction, float angle=90.0f)` |
| `rotate_left`  | `rotate_left(angle=90.0)`                                | `rotate_left(float angle=90.0f)`                                                                         |
| `rotate_right` | `rotate_right(angle=90.0)`                               | `rotate_right(float angle=90.0f)`                                                                        |
| `circle`       | `circle(direction="left", turns=1)`                      | `circle(const std::string& direction="left", int turns=1)`                                               |
| `rotate_walk`  | `rotate_walk(angle=0.0, distance=0.0, speed_ratio=None)` | `rotate_walk(float angle_deg=0.0f, float distance_m=0.0f, int speed_ratio=-1)`                           |

**`rotate` parameters:**

| Parameter   | Type          | Accepted Values                     | Description                                                 |
| ----------- | ------------- | ----------------------------------- | ----------------------------------------------------------- |
| `direction` | `str` / `int` | `"left"` / `"right"` (or `0` / `1`) | Rotation direction. Raises `ValueError` for invalid values. |
| `angle`     | `float`       | `[0, 360]` degrees (clamped)        | Rotation angle                                              |

**`circle` parameters:**

| Parameter   | Type  | Range                | Description          |
| ----------- | ----- | -------------------- | -------------------- |
| `direction` | `str` | `"left"` / `"right"` | Direction            |
| `turns`     | `int` | `[1, 10]` (clamped)  | Number of full turns |

**`rotate_walk` parameters:**

| Parameter     | Type            | Range                                         | Description                                                                                 |
| ------------- | --------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `angle`       | `float`         | `[-180, 180]` deg (clamped)                   | Heading angle. Positive = counter-clockwise (left turn), Negative = clockwise (right turn). |
| `distance`    | `float`         | `[0, 3]` m (clamped)                          | Forward walk distance after rotation                                                        |
| `speed_ratio` | `int` or `None` | `None` (use current) or `[10, 100]` (clamped) | Optional speed ratio override for the walk phase                                            |

### 6.3 Velocity sequence

Direct velocity control. When `speed_ratio` is explicitly provided, temporarily sets the speed ratio and disables obstacle avoidance, then restores after completion. When omitted (default `None` / `-1`), uses the current base speed ratio with no save/restore.

|               | Python                                                                             | C++                                                                                                                     |
| ------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Signature** | `velocity_sequence(vel_seq, gait="walk", speed_ratio=None, stand_down_after=True)` | `velocity_sequence(const std::string& vel_seq, ...)` / `velocity_sequence(const std::vector<VelocityStep>& steps, ...)` |
| **Returns**   | `SequenceProgress` / `None`                                                        | `bool`                                                                                                                  |

**Parameters:**

| Parameter          | Type                                                                             | Description                                                                                 |
| ------------------ | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `vel_seq`          | `str` or `list[tuple]` (Py) / `std::string` or `std::vector<VelocityStep>` (C++) | Velocity commands; string format: `"vx,vy,vyaw,dur;..."`                                    |
| `gait`             | `str`                                                                            | `"walk"` or `"flying_trot"`. Raises `ValueError` for invalid gait.                          |
| `speed_ratio`      | `int` or `None`                                                                  | Optional speed ratio override `[10–100]` (clamped). Default `None`/`-1` = use current base. |
| `stand_down_after` | `bool`                                                                           | Append `stand_down` motion at the end                                                       |

**`VelocityStep` struct (C++):**

| Field      | Type    | Description                                        |
| ---------- | ------- | -------------------------------------------------- |
| `vx`       | `float` | Forward (+) / backward (−) velocity (m/s)          |
| `vy`       | `float` | Strafe left (+) / right (−) velocity (m/s)         |
| `vyaw`     | `float` | Turn left (+) / right (−) angular velocity (rad/s) |
| `duration` | `float` | Duration of this step (s)                          |

---

## 7. Pose / Balance APIs

All balance methods require `balance_stand` state as a prerequisite (handled internally).

**Two modes:**

- `"dynamic"` — sinusoidal sweep: 0 → target → 0 over the specified duration.
- `"static"` — smoothly transition to target (0.5s), hold for duration, smoothly transition back to 0 (0.5s).

### 7.1 Single-axis balance motions

| Method            | Python Signature                                      | C++ Signature                                                                         | Description                                        |
| ----------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `balance_pitch`   | `balance_pitch(value, duration=2.0, mode="dynamic")`  | `balance_pitch(float value, float duration=2.0f, const std::string& mode="dynamic")`  | Pitch (nod). `>0` forward, `<0` backward. Degrees. |
| `balance_yaw`     | `balance_yaw(value, duration=2.0, mode="dynamic")`    | `balance_yaw(float value, float duration=2.0f, const std::string& mode="dynamic")`    | Yaw (look). `>0` left, `<0` right. Degrees.        |
| `balance_roll`    | `balance_roll(value, duration=2.0, mode="dynamic")`   | `balance_roll(float value, float duration=2.0f, const std::string& mode="dynamic")`   | Roll (lean). `>0` left, `<0` right. Degrees.       |
| `balance_height`  | `balance_height(value, duration=2.0, mode="dynamic")` | `balance_height(float value, float duration=2.0f, const std::string& mode="dynamic")` | Height delta. `<0` squat down. Meters.             |
| `balance_neutral` | `balance_neutral(duration=0.5)`                       | `balance_neutral(float duration=0.5f)`                                                | Return all axes to neutral                         |

| Parameter  | Type    | Range                                                                                        | Description                                             |
| ---------- | ------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `value`    | `float` | `roll: [-30, 30]°`, `pitch: [-15, 15]°`, `yaw: [-20, 20]°`, `height: [-0.12, 0]` m — clamped | Target offset value in degrees (rpy) or meters (height) |
| `duration` | `float` | `[0.5, 5]` s (clamped)                                                                       | Duration in seconds                                     |
| `mode`     | `str`   | `"dynamic"` / `"static"`                                                                     | Motion mode                                             |

**Valid `motion_id` values:** `balance_pitch`, `balance_yaw`, `balance_roll`, `balance_height`, `balance_neutral`. Invalid IDs raise `ValueError`.

### 7.2 Batch balance sequence

Executes multiple balance motions in a single RPC call — more efficient than individual calls.

|               | Python                      | C++                                                           |
| ------------- | --------------------------- | ------------------------------------------------------------- |
| **Signature** | `balance_sequence(motions)` | `balance_sequence(const std::vector<BalanceMotion>& motions)` |
| **Returns**   | `SequenceProgress` / `None` | `bool`                                                        |

**`motions` format:**

| Language | Format                                                                               |
| -------- | ------------------------------------------------------------------------------------ |
| Python   | `list[tuple(motion_id: str, value: float, duration: float, mode: str)]`              |
| C++      | `std::vector<BalanceMotion>` where `BalanceMotion{motion_id, value, duration, mode}` |

Validates `motion_id` and clamps `value` to the valid range per axis.

### 7.3 Composite poses: `dynamic_pose` / `static_pose`

Control roll, pitch, yaw, and height **simultaneously** in a single server-side motion.

- `dynamic_pose` — sinusoidal sweep on all axes: 0 → target → 0 over the duration.
- `static_pose` — smoothly transition to target, hold for duration, smoothly transition back to 0.

|               | Python                                                                       | C++                                                                                                    |
| ------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **Signature** | `dynamic_pose(duration=2.0, roll_deg=0, pitch_deg=0, yaw_deg=0, height_m=0)` | `dynamic_pose(float duration, float roll_deg=0, float pitch_deg=0, float yaw_deg=0, float height_m=0)` |
|               | `static_pose(duration=2.0, roll_deg=0, pitch_deg=0, yaw_deg=0, height_m=0)`  | `static_pose(float duration, float roll_deg=0, float pitch_deg=0, float yaw_deg=0, float height_m=0)`  |
| **Returns**   | `SequenceProgress` / `None`                                                  | `bool`                                                                                                 |

| Parameter   | Type    | Range                    | Description                    |
| ----------- | ------- | ------------------------ | ------------------------------ |
| `duration`  | `float` | `[1, 5]` s (clamped)     | Duration in seconds            |
| `roll_deg`  | `float` | `[-30, 30]°` (clamped)   | Roll angle. `0` = no motion.   |
| `pitch_deg` | `float` | `[-15, 15]°` (clamped)   | Pitch angle. `0` = no motion.  |
| `yaw_deg`   | `float` | `[-20, 20]°` (clamped)   | Yaw angle. `0` = no motion.    |
| `height_m`  | `float` | `[-0.12, 0]` m (clamped) | Height delta. `0` = no motion. |

---

## 8. Safety & Resource Management

### 8.1 `enable_safety_ready`

Registers a Ctrl+C handler. When Ctrl+C is pressed, the current motion is cancelled and the robot transitions to `ready` before the process exits.

|               | Python                        | C++                                  |
| ------------- | ----------------------------- | ------------------------------------ |
| **Signature** | `robot.enable_safety_ready()` | `robot::enable_safety_ready(client)` |
| **Returns**   | `None`                        | `void`                               |

> **Note:** The handler only triggers on Ctrl+C (SIGINT). Normal program exit does **not** call `ready()`.

### 8.2 Resource management

|                 | Python                   | C++                                         |
| --------------- | ------------------------ | ------------------------------------------- |
| Close channel   | `close()`                | _(destructor)_                              |
| Context manager | `__enter__` / `__exit__` | —                                           |
| Raw stub access | —                        | `operator->()` returns `gRPCService::Stub*` |

---

## 9. Parameter Validation Summary

| Parameter                               | Clamping Range                                                                     | Error Handling                                    |
| --------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------- |
| `speed_ratio`                           | `[10, 100]`                                                                        | Clamped silently                                  |
| `set_target_state` state name           | Must be a valid state                                                              | `ValueError` (Py) / `std::invalid_argument` (C++) |
| `velocity_sequence` gait                | `"walk"` / `"flying_trot"`                                                         | `ValueError` (Py) / `std::invalid_argument` (C++) |
| `line_walk` direction                   | `0–3` or `"forward"/"backward"/"left"/"right"`                                     | `ValueError` for invalid values                   |
| `line_walk` distance                    | `[0, 3]` m                                                                         | Clamped silently                                  |
| `line_walk` speed_ratio                 | `None` (use current) or `[10, 100]`                                                | Clamped silently when provided                    |
| `rotate` angle                          | `[0, 360]`                                                                         | Clamped silently                                  |
| `rotate` direction                      | `"left"` / `"right"` (or `0` / `1`)                                                | `ValueError` for invalid values                   |
| `circle` turns                          | `[1, 10]`                                                                          | Clamped silently                                  |
| `rotate_walk` angle                     | `[-180, 180]`                                                                      | Clamped silently                                  |
| `rotate_walk` distance                  | `[0, 3]` m                                                                         | Clamped silently                                  |
| `rotate_walk` speed_ratio               | `None` (use current) or `[10, 100]`                                                | Clamped silently when provided                    |
| Balance `value`                         | `roll: [-30, 30]°`, `pitch: [-15, 15]°`, `yaw: [-20, 20]°`, `height: [-0.12, 0]` m | Clamped silently                                  |
| Balance `duration`                      | `[0.5, 5]` s                                                                       | Clamped silently                                  |
| Balance `motion_id`                     | Must be a valid balance motion                                                     | `ValueError` for invalid IDs                      |
| `dynamic_pose` / `static_pose` angles   | `roll: [-30, 30]°`, `pitch: [-15, 15]°`, `yaw: [-20, 20]°`                         | Clamped silently                                  |
| `dynamic_pose` / `static_pose` height   | `[-0.12, 0]` m                                                                     | Clamped silently                                  |
| `dynamic_pose` / `static_pose` duration | `[1, 5]` s                                                                         | Clamped silently                                  |
| `set_obstacle_avoidance` string         | `"on"` / `"off"` only                                                              | `ValueError` (Py) / `std::invalid_argument` (C++) |

---

## 10. Block Name → API Quick Reference

| Block Name             | Python API                              | C++ API                                 |
| ---------------------- | --------------------------------------- | --------------------------------------- |
| passive                | `passive()`                             | `passive()`                             |
| emergency              | `emergency()`                           | `emergency()`                           |
| ready                  | `ready()`                               | `ready()`                               |
| stand_down             | `stand_down()`                          | `stand_down()`                          |
| balance_stand          | `balance_stand()`                       | `balance_stand()`                       |
| walk                   | `walk()`                                | `walk()`                                |
| flying_trot            | `flying_trot()`                         | `flying_trot()`                         |
| change_mode            | `change_mode()`                         | `change_mode()`                         |
| change_mode            | `change_mode()`                         | `change_mode()`                         |
| walk_forward           | `walk_forward(distance, speed_ratio)`   | `walk_forward(dist, sr)`                |
| walk_backward          | `walk_backward(distance, speed_ratio)`  | `walk_backward(dist, sr)`               |
| move_left              | `move_left(distance, speed_ratio)`      | `move_left(dist, sr)`                   |
| move_right             | `move_right(distance, speed_ratio)`     | `move_right(dist, sr)`                  |
| set_speed_ratio        | `set_speed_ratio(ratio)`                | `set_speed_ratio(ratio)`                |
| get_speed_ratio        | `get_speed_ratio()`                     | `get_speed_ratio()`                     |
| set_obstacle_avoidance | `set_obstacle_avoidance("on"/"off")`    | `set_obstacle_avoidance("on"/"off")`    |
| get_obstacle_avoidance | `get_obstacle_avoidance()`              | `get_obstacle_avoidance()`              |
| rotate                 | `rotate("left"/"right", angle)`         | `rotate("left"/"right", angle)`         |
| circle                 | `circle("left"/"right", turns)`         | `circle("left"/"right", turns)`         |
| rotate_walk            | `rotate_walk(angle, distance)`          | `rotate_walk(angle, distance)`          |
| dynamic_pose           | `dynamic_pose(duration, ...)`           | `dynamic_pose(duration, ...)`           |
| static_pose            | `static_pose(duration, ...)`            | `static_pose(duration, ...)`            |
| balance_pitch          | `balance_pitch(value, duration, mode)`  | `balance_pitch(value, duration, mode)`  |
| balance_yaw            | `balance_yaw(value, duration, mode)`    | `balance_yaw(value, duration, mode)`    |
| balance_roll           | `balance_roll(value, duration, mode)`   | `balance_roll(value, duration, mode)`   |
| balance_height         | `balance_height(value, duration, mode)` | `balance_height(value, duration, mode)` |
| balance_neutral        | `balance_neutral(duration)`             | `balance_neutral(duration)`             |
| dance                  | `dance()`                               | `dance()`                               |
| jump                   | `jump()`                                | `jump()`                                |
| wave_hand              | `wave_hand()`                           | `wave_hand()`                           |
| backflip               | `backflip()`                            | `backflip()`                            |
| enable_safety_ready    | `robot.enable_safety_ready()`           | `robot::enable_safety_ready(client)`    |

---

## 11. Changelog

### 2026-03-18

| Type        | Change                                                                                                                                                                                                                                                         |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Changed** | Refined balance clamp ranges: `roll ±30°`, `pitch ±15°`, `yaw ±20°`, `height [-0.12, 0]m`; single-axis duration `[0.5, 5]s`, composite pose duration `[1, 5]s`.                                                                                                |
| **Changed** | `set_obstacle_avoidance` now triggers OA on/off voice prompts server-side for client RPC calls as well.                                                                                                                                                        |
| **Changed** | `E3` now includes `change_mode` as an interactive/CLI action option.                                                                                                                                                                                           |
| **Changed** | `E6` now explicitly demonstrates `balance_pitch/yaw/roll/height` single-axis APIs (dynamic + static), plus `balance_sequence`, `dynamic_pose`, and `static_pose`.                                                                                              |
| **Changed** | `E9` now demonstrates the combo flow using the latest script order: state switching (`walk` + `change_mode` toggles), 1m cardinal moves, 90°/180° rotations, one full circle, single-axis balance motions (dynamic + static), and two composite balance poses. |

### 2026-07-22

| Type        | Change                                                                                                                                                           |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **New**     | `dynamic_pose(duration, roll_deg, pitch_deg, yaw_deg, height_m)` — composite sinusoidal pose controlling all axes simultaneously in a single server-side motion. |
| **New**     | `static_pose(duration, roll_deg, pitch_deg, yaw_deg, height_m)` — composite hold pose controlling all axes simultaneously.                                       |
| **New**     | `ready()` — slow lie-down state transition.                                                                                                                      |
| **New**     | `emergency()` — alias for `passive()`.                                                                                                                           |
| **New**     | `enable_safety_ready()` — auto-`ready()` on Ctrl+C (safety handler). Only triggers on SIGINT, not on normal program exit.                                        |
| **Changed** | Balance motions now use `value` (degrees for rpy, meters for height), `duration` (seconds), and `mode` ("dynamic"/"static") instead of amplitude/beats.          |
| **Changed** | `dynamic_pose` no longer takes `mode` parameter — it is always "dynamic". Use `static_pose` for "static" mode.                                                   |
| **Removed** | `set_bpm()` / `bpm()` — BPM is no longer used. Balance timing is now duration-based.                                                                             |
| **Removed** | `bpm` parameter from constructor and `execute()`.                                                                                                                |
| **Fixed**   | C++ segfault on normal program exit caused by atexit handler accessing destroyed client.                                                                         |
| **Fixed**   | Python `enable_safety_ready()` no longer triggers `ready()` on normal exit — only on Ctrl+C.                                                                     |

### 2026-07-20

| Type        | Change                                                                                                                                                                                                                                                                                                                                                                       |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Changed** | `speed_ratio` parameter default in `line_walk`, `walk_forward`, `walk_backward`, `move_left`, `move_right`, `velocity_sequence`, `rotate_walk` changed from `80` to `None` (Python) / `-1` (C++). When omitted, the current base speed ratio is used with no save/restore. When explicitly provided, the speed ratio is temporarily overridden and restored after execution. |
| **Changed** | `get_speed_ratio()` and `get_obstacle_avoidance()` now return locally tracked values instead of querying the server. Values are updated from `set_*` RPC responses. This avoids stale reads from the eventually-consistent `GetRobotState` RPC.                                                                                                                              |
| **Changed** | Constructor now seeds speed ratio from `get_state()` instead of `get_speed_ratio()`, and stores values locally rather than caching via server queries.                                                                                                                                                                                                                       |

### 2026-07-18

| Type        | Change                                                                                                                                                                                                                                                  |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **New**     | `x_leg(mode)` — switch between `"std"` (parallel) and `"x"` (X-shaped) leg modes                                                                                                                                                                        |
| **Changed** | `walk_left` → `move_left`, `walk_right` → `move_right`                                                                                                                                                                                                  |
| **Changed** | `line_walk` / `rotate_walk` distance range: `[0, 10]` → `[0, 3]` m                                                                                                                                                                                      |
| **Changed** | `circle` turns range: `[1, 5]` → `[1, 10]`                                                                                                                                                                                                              |
| **Changed** | Extracted reusable validation utility functions (`clamp_speed_ratio`, `clamp_distance`, `clamp_angle`, `clamp_turns`, `clamp_amplitude`, `validate_state`, `validate_balance_motion`, `validate_gait`, `resolve_direction`, `resolve_rotate_direction`) |
| **Changed** | C++ state methods now available without `set_` prefix (e.g. `balance_stand()` alongside `set_balance_stand()`)                                                                                                                                          |
| **Changed** | Constructor queries `get_speed_ratio()` instead of `set_speed_ratio(0)`                                                                                                                                                                                 |
| **Removed** | `rl` gait removed from `velocity_sequence`                                                                                                                                                                                                              |

---

## 12. Version

This document corresponds to the workspace implementation as of **2026-07-22**.
