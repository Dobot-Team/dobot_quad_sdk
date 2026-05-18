# High-Level API Reference

High-level robot client library public interface reference and example programs.

| Language | File                                           | Class           |
| -------- | ---------------------------------------------- | --------------- |
| Python   | `high_level/python/dobot_quad/robot_client.py` | `RobotClient`   |
| C++      | `high_level/cpp/robot_client.h`                | `robot::Client` |

!!! info "Transport Protocol"
`grpc_service.proto` (`grpc_comm` package), all calls via gRPC.

## 1. Quick Start

=== "Python"

    ```python
    from dobot_quad import RobotClient

    robot = RobotClient("192.168.5.2:50051")

    robot.balance_stand()            # Switch to balance stand
    robot.walk_forward(2.0)          # Walk forward 2 meters
    robot.move_left(1.0)             # Move left 1 meter
    robot.rotate("left", 90)         # Rotate left 90°
    robot.change_mode()              # Switch leg configuration
    robot.dance()                    # Dance
    robot.stand_down()               # Stand down
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"

    robot::Client client("192.168.5.2:50051");

    client.balance_stand();           // Switch to balance stand
    client.walk_forward(2.0);         // Walk forward 2 meters
    client.move_left(1.0);            // Move left 1 meter
    client.rotate("left", 90);        // Rotate left 90°
    client.change_mode();             // Switch leg configuration
    client.dance();                   // Dance
    client.stand_down();              // Stand down
    ```

### Wheeled Robot Quick Start

!!! info "Automatic Robot Type Detection"
The SDK uses `get_robot_type()` to automatically detect the connected robot type (legged `miniQuad` or wheeled `miniQuadW`).
Interfaces like `line_walk`, `rotate`, and `velocity_sequence` work on both robot types — the server automatically selects the appropriate motion controller.

=== "Python"

    ```python
    from dobot_quad import RobotClient

    robot = RobotClient("192.168.5.2:50051")

    print(robot.get_robot_type())     # "miniQuadW"
    print(robot.is_quad_wheel())      # True

    robot.wheel_loco()                # Switch to wheel locomotion
    robot.walk_forward(2.0)           # Walk forward 2 meters
    robot.move_left(1.0)              # Move left 1 meter
    robot.rotate("left", 90)          # Rotate left 90°
    robot.drift()                     # Switch to drift mode
    robot.change_mode()               # Switch leg configuration
    robot.handstand()                 # Handstand
    robot.stand_down()                # Stand down
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"

    robot::Client client("192.168.5.2:50051");

    std::cout << client.get_robot_type();  // "miniQuadW"
    std::cout << client.is_quad_wheel();   // true

    client.wheel_loco();                // Switch to wheel locomotion
    client.walk_forward(2.0);           // Walk forward 2 meters
    client.move_left(1.0);              // Move left 1 meter
    client.rotate("left", 90);          // Rotate left 90°
    client.drift();                     // Switch to drift mode
    client.change_mode();               // Switch leg configuration
    client.handstand();                 // Handstand
    client.stand_down();                // Stand down
    ```

## 2. Interface Reference

## 2.1 Constructor / Connection

=== "Python"

    ```python
    RobotClient(addr="192.168.5.2:50051")
    ```

=== "C++"

    ```cpp
    Client(addr="192.168.5.2:50051")
    ```

| Parameter | Type   | Default               | Description          |
| --------- | ------ | --------------------- | -------------------- |
| `addr`    | string | `"192.168.5.2:50051"` | gRPC service address |

**Constructor Behavior:**

1. Opens gRPC channel to `addr`.
2. Queries current speed ratio via `get_state()` and stores locally.
3. Enables obstacle avoidance (`set_obstacle_avoidance(true)`) and stores result locally.

=== "Python"

    ```python
    # Context manager (recommended)
    with RobotClient("192.168.5.2:50051") as robot:
        robot.balance_stand()
    # Channel auto-closes on exit
    ```

=== "C++"

    ```cpp
    robot::Client client("192.168.5.2:50051");
    client.balance_stand();
    // Auto-cleanup on destruction
    ```

## 2.2 Query Interfaces

### 2.2.1 get_state()

Returns complete robot telemetry state snapshot.

| Return Field                 | Type       | Description                          |
| ---------------------------- | ---------- | ------------------------------------ |
| `success`                    | bool       | RPC success                          |
| `current_state`              | string     | Current FSM state name               |
| `current_speed_ratio`        | int32      | Current speed ratio [10–100]         |
| `obstacle_avoidance_enabled` | bool       | Obstacle avoidance active            |
| `robot_state`                | RobotState | Joint, body, contact force telemetry |

`RobotState` Message Body:

| Field                     | Type     | Description                               |
| ------------------------- | -------- | ----------------------------------------- |
| `jpos_leg / jpos_leg_des` | float[]  | Leg joint position / desired (rad)        |
| `jvel_leg / jvel_leg_des` | float[]  | Leg joint velocity / desired (rad/s)      |
| `jtau_leg / jtau_leg_des` | float[]  | Leg joint torque / desired (Nm)           |
| `pos_body`                | float[3] | Body position [x, y, z] (m)               |
| `vel_body`                | float[3] | Body linear velocity (m/s)                |
| `acc_body`                | float[3] | Body linear acceleration (m/s²)           |
| `omega_body`              | float[3] | Body angular velocity (rad/s)             |
| `ori_body`                | float[3] | Body orientation [roll, pitch, yaw] (rad) |
| `grf_left / grf_right`    | float[3] | Left/right foot ground reaction force (N) |
| `grf_vertical_filtered`   | float[2] | Filtered vertical contact force (N)       |

### 2.2.2 get_motions()

Returns list of server-registered motion library.

### 2.2.3 get_current_state_name() → string

Gets current FSM state name. Returns empty string on failure.

### 2.2.4 get_speed_ratio() → int

Returns locally tracked speed ratio. Updated from RPC response on each `set_speed_ratio()` call.

### 2.2.5 get_obstacle_avoidance() → bool

Returns locally tracked obstacle avoidance state. Updated from RPC response on each `set_obstacle_avoidance()` call.

### 2.2.6 get_robot_type() → string

Returns robot type identifier string. Legged returns `"miniQuad"`, wheeled returns `"miniQuadW"`. Cached after first call.

### 2.2.7 is_quad() → bool

Returns whether the robot is legged (`robot_type == "miniQuad"`).

### 2.2.8 is_quad_wheel() → bool

Returns whether the robot is wheeled (`robot_type == "miniQuadW"`).

## 2.3 Configuration Interfaces

### 2.3.1 set_speed_ratio(ratio)

Sets speed ratio, auto-clamped to **[10, 100]**.

=== "Python"

    ```python
    set_speed_ratio(ratio: int)
    ```

=== "C++"

    ```cpp
    set_speed_ratio(int ratio)
    ```

### 2.3.2 set_obstacle_avoidance(enable)

Enables/disables obstacle avoidance. Accepts `bool` or `"on"/"off"` string.

When client toggles obstacle avoidance via RPC, server triggers voice prompt: `avoid_obstacle_on.wav` / `avoid_obstacle_off.wav`.

## 2.4 Motion Execution Interface

### 2.4.1 execute(\*motions, loop=False)

Executes motion sequence with real-time streaming progress output. Each parameter can be:

- `str` — Motion ID
- `(str, dict)` — Motion ID + parameter dict

Press **Ctrl+C** to cancel anytime.

## 2.5 State Switching Interface

### 2.5.1 set_target_state(state_name)

Switches state by name (case-insensitive). Invalid names throw `ValueError`.

**Valid States / Function List:**

| #   | Function                  | Description                    | Note                   |
| --- | ------------------------- | ------------------------------ | ---------------------- |
| 1   | `passive()`               | Passive mode (motor power off) |                        |
| 2   | `emergency()`             | Emergency stop                 | Alias for `passive()`  |
| 3   | `ready()`                 | Slow stand down (safe stop)    | :material-new-box: New |
| 4   | `stand_down()`            | Stand down                     |                        |
| 5   | `balance_stand()`         | Balance stand                  |                        |
| 6   | `walk()`                  | Switch to walk mode            |                        |
| 7   | `rl()`                    | Switch to RL mode              |                        |
| 8   | `flying_trot()`           | Switch to running mode         |                        |
| 9   | `change_mode()`           | Walk ⇄ Run smooth switch       | :material-new-box: New |
| 10  | `dance()`                 | Dance (alias: dance0)          |                        |
| 11  | `jump()`                  | Jump                           |                        |
| 12  | `wave_hand(duration=5.0)` | Wave hand (alias: wave)        |                        |
| 13  | `backflip()`              | Backflip                       |                        |
| 14  | `recovery()`              | Recovery/self-rescue           |                        |

**Wheeled Robot (miniQuadW) Valid States / Function List:**

| #   | Function        | Description                    | Note                            |
| --- | --------------- | ------------------------------ | ------------------------------- |
| 1   | `passive()`     | Passive mode (motor power off) | Shared                          |
| 2   | `emergency()`   | Emergency stop                 | Alias for `passive()`           |
| 3   | `ready()`       | Slow stand down (safe stop)    | Shared                          |
| 4   | `stand_down()`  | Stand down                     | Shared                          |
| 5   | `wheel_loco()`  | Wheel locomotion               | :material-new-box: Wheeled only |
| 6   | `drift()`       | Drift mode                     | :material-new-box: Wheeled only |
| 7   | `handstand()`   | Handstand                      | :material-new-box: Wheeled only |
| 8   | `change_mode()` | Switch leg configuration       | Shared                          |

!!! warning "Note"
All state switching methods have removed `set_` prefix. Use `robot.balance_stand()` instead of `robot.set_balance_stand()`.

### 2.5.2 change_mode()

Switches leg configuration (parallel ↔ X-shape). No parameters, toggles between two configurations.

=== "Python"

    ```python
    robot.change_mode()    # Switch leg configuration
    robot.change_mode()    # Call again to switch back
    ```

=== "C++"

    ```cpp
    client.change_mode();    // Switch leg configuration
    client.change_mode();    // Call again to switch back
    ```

## 2.6 Velocity Sequence Interface

### 2.6.1 velocity_sequence(vel_seq, gait, speed_ratio, stand_down_after)

Executes velocity sequence. When `speed_ratio` is explicitly provided, temporarily sets and restores after execution; when omitted, uses current base speed ratio.

| Parameter          | Type          | Default   | Description                                                          |
| ------------------ | ------------- | --------- | -------------------------------------------------------------------- |
| `vel_seq`          | string / list | —         | `"vx,vy,vyaw,dur;..."` or tuple list                                 |
| `gait`             | string        | `"walk"`  | Legged: `"walk"` / `"flying_trot"` / `"rl"`; Wheeled: `"wheel_loco"` |
| `speed_ratio`      | int           | `None/-1` | Optional [10, 100], uses current base value when omitted             |
| `stand_down_after` | bool          | `true`    | Whether to stand down after sequence                                 |

=== "Python"

    ```python
    steps = [
        (0.8, 0, 0, 2),   # forward 2s
        (0, 0, 0, 1),     # stop 1s
        (-0.8, 0, 0, 2),  # backward 2s
    ]
    robot.velocity_sequence(steps, gait="walk", speed_ratio=60)
    ```

=== "C++"

    ```cpp
    std::vector<robot::VelocityStep> steps = {
        {0.8f, 0, 0, 2},   // forward 2s
        {0, 0, 0, 1},      // stop 1s
        {-0.8f, 0, 0, 2},  // backward 2s
    };
    client.velocity_sequence(steps, "walk", 60);
    ```

## 2.7 Line Walk Interface

### 2.7.1 line_walk(direction, distance, speed_ratio)

When `speed_ratio` is explicitly provided, temporarily sets and restores after execution; when omitted, uses current base speed ratio.

!!! info "Wheeled Robot Support"
The wheeled robot supports line walk in both **WHEEL_LOCO** (`knee_mode=0`) and **DRIFT** (`knee_mode=1`) states. The server automatically selects the target state based on the current `knee_mode`.
Note: DRIFT mode does **not** support lateral movement (`move_left` / `move_right`), only forward and backward.

| Parameter     | Type         | Range             | Description                                    |
| ------------- | ------------ | ----------------- | ---------------------------------------------- |
| `direction`   | int / string | 0-3               | 0="forward", 1="backward", 2="left", 3="right" |
| `distance`    | float        | **[0, 3] m**      | Walking distance (meters)                      |
| `speed_ratio` | int / None   | None or [10, 100] | Optional speed ratio override                  |

### 2.7.2 Direction Shortcut Functions

| Function                  | Equivalent Call          | Description   |
| ------------------------- | ------------------------ | ------------- |
| `walk_forward(distance)`  | `line_walk(0, distance)` | Walk forward  |
| `walk_backward(distance)` | `line_walk(1, distance)` | Walk backward |
| `move_left(distance)`     | `line_walk(2, distance)` | Move left     |
| `move_right(distance)`    | `line_walk(3, distance)` | Move right    |

!!! warning "Breaking Change"
`walk_left` → `move_left`, `walk_right` → `move_right`. Distance limit changed from 10m to **3m**.

## 2.8 Rotation Control Interface

!!! info "Wheeled Robot Support"
Rotation interfaces are only available in the **WHEEL_LOCO** state on the wheeled robot (DRIFT mode does not support in-place rotation).
`rotate_walk` combines rotation + line walk, and is subject to the same limitation.

### 2.8.1 rotate(direction, angle)

| Parameter   | Type         | Range                 | Description        |
| ----------- | ------------ | --------------------- | ------------------ |
| `direction` | string / int | "left"/"right" or 0/1 | Rotation direction |
| `angle`     | float        | [0, 360]°             | Rotation angle     |

Shortcut functions: `rotate_left(angle)`, `rotate_right(angle)`

### 2.8.2 circle(direction, turns)

Rotates specified number of turns.

| Parameter   | Range          | Description        |
| ----------- | -------------- | ------------------ |
| `direction` | "left"/"right" | Rotation direction |
| `turns`     | **[1, 10]**    | Number of turns    |

### 2.8.3 rotate_walk(angle, distance)

Walks toward specified direction angle.

| Parameter  | Range            | Description                                            |
| ---------- | ---------------- | ------------------------------------------------------ |
| `angle`    | **[-180, 180]°** | Target direction angle (positive=right, negative=left) |
| `distance` | **[0, 3] m**     | Walking distance                                       |

## 2.9 Balance Actions Interface

!!! warning "Legged Robot Only"
Balance action interfaces (balance_pitch / balance_yaw / balance_roll / balance_height / balance_neutral / balance_sequence) and composite pose interfaces (dynamic_pose / static_pose) are only available on the legged robot (miniQuad) in BALANCE_STAND state. The wheeled robot does not support these interfaces.

!!! info "Modes"
`"dynamic"` — Sine sweep to target value → hold;
`"static"` — Ramp to target, hold, ramp back.

### 2.9.1 Single-Axis Control

| Function                                | value Range  | Description                              |
| --------------------------------------- | ------------ | ---------------------------------------- |
| `balance_pitch(value, duration, mode)`  | [-15, 15]°   | Pitch. >0 forward lean, <0 backward lean |
| `balance_yaw(value, duration, mode)`    | [-20, 20]°   | Yaw. >0 look right, <0 look left         |
| `balance_roll(value, duration, mode)`   | [-30, 30]°   | Roll. >0 left lean, <0 right lean        |
| `balance_height(value, duration, mode)` | [-0.12, 0] m | Height. <0 squat                         |
| `balance_neutral(duration)`             | —            | Return to neutral                        |

| Parameter  | Type   | Range                | Description                                                                              |
| ---------- | ------ | -------------------- | ---------------------------------------------------------------------------------------- |
| `value`    | float  | See table above      | Target offset (from initial pose to target pose), unit: degrees (rpy) or meters (height) |
| `duration` | float  | [0.5, 5] s           | Duration (seconds), default 2.0                                                          |
| `mode`     | string | "dynamic" / "static" | Motion mode, default "dynamic"                                                           |

### 2.9.2 Batch Execution

`balance_sequence(motions)` — Batch executes multiple balance actions in single RPC. Motions format: `(motion_id, value, duration, mode)`

=== "Python"

    ```python
    robot.balance_sequence([
        ("balance_pitch",  20.0, 2.0, "dynamic"),   # Forward lean 20°
        ("balance_pitch", -20.0, 2.0, "dynamic"),   # Backward lean 20°
        ("balance_neutral", 0.0, 0.5, "dynamic"),   # Return to neutral
    ])
    ```

=== "C++"

    ```cpp
    client.balance_sequence({
        {"balance_pitch",   20.0f, 2.0f, "dynamic"},
        {"balance_pitch",  -20.0f, 2.0f, "dynamic"},
        {"balance_neutral",  0.0f, 0.5f, "dynamic"},
    });
    ```

## 2.10 Composite Pose Interface

Includes dynamic_pose / static_pose. Simultaneously controls roll, pitch, yaw, height — all axes synchronized in single server motion.

| Parameter   | Range        | Description                                 |
| ----------- | ------------ | ------------------------------------------- |
| `duration`  | [1, 5] s     | Duration (seconds)                          |
| `roll_deg`  | [-30, 30]°   | Roll angle, 0 = no change                   |
| `pitch_deg` | [-15, 15]°   | Pitch angle, 0 = no change                  |
| `yaw_deg`   | [-20, 20]°   | Yaw angle, >0 right, <0 left, 0 = no change |
| `height_m`  | [-0.12, 0] m | Height increment, 0 = no change             |

!!! tip "Difference"
`dynamic_pose` — Sine sweep to target;
`static_pose` — Ramp to target, hold, ramp back.

=== "Python"

    ```python
    # Sine sweep: simultaneous multi-axis control
    robot.dynamic_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)

    # Hold pose: ramp to target for 5 seconds
    robot.static_pose(5.0, pitch_deg=15, height_m=-0.03)

    # Return to neutral
    robot.balance_neutral()
    ```

=== "C++"

    ```cpp
    // Sine sweep: simultaneous multi-axis control
    client.dynamic_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);

    // Hold pose: ramp to target for 5 seconds
    client.static_pose(5.0f, 15.0f, 0.0f, 0.0f, -0.03f);

    // Return to neutral
    client.balance_neutral();
    ```

## 2.11 Special Motions Interface

| Function                  | Description                         |
| ------------------------- | ----------------------------------- |
| `dance()`                 | Dance (internally calls `dance0`)   |
| `jump()`                  | Jump                                |
| `wave_hand(duration=5.0)` | Wave hand (internally calls `wave`) |
| `backflip()`              | Backflip                            |

## 2.12 Safety Handler Interface

### enable_safety_ready()

Registers **Ctrl+C** handler. When **Ctrl+C** is pressed, cancels current motion and switches to `ready` state before process exit.

=== "Python"

    ```python
    robot.enable_safety_ready()
    ```

=== "C++"

    ```cpp
    robot::enable_safety_ready(client)
    ```

!!! warning "Note"
Handler only triggers on Ctrl+C (SIGINT). Normal program exit **will not** call `ready()`.

## 3. Example Programs

All examples provide both Python and C++ versions, located in `high_level/python/examples/` and `high_level/cpp/` directories.

### E1: Get Available Motions

Lists all server-available motions and their parameters.

=== "Python"

    ```python
    from dobot_quad import RobotClient

    robot = RobotClient("192.168.5.2:50051")
    res = robot.get_motions()

    for m in res.motions:
        print(f"  [{m.motion_id}]")
        for p in m.parameters:
            print(f"      {p.key}: {p.float_value or p.int_value or p.string_value}")
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"

    robot::Client client("192.168.5.2:50051");
    auto res = client.get_motions();

    for (const auto& m : res.motions())
        std::cout << "  [" << m.motion_id() << "]" << std::endl;
    ```

### E2: Get Current State

=== "Python"

    ```python
    robot = RobotClient("192.168.5.2:50051")
    state = robot.get_current_state_name()
    print(f"Current state: {state}")
    ```

=== "C++"

    ```cpp
    robot::Client client("192.168.5.2:50051");
    auto state = client.get_current_state_name();
    std::cout << "Current state: " << state << std::endl;
    ```

### E3: State Switching

Supports command-line arguments or interactive selection. The program automatically displays the appropriate state list based on robot type.

=== "Python (Legged)"

    ```python
    robot.set_target_state("balance_stand")
    robot.walk()
    robot.flying_trot()
    robot.change_mode()
    ```

=== "Python (Wheeled)"

    ```python
    robot.wheel_loco()
    robot.drift()
    robot.handstand()
    robot.change_mode()
    ```

=== "C++ (Legged)"

    ```cpp
    client.balance_stand();
    client.walk();
    client.flying_trot();
    client.change_mode();
    ```

=== "C++ (Wheeled)"

    ```cpp
    client.wheel_loco();
    client.drift();
    client.handstand();
    client.change_mode();
    ```

### E4: Velocity Sequence

=== "Python (Legged)"

    ```python
    steps = [
        (0.8, 0, 0, 2),   # forward 2s
        (0, 0, 0, 1),     # stop 1s
        (-0.8, 0, 0, 2),  # backward 2s
        (0, 0, 0, 1),     # stop 1s
    ]
    robot.velocity_sequence(steps, gait="walk", speed_ratio=60)
    # Also supports flying_trot:
    robot.velocity_sequence(steps, gait="flying_trot")
    ```

=== "Python (Wheeled)"

    ```python
    steps = [
        (0.8, 0, 0, 2),    # forward 2s
        (0, 0.3, 0, 2),    # strafe left 2s
        (0, 0, 0.4, 2),    # turn left 2s
        (0, 0, 0, 1),      # stop 1s
    ]
    robot.velocity_sequence(steps, gait="wheel_loco", speed_ratio=60)
    ```

=== "C++ (Legged)"

    ```cpp
    std::vector<robot::VelocityStep> steps = {
        {0.8f, 0, 0, 2},   // forward 2s
        {0, 0, 0, 1},      // stop 1s
        {-0.8f, 0, 0, 2},  // backward 2s
        {0, 0, 0, 1},      // stop 1s
    };
    client.velocity_sequence(steps, "walk", 60);
    ```

=== "C++ (Wheeled)"

    ```cpp
    std::vector<robot::VelocityStep> steps = {
        {0.8f, 0, 0, 2},     // forward 2s
        {0, 0.3f, 0, 2},     // strafe left 2s
        {0, 0, 0.4f, 2},     // turn left 2s
        {0, 0, 0, 1},        // stop 1s
    };
    client.velocity_sequence(steps, "wheel_loco", 60);
    ```

### E5: Robot Telemetry

=== "Python"

    ```python
    res = robot.get_state()
    print(f"Current state: {res.current_state}")
    print(f"Speed ratio:   {res.current_speed_ratio}")

    s = res.robot_state
    print(f"Body pos: {list(s.pos_body)}")
    print(f"Leg torques: {list(s.jtau_leg)}")
    ```

=== "C++"

    ```cpp
    auto res = client.get_state();
    std::cout << "Current state: " << res.current_state() << std::endl;
    const auto& s = res.robot_state();
    // s.pos_body(), s.jtau_leg(), etc.
    ```

### E6: Balance Actions

!!! warning "Legged Robot Only"
Balance actions are only available on the legged robot (miniQuad). The wheeled robot will display an unsupported message and exit.

=== "Python"

    ```python
    # Single-axis functions (dynamic)
    robot.balance_pitch(15.0, 2.0, "dynamic")
    robot.balance_yaw(20.0, 2.0, "dynamic")
    robot.balance_roll(-15.0, 2.0, "dynamic")
    robot.balance_height(-0.05, 2.0, "dynamic")

    # Single-axis functions (static)
    robot.balance_pitch(-15.0, 2.5, "static")
    robot.balance_yaw(-20.0, 2.5, "static")
    robot.balance_roll(15.0, 2.5, "static")
    robot.balance_height(-0.08, 2.5, "static")

    # balance_sequence
    robot.balance_sequence([
        ("balance_pitch", 15.0, 2.0, "dynamic"),
        ("balance_yaw", 20.0, 2.0, "dynamic"),
        ("balance_roll", -15.0, 2.0, "dynamic"),
        ("balance_height", -0.05, 2.0, "dynamic"),
        ("balance_neutral", 0.0, 0.5, "dynamic"),
    ])

    # Two composite poses
    robot.dynamic_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
    robot.static_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
    robot.balance_neutral()
    ```

=== "C++"

    ```cpp
    // Single-axis functions (dynamic)
    client.balance_pitch(15.0f, 2.0f, "dynamic");
    client.balance_yaw(20.0f, 2.0f, "dynamic");
    client.balance_roll(-15.0f, 2.0f, "dynamic");
    client.balance_height(-0.05f, 2.0f, "dynamic");

    // Single-axis functions (static)
    client.balance_pitch(-15.0f, 2.5f, "static");
    client.balance_yaw(-20.0f, 2.5f, "static");
    client.balance_roll(15.0f, 2.5f, "static");
    client.balance_height(-0.08f, 2.5f, "static");

    // balance_sequence
    client.balance_sequence({
        {"balance_pitch", 15.0f, 2.0f, "dynamic"},
        {"balance_yaw", 20.0f, 2.0f, "dynamic"},
        {"balance_roll", -15.0f, 2.0f, "dynamic"},
        {"balance_height", -0.05f, 2.0f, "dynamic"},
        {"balance_neutral", 0.0f, 0.5f, "dynamic"},
    });

    // Two composite poses
    client.dynamic_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.static_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.balance_neutral();
    ```

### E7: Line Walk

=== "Python"

    ```python
    robot.walk_forward(2.0)       # Forward 2m (max 3m)
    robot.walk_backward(1.5)      # Backward 1.5m
    robot.move_left(1.0)          # Left 1m (formerly walk_left)
    robot.move_right(1.0)         # Right 1m (formerly walk_right)

    # Using generic interface:
    robot.line_walk("forward", 2.0)
    robot.line_walk(2, 1.0)       # direction=2 (left)
    ```

=== "C++"

    ```cpp
    client.walk_forward(2.0);       // Forward 2m (max 3m)
    client.walk_backward(1.5);      // Backward 1.5m
    client.move_left(1.0);          // Left 1m (formerly walk_left)
    client.move_right(1.0);         // Right 1m (formerly walk_right)

    // Using generic interface:
    client.line_walk(0, 2.0);       // direction=0 (forward)
    ```

### E8: Rotation

=== "Python"

    ```python
    robot.rotate("left", 90)         # Rotate left 90°
    robot.rotate_right(45)           # Rotate right 45°
    robot.circle("left", turns=3)    # Rotate left 3 turns (max 10)
    robot.rotate_walk(-45, 2.0)      # Walk 2m toward -45° direction (left)
    ```

=== "C++"

    ```cpp
    client.rotate("left", 90);       // Rotate left 90°
    client.rotate_right(45);         // Rotate right 45°
    client.circle("left", 3);        // Rotate left 3 turns (max 10)
    client.rotate_walk(-45, 2.0);    // Walk 2m toward -45° direction (left)
    ```

### E9: Combo Sequence

Arduino-style sequential blocking calls — each function blocks until motion completes. The program executes different flows based on robot type.

=== "Python (Legged)"

    ```python
    # Full flow: state switch + change_mode + motion + balance
    robot.passive(); robot.ready(); robot.balance_stand()
    robot.walk(); robot.change_mode(); robot.change_mode()

    robot.walk_forward(1.0); robot.walk_backward(1.0)
    robot.move_left(1.0); robot.move_right(1.0)

    robot.rotate_left(90); robot.rotate_left(180)
    robot.rotate_right(90); robot.rotate_right(180)
    robot.circle("left", 1)

    robot.balance_pitch(15.0, 2.0, "dynamic"); robot.balance_pitch(-15.0, 2.5, "static")
    robot.balance_yaw(20.0, 2.0, "dynamic");   robot.balance_yaw(-20.0, 2.5, "static")
    robot.balance_roll(15.0, 2.0, "dynamic");  robot.balance_roll(-15.0, 2.5, "static")
    robot.balance_height(-0.05, 2.0, "dynamic"); robot.balance_height(-0.08, 2.5, "static")

    robot.dynamic_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
    robot.static_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
    robot.balance_neutral()

    robot.wave_hand(); robot.dance(); robot.recovery()
    robot.stand_down()
    ```

=== "Python (Wheeled)"

    ```python
    # Wheeled full flow: state switch + motion
    robot.passive(); robot.ready()
    robot.wheel_loco()
    robot.change_mode(); robot.change_mode()

    robot.walk_forward(1.0); robot.walk_backward(1.0)
    robot.move_left(1.0); robot.move_right(1.0)

    robot.rotate_left(90); robot.rotate_right(90)
    robot.circle("left", 1)

    # Wheeled-specific state switching
    robot.drift()
    robot.wheel_loco()
    robot.handstand()

    robot.stand_down()
    ```

=== "C++ (Legged)"

    ```cpp
    // Full flow: state switch + change_mode + motion + balance
    client.passive(); client.ready(); client.balance_stand();
    client.walk(); client.change_mode(); client.change_mode();

    client.walk_forward(1.0f); client.walk_backward(1.0f);
    client.move_left(1.0f); client.move_right(1.0f);

    client.rotate_left(90.0f); client.rotate_left(180.0f);
    client.rotate_right(90.0f); client.rotate_right(180.0f);
    client.circle("left", 1);

    client.balance_pitch(15.0f, 2.0f, "dynamic"); client.balance_pitch(-15.0f, 2.5f, "static");
    client.balance_yaw(20.0f, 2.0f, "dynamic");   client.balance_yaw(-20.0f, 2.5f, "static");
    client.balance_roll(15.0f, 2.0f, "dynamic");  client.balance_roll(-15.0f, 2.5f, "static");
    client.balance_height(-0.05f, 2.0f, "dynamic"); client.balance_height(-0.08f, 2.5f, "static");

    client.dynamic_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.static_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.balance_neutral();

    client.wave_hand(); client.dance(); client.recovery();
    client.stand_down();
    ```

=== "C++ (Wheeled)"

    ```cpp
    // Wheeled full flow: state switch + motion
    client.passive(); client.ready();
    client.wheel_loco();
    client.change_mode(); client.change_mode();

    client.walk_forward(1.0f); client.walk_backward(1.0f);
    client.move_left(1.0f); client.move_right(1.0f);

    client.rotate_left(90.0f); client.rotate_right(90.0f);
    client.circle("left", 1);

    // Wheeled-specific state switching
    client.drift();
    client.wheel_loco();
    client.handstand();

    client.stand_down();
    ```

### E10: Configuration Demo

=== "Python"

    ```python
    # Query current speed ratio (returns local tracked value)
    sr = robot.get_speed_ratio()
    print(f"Speed ratio: {sr}")

    # Set base speed ratio
    robot.set_speed_ratio(30)

    # Without speed_ratio, uses current base value (30)
    robot.walk_forward(2.0)

    # Explicit speed_ratio=100, temporarily override, restores to 30 after execution
    robot.walk_forward(2.0, speed_ratio=100)

    # Obstacle avoidance switch
    robot.set_obstacle_avoidance(True)    # or "on"
    robot.set_obstacle_avoidance(False)   # or "off"
    ```

=== "C++"

    ```cpp
    // Query current speed ratio (returns local tracked value)
    int sr = client.get_speed_ratio();
    std::cout << "Speed ratio: " << sr << std::endl;

    // Set base speed ratio
    client.set_speed_ratio(30);

    // Without speed_ratio, uses current base value (30)
    client.walk_forward(2.0);

    // Explicit speed_ratio=100, temporarily override, restores to 30 after execution
    client.walk_forward(2.0, 100);

    // Obstacle avoidance switch
    client.set_obstacle_avoidance(true);
    client.set_obstacle_avoidance("off");
    ```

## Parameter Quick Reference

| Parameter                           | Range                                                | Functions                                                                     |
| ----------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------- |
| speed_ratio                         | [10, 100]                                            | set_speed_ratio; optional override: line_walk, velocity_sequence, rotate_walk |
| distance                            | **[0, 3] m**                                         | walk_forward, walk_backward, move_left, move_right, rotate_walk               |
| angle (rotate)                      | [0, 360]°                                            | rotate, rotate_left, rotate_right                                             |
| angle (rotate_walk)                 | **[-180, 180]°**                                     | rotate_walk                                                                   |
| turns                               | **[1, 10]**                                          | circle                                                                        |
| balance value (rpy)                 | roll: [-30, 30]°, pitch: [-15, 15]°, yaw: [-20, 20]° | balance_pitch/yaw/roll, balance_sequence                                      |
| balance value (height)              | [-0.12, 0] m                                         | balance_height, balance_sequence                                              |
| balance duration                    | [0.5, 5] s                                           | All balance\_\* functions                                                     |
| dynamic_pose / static_pose angles   | roll: [-30, 30]°, pitch: [-15, 15]°, yaw: [-20, 20]° | dynamic_pose, static_pose                                                     |
| dynamic_pose / static_pose height   | [-0.12, 0] m                                         | dynamic_pose, static_pose                                                     |
| dynamic_pose / static_pose duration | [1, 5] s                                             | dynamic_pose, static_pose                                                     |
| obstacle_avoidance                  | bool / "on" / "off"                                  | set_obstacle_avoidance                                                        |
