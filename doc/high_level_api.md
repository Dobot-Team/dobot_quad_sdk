# High-Level Control API Documentation

[English](high_level_api.md) · [简体中文](high_level_api.zh-CN.md)

This document provides detailed information about the Dobot Quad SDK's high-level control layer (gRPC) API, including functionality, principles, and usage of each example program.

---

## Table of Contents

- [Overview](#overview)
- [State Machine Introduction](#state-machine-introduction)
- [Speed Ratio & Velocity System](#speed-ratio--velocity-system)
- [Obstacle Avoidance](#obstacle-avoidance)
- [Kill Robot Tool](#kill-robot-tool)
- [Example Programs](#example-programs)
  - [E1: Get Available Motions](#e1-get-available-motions)
  - [E2: Get Current State](#e2-get-current-state)
  - [E3: Auto State Switch](#e3-auto-state-switch)
  - [E4: Velocity Sequence Control](#e4-velocity-sequence-control)
  - [E5: Robot State Query](#e5-robot-state-query)
  - [E6: Balance Motion Control](#e6-balance-motion-control)
  - [E7: Line Walk](#e7-line-walk)
  - [E8: Rotation](#e8-rotation)
  - [E9: Combo Sequence](#e9-combo-sequence)
  - [E10: Speed Ratio & Obstacle Avoidance](#e10-speed-ratio--obstacle-avoidance)
- [RPC Reference](#rpc-reference)
- [FAQ](#faq)

---

## Overview

The high-level control layer is implemented using the gRPC protocol and provides the following core features:

- **State Machine Management**: Control transitions between different motion states
- **Motion Planning**: Execute predefined motion sequences with real-time progress streaming
- **State Query**: Real-time retrieval of robot status data (joints, body, FSM state)
- **Parameter Configuration**: Dynamic adjustment of speed ratio and obstacle avoidance
- **Velocity Control**: Direct velocity commands in physical units (m/s, rad/s)

### Connection

Default gRPC service address is `192.168.5.2:50051` (robot host port).

```python
import grpc
from dobot_quad.proto import grpc_service_pb2_grpc

channel = grpc.insecure_channel("192.168.5.2:50051")
stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
```

### Client Libraries

Two ready-to-use client libraries are provided:

| Language | File | Class |
|----------|------|-------|
| Python | `high_level/python/dobot_quad/robot_client.py` | `RobotClient` |
| C++ | `high_level/cpp/robot_client.h` | `robot::Client` |

Both wrap all RPC calls with progress display, error handling, and Ctrl+C cancellation support.

For Python, running `pip install .` inside `high_level/python` installs the `dobot_quad` package and auto-generates gRPC bindings. Examples live in the `examples/` subdirectory.

---

## State Machine Introduction

The robot uses a Finite State Machine (FSM) to manage motion states. Main states include:

| State Name | Description |
|------------|-------------|
| `PASSIVE` | Passive mode, motors disabled |
| `STAND_DOWN` | Lying down state |
| `STAND_UP` | Standing state |
| `BALANCE_STAND` | Balance standing, supports posture adjustment |
| `WALK` | Walking mode |
| `FLYING_TROT` | Flying trot (running gait) |
| `RL` | Reinforcement learning control mode |
| `WAVE` | Waving motion |
| `DANCE0` | Dance motion |
| `JUMP` | Jump motion |
| `BACKFLIP` | Backflip motion |

### State Transition Rules

The state machine has strict transition rules; you cannot jump directly from any state to any other state. For example:

- `PASSIVE` → `STAND_DOWN` → `STAND_UP` → `BALANCE_STAND`
- `BALANCE_STAND` → `WALK` / `FLYING_TROT` / `RL`

Use the `path_to_state` motion to automatically find transition paths.

---

## Speed Ratio & Velocity System

### Speed Ratio

The **speed ratio** controls the overall speed scaling of the robot. It can be set via the `SetSpeedRatio` RPC.

| Property | Value |
|----------|-------|
| Range | 10 – 100 |
| Step | 10 |
| Default | 50 |

When you set speed ratio to 0, the RPC returns the current value without modifying it (query mode).

The speed ratio affects the **real speed scale** used in the velocity pipeline:

```
realSpeedScale = (1 - k_lower) × speedRatio / 100 + k_lower
```

where `k_lower` is the minimum speed fraction (varies per gait, see table below).

### Gait Velocity Bounds

Each gait mode has its own velocity limits. The maximum achievable velocity depends on both the gait bounds and the current speed ratio:

```
v_max = bound × realSpeedScale
```

| Gait | Direction | Bound | k_lower | Max @ ratio=50 | Max @ ratio=100 |
|------|-----------|-------|---------|-----------------|-----------------|
| **WALK** | vx (forward) | 1.2 m/s | 0.4 | 0.84 m/s | 1.20 m/s |
| | vx (backward) | 0.8 m/s | 0.4 | 0.56 m/s | 0.80 m/s |
| | vy (strafe) | 0.45 m/s | 0.4 | 0.315 m/s | 0.45 m/s |
| | vyaw (turn) | 1.8 rad/s | 0.4 | 1.26 rad/s | 1.80 rad/s |
| **FLYING_TROT** | vx (forward) | 2.0 m/s | 0.2 | 1.20 m/s | 2.00 m/s |
| | vx (backward) | 1.0 m/s | 0.2 | 0.60 m/s | 1.00 m/s |
| | vy (strafe) | 0.55 m/s | 0.2 | 0.33 m/s | 0.55 m/s |
| | vyaw (turn) | 1.4 rad/s | 0.2 | 0.84 rad/s | 1.40 rad/s |
| **RL** | vx (forward) | 0.8 m/s | 0.3 | 0.52 m/s | 0.80 m/s |
| | vx (backward) | 0.6 m/s | 0.3 | 0.39 m/s | 0.60 m/s |
| | vy (strafe) | 0.45 m/s | 0.3 | 0.293 m/s | 0.45 m/s |
| | vyaw (turn) | 1.2 rad/s | 0.3 | 0.78 rad/s | 1.20 rad/s |

> **Note**: When a requested velocity exceeds the achievable maximum, it is internally clamped to the bound. For best results, keep your velocity values within the "Max @ ratio=N" limits.

### Setting Speed Ratio

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# Query current speed ratio (returns locally tracked value)
current = robot.get_speed_ratio()
print(f"Current speed ratio: {current}")

# Set speed ratio to 80
robot.set_speed_ratio(80)
```

```cpp
robot::Client client("192.168.5.2:50051");

// Query current speed ratio (returns locally tracked value)
int current = client.get_speed_ratio();
std::cout << "Current: " << current << std::endl;

// Set speed ratio to 80
client.set_speed_ratio(80);
```

> **Note:** `get_speed_ratio()` and `get_obstacle_avoidance()` return locally tracked values updated from `set_*()` RPC responses, rather than querying the server each time. This avoids stale reads from the eventually-consistent `GetRobotState` RPC.

---

## Obstacle Avoidance

The robot has a built-in obstacle avoidance system that uses sensors to detect obstacles and modifies velocity commands to prevent collisions. When enabled, the obstacle avoidance system may **override the forward velocity (vx)** to zero if an obstacle is detected ahead.

> **Important**: Obstacle avoidance primarily affects the forward direction (vx). Lateral (vy) and rotational (vyaw) velocities are not modified by the obstacle avoidance system.

### Enable/Disable Obstacle Avoidance

Use the `SetObstacleAvoidance` RPC to toggle the obstacle avoidance system:

```python
robot = RobotClient("192.168.5.2:50051")

# Disable obstacle avoidance
robot.set_obstacle_avoidance(False)

# Enable obstacle avoidance
robot.set_obstacle_avoidance(True)
```

```cpp
robot::Client client("192.168.5.2:50051");

// Disable obstacle avoidance
client.set_obstacle_avoidance(false);

// Enable obstacle avoidance
client.set_obstacle_avoidance(true);
```

> **Tip**: If you notice the robot not moving forward while vy/vyaw work correctly, it is likely because obstacle avoidance is blocking vx. Try disabling it to test.

---

## Kill Robot Tool

**Files**: `high_level/python/examples/kill_robot.py` / `high_level/cpp/kill_robot.cpp`

### Description

`kill_robot` is a utility tool for safely shutting down the robot's main control program. Before using certain low-level control features (such as direct motor control, LED control), you must use this tool to stop the main control program to avoid control conflicts and safety hazards.

### How It Works

The tool executes the `kill_robot` motion command via gRPC interface. The server will safely shut down following these steps:

1. **Switch to PASSIVE State**: Switch robot to passive mode, disabling all motors
2. **Wait 5 Seconds**: Ensure the robot has safely stopped to avoid falls from sudden program exit
3. **Terminate Controller Processes**: Kill all main control program processes

### Usage

#### Python Version

```bash
cd high_level/python
python3 examples/kill_robot.py [server_address:port]

# Example
python3 examples/kill_robot.py 192.168.5.2:50051
```

#### C++ Version

```bash
cd high_level/cpp/build
./kill_robot [server_address:port]

# Example
./kill_robot 192.168.5.2:50051
```

Default server address is `192.168.5.2:50051`.

### Safety Confirmation

The tool will prompt for confirmation:

```
Are you sure? (y/N):
```

Only entering `y` will proceed with execution to prevent accidental operation.

### Error Handling

Since the `kill_robot` command shuts down the server process, the client may receive a connection error (`StatusCode.UNAVAILABLE` or `Socket closed`). This actually indicates the command was successfully executed, and the program will treat this as success and display:

```
Kill robot command executed successfully (server shut down as expected).
```

### Important Notes

- **When to Use**: Must execute before using low-level motor control (low_level E9) or LED control (low_level E3)
- **Safety Reminder**: Before execution, ensure the robot is in a safe position (flat ground, away from obstacles) to avoid falls from sudden motor disable

---

## Example Programs

### E1: Get Available Motions

**Files**: `high_level/python/examples/e1_get_available_motions.py` / `high_level/cpp/e1_get_available_motions.cpp`

#### Description

Query all motions supported by the robot and their parameters. This is the first step to understanding robot capabilities, providing:

- Motion ID list
- Description for each motion
- Supported parameters and default values for each motion

#### Principle

Through the `GetAvailableMotions` RPC call, the server returns information about all motions registered in the `MotionLibrary`.

#### Running

```bash
# Python
cd high_level/python
python3 examples/e1_get_available_motions.py [server_address]

# C++
cd high_level/cpp/build
./e1_get_available_motions [server_address]
```

#### Sample Output

```
Connected to server: 192.168.5.2:50051
Example 1: Get Available Motions
Successfully retrieved motion list
Found 15 motions:

  [passive]
    Description: Trigger FSM to PASSIVE once

  [stand_up]
    Description: Trigger FSM to STAND_UP once

  [walk_velocity_seq]
    Description: Walk with velocity sequence control
    Parameters (default values):
      - velocity_sequence: "" (string)

  [balance_pitch]
    Description: Control robot pitch angle in balance stand
    Parameters (default values):
      - value: 0.0 (float)
      - duration: 2.0 (float)
      - mode: "dynamic" (string)

  ......
```

#### Motion Parameter Reference

| Motion Type | Motion ID | Parameters | Description |
|-------------|-----------|------------|-------------|
| State switch | `passive`, `stand_down`, `stand_up`, `balance_stand`, etc. | None | Single state transition |
| Auto pathfinding | `path_to_state` | `target_state` | Automatically navigate to target state |
| Velocity sequence | `walk_velocity_seq`, `flying_trot_velocity_seq` | `velocity_sequence` | Velocity control in m/s and rad/s (see E4) |
| Balance motions | `balance_pitch`, `balance_yaw`, `balance_roll`, `balance_height`, `balance_neutral` | `value`, `duration`, `mode` | Posture control in BALANCE_STAND (see E6) |
| Line walk | `line_walk` | `direction`, `distance` | Walk straight for a given distance (see E7) |
| Rotation | `rotation` | `direction`, `angle` | Rotate in place by a given angle (see E8) |
| Special | `kill_robot` | None | Safely shut down the controller |

---

### E2: Get Current State

**Files**: `high_level/python/examples/e2_get_current_state.py` / `high_level/cpp/e2_get_current_state.cpp`

#### Description

Query the robot's current FSM state and basic telemetry data. Useful for checking the robot's current mode before issuing commands.

#### Principle

Through the `GetRobotState` RPC call, returns the current FSM state name along with sensor data.

#### Running

```bash
# Python
cd high_level/python
python3 examples/e2_get_current_state.py [server_address]

# C++
cd high_level/cpp/build
./e2_get_current_state [server_address]
```

#### Sample Output

```
Connected to server: 192.168.5.2:50051

Current state: STAND_DOWN
```

---

### E3: Auto State Switch

**Files**: `high_level/python/examples/e3_auto_state_switch.py` / `high_level/cpp/e3_auto_state_switch.cpp`

#### Description

Automatically find path to target state. Regardless of the robot's current state, the system will calculate the shortest path and execute state transitions.

#### Principle

Uses the `path_to_state` motion, which internally calls the `StateRoute` component for path planning:

1. Get current state
2. Calculate shortest path to target state
3. Execute state transitions along the path
4. Wait for each state to stabilize before proceeding

#### Sample Code

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# Navigate to BALANCE_STAND from any state
robot.execute("balance_stand")

# Navigate to WALK
robot.execute(("path_to_state", {"target_state": "WALK"}))
```

#### Supported Target States

```python
state_list = [
    "PASSIVE",
    "STAND_DOWN",
    "STAND_UP",
    "BALANCE_STAND",
    "WALK",
    "RL",
    "FLYING_TROT",
    "WAVE",
    "DANCE0",
    "BACK_FLIP",
    "JUMP",
]
```

#### Running

```bash
# Python (interactive menu)
cd high_level/python
python3 examples/e3_auto_state_switch.py [server_address]

# C++
cd high_level/cpp/build
./e3_auto_state_switch [server_address]
```

The program provides an interactive menu to select the target state.

---

### E4: Velocity Sequence Control

**Files**: `high_level/python/examples/e4_velocity_sequence.py` / `high_level/cpp/e4_velocity_sequence.cpp`

#### Description

Control the robot's motion trajectory through velocity sequences in `WALK` or `FLYING_TROT` state. Velocities are specified in **physical units** (m/s and rad/s) and internally converted to controller commands using the velocity bounds and current speed ratio.

#### Motion IDs

| Motion ID | Target Gait |
|-----------|-------------|
| `walk_velocity_seq` | WALK |
| `flying_trot_velocity_seq` | FLYING_TROT |

Each motion automatically switches to the required gait state before executing the velocity sequence.

#### Velocity Sequence Format

```
"vx,vy,vyaw,duration;vx,vy,vyaw,duration;..."
```

| Parameter | Unit | Description |
|-----------|------|-------------|
| `vx` | m/s | X-direction linear velocity (forward/backward) |
| `vy` | m/s | Y-direction linear velocity (left/right strafe) |
| `vyaw` | rad/s | Angular velocity around Z-axis (left/right turn) |
| `duration` | seconds | Duration to maintain this velocity command |

#### Velocity Direction Reference

| Direction | Condition | Description |
|-----------|-----------|-------------|
| Forward | vx > 0 | Move forward |
| Backward | vx < 0 | Move backward |
| Strafe left | vy > 0 | Move to the left |
| Strafe right | vy < 0 | Move to the right |
| Turn left (CCW) | vyaw > 0 | Counter-clockwise rotation |
| Turn right (CW) | vyaw < 0 | Clockwise rotation |

#### Recommended Velocity Ranges

See the Gait Velocity Bounds section for detailed maximum velocities per gait and speed ratio. Common safe values at the default speed ratio (50):

| Gait | vx | vy | vyaw |
|------|----|----|------|
| WALK | +/-0.5 m/s | +/-0.2 m/s | +/-0.8 rad/s |
| FLYING_TROT | +/-0.8 m/s | +/-0.3 m/s | +/-0.6 rad/s |

#### Sample Code

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# Walk demo: forward, backward, strafe, turn
robot.execute(
    (
        "walk_velocity_seq",
        {
            "velocity_sequence":
            "0.5,0.0,0.0,2.0;"   # forward  0.5 m/s for 2s
            "0.0,0.0,0.0,1.0;"   # stop for 1s
            "-0.4,0.0,0.0,2.0;"  # backward 0.4 m/s for 2s
            "0.0,0.0,0.0,1.0;"   # stop
            "0.0,0.2,0.0,2.0;"   # strafe left  0.2 m/s
            "0.0,0.0,0.0,1.0;"   # stop
            "0.0,-0.2,0.0,2.0;"  # strafe right 0.2 m/s
            "0.0,0.0,0.0,1.0;"   # stop
            "0.0,0.0,0.5,2.0;"   # turn left  0.5 rad/s
            "0.0,0.0,0.0,1.0;"   # stop
            "0.0,0.0,-0.5,2.0;"  # turn right 0.5 rad/s
            "0.0,0.0,0.0,1.0;"   # stop
        },
    ),
    "stand_down",
)
```

```python
# Flying trot demo: faster speeds
robot.execute(
    (
        "flying_trot_velocity_seq",
        {
            "velocity_sequence":
            "0.8,0.0,0.0,2.0;"  # sprint forward 0.8 m/s
            "0.0,0.0,0.0,1.0;"  # stop
            "0.0,0.0,0.6,2.0;"  # turn left 0.6 rad/s
            "0.0,0.0,0.0,1.0;"  # stop
        },
    ),
    "stand_down",
)
```

#### Running

```bash
# Python (1=walk demo, 2=flying trot demo)
cd high_level/python
python3 examples/e4_velocity_sequence.py [server_address] [1|2]

# C++
cd high_level/cpp/build
./e4_velocity_sequence [server_address] [1|2]
```

#### Progress Streaming

During execution, the server streams real-time progress updates. For velocity sequences, messages include the current segment index and velocity values:

```
Running... (Ctrl+C to stop)
  [1/2] walk_velocity_seq | state: WALK (VelSeg 1/12: vx=0.50 vy=0.00 vyaw=0.00)
  [1/2] walk_velocity_seq | state: WALK (VelSeg 2/12: vx=0.00 vy=0.00 vyaw=0.00)
  ...
  [1/2] walk_velocity_seq | state: WALK (VelSeg 12/12: vx=0.00 vy=0.00 vyaw=0.00)
Done.
```

---

### E5: Robot State Query

**Files**: `high_level/python/examples/e5_robot_state.py` / `high_level/cpp/e5_robot_state.cpp`

#### Description

Real-time retrieval of robot status data, including:

- Joint positions, velocities, torques (actual and desired)
- Body position, velocity, acceleration, orientation, angular velocity
- Contact force information
- Battery voltage
- Current FSM state name

#### Principle

Retrieves `RobotState` message through the `GetRobotState` RPC call.

#### Output Data Reference

| Category | Field | Unit | Description |
|----------|-------|------|-------------|
| Leg Joints (Actual) | `jpos_leg` | rad | Joint positions (12 joints) |
| | `jvel_leg` | rad/s | Joint velocities |
| | `jtau_leg` | Nm | Joint torques |
| Leg Joints (Desired) | `jpos_leg_des` | rad | Desired joint positions |
| | `jvel_leg_des` | rad/s | Desired joint velocities |
| | `jtau_leg_des` | Nm | Desired joint torques |
| Body State | `pos_body` *(not yet available)* | m | Body position [x, y, z] |
| | `vel_body` *(not yet available)* | m/s | Body velocity [vx, vy, vz] |
| | `acc_body` | m/s2 | Body acceleration [ax, ay, az] |
| | `ori_body` | rad | Body orientation [roll, pitch, yaw] |
| | `omega_body` | rad/s | Body angular velocity |
| Contact Forces (Raw) | `grf_left` *(not yet available)* | N | Left foot forces [fx, fy, fz] |
| | `grf_right` *(not yet available)* | N | Right foot forces [fx, fy, fz] |
| Contact Force Statistics | `temp[0]` | N | Total contact force of left foot |
| | `temp[1]` | N | Total contact force of right foot |
| | `temp[2]` | N | Total contact force of both feet |
| | `temp[3]` | N | Total ground reaction force in X direction |
| Power Status | `temp[8]` | V | Battery 1 voltage |
| | `temp[9]` | V | Battery 2 voltage |
| FSM State | `current_state` | -- | Current FSM state name (e.g. "WALK") |

> **Note**: `temp[4]` to `temp[7]` are reserved fields and not currently used.

#### Running

```bash
# Python
cd high_level/python
python3 examples/e5_robot_state.py [server_address]

# C++
cd high_level/cpp/build
./e5_robot_state [server_address]
```

---

### E6: Balance Motion Control

**Files**: `high_level/python/examples/e6_balance_motions.py` / `high_level/cpp/e6_balance_motions.cpp`

#### Description

Control robot posture in `BALANCE_STAND` state, executing four basic motions:

- **Pitch**: Nodding motion (look up / look down)
- **Yaw**: Head shaking motion (turn left / turn right)
- **Roll**: Side-to-side swaying (lean left / lean right)
- **Height**: Squat / stand tall

#### Motion Parameters

| Parameter | Description | Range |
|-----------|-------------|-------|
| `value` | Target offset value (degrees for rpy, meters for height) | roll: `[-30, 30]`, pitch: `[-15, 15]`, yaw: `[-20, 20]`, height: `[-0.12, 0]` |
| `duration` | Motion duration (seconds) | single-axis/balance-sequence: `[0.5, 5]`; composite pose (`dynamic_pose`/`static_pose`): `[1, 5]` |
| `mode` | Motion mode | `"dynamic"` / `"static"` |

#### Sample Code

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# Single-axis APIs
robot.balance_pitch(15.0, 2.0, "dynamic")
robot.balance_yaw(20.0, 2.0, "dynamic")
robot.balance_roll(-15.0, 2.0, "dynamic")
robot.balance_height(-0.05, 2.0, "dynamic")

# Batch API
robot.balance_sequence([
  ("balance_pitch", 15.0, 2.0, "dynamic"),
  ("balance_yaw", 20.0, 2.0, "dynamic"),
  ("balance_roll", -15.0, 2.0, "dynamic"),
  ("balance_height", -0.05, 2.0, "dynamic"),
  ("balance_neutral", 0.0, 0.5, "dynamic"),
])

# Composite pose APIs
robot.dynamic_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
robot.static_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
robot.balance_neutral()
```

#### Running

```bash
# Python
cd high_level/python
python3 examples/e6_balance_motions.py [server_address]

# C++
cd high_level/cpp/build
./e6_balance_motions [server_address]
```

---

### E7: Line Walk

**Files**: `high_level/python/examples/e7_line_walk.py` / `high_level/cpp/e7_line_walk.cpp`

#### Description

Command the robot to walk in a straight line for a specified distance. The robot must be in `BALANCE_STAND` state (or the motion will auto-navigate there). The system automatically calculates the appropriate velocity and duration based on the requested distance.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `direction` | int | 0 | Direction: 0=forward, 1=backward, 2=left, 3=right |
| `distance` | float | 1.0 | Distance in meters |

#### Sample Code

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# Walk then rotate-walk
robot.line_walk(0, 1.0)
robot.rotate_walk(angle=45, distance=1.0, speed_ratio=10)
```

#### Running

```bash
# Python
cd high_level/python
python3 examples/e7_line_walk.py [server_address] [direction] [distance]

# Example
python3 examples/e7_line_walk.py 192.168.5.2:50051 0 1.0

# C++
cd high_level/cpp/build
./e7_line_walk [server_address] [direction] [distance]
```

---

### E8: Rotation

**Files**: `high_level/python/examples/e8_rotation.py` / `high_level/cpp/e8_rotation.cpp`

#### Description

Command the robot to rotate in place by a specified angle. The robot must be in `BALANCE_STAND` state (or the motion will auto-navigate there). The system automatically calculates the appropriate angular velocity and duration.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `direction` | int | 0 | Direction: 0=left/CCW (counter-clockwise), 1=right/CW (clockwise) |
| `angle` | float | 90.0 | Rotation angle in degrees |

#### Sample Code

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# Current demo in script
# robot.rotate(direction, angle)
robot.circle(direction="right", turns=3)
```

#### Running

```bash
# Python
cd high_level/python
python3 examples/e8_rotation.py [server_address] [direction] [angle]

# Example
python3 examples/e8_rotation.py 192.168.5.2:50051 0 90

# C++
cd high_level/cpp/build
./e8_rotation [server_address] [direction] [angle]
```

---

### E9: Combo Sequence

**Files**: `high_level/python/examples/e9_combo_sequence.py` / `high_level/cpp/e9_combo_sequence.cpp`

#### Description

Demonstrates an Arduino-style blocking combo flow by chaining high-level APIs in sequence:

- state switching (`passive`, `ready`, `balance_stand`, `walk`, `change_mode`)
- 1m cardinal moves and rotation commands
- single-axis balance (`dynamic` / `static`)
- composite poses (`dynamic_pose`, `static_pose`)
- basic action states (`wave`, `dance`, `recovery`, `stand_down`)

#### Running

```bash
# Python
cd high_level/python
python3 examples/e9_combo_sequence.py [server_address]

# C++
cd high_level/cpp/build
./e9_combo_sequence [server_address]
```

---

### E10: Speed Ratio & Obstacle Avoidance

**Files**: `high_level/python/examples/e10_config_demo.py` / `high_level/cpp/e10_config_demo.cpp`

#### Description

Demonstrates how to query and configure the speed ratio and obstacle avoidance settings:

- **Speed Ratio**: Query the current value with `get_speed_ratio()`, set a persistent base value with `set_speed_ratio()`, and use the optional `speed_ratio` parameter in walk functions for temporary overrides.
- **Obstacle Avoidance**: Toggle on/off with `set_obstacle_avoidance()`, query with `get_obstacle_avoidance()`.

#### Key Concepts

- `get_speed_ratio()` returns the **locally tracked** value (updated from `set_speed_ratio()` RPC responses). It does not query the server each time.
- When `walk_forward(dist, speed_ratio=N)` is called with an explicit `speed_ratio`, the value is temporarily applied and restored after execution. When omitted, the current base speed ratio is used.
- `get_obstacle_avoidance()` similarly returns the locally tracked state.

#### Sample Code

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# Query current speed ratio
print(f"Speed ratio: {robot.get_speed_ratio()}")

# Set base speed ratio to 10 (slow)
robot.set_speed_ratio(10)
robot.walk_forward(1.0)              # uses base speed ratio (10)

# Temporary override: walk at speed_ratio=100, then restore to 10
robot.walk_forward(1.0, speed_ratio=100)
print(f"Speed ratio after: {robot.get_speed_ratio()}")  # still 10

# Toggle obstacle avoidance
robot.set_obstacle_avoidance(False)  # or "off"
print(f"OA enabled: {robot.get_obstacle_avoidance()}")  # False
robot.set_obstacle_avoidance(True)   # or "on"
print(f"OA enabled: {robot.get_obstacle_avoidance()}")  # True
```

#### Running

```bash
# Python
cd high_level/python
python3 examples/e10_config_demo.py [server_address]

# C++
cd high_level/cpp/build
./e10_config_demo [server_address]
```

---

## RPC Reference

### Service: gRPCService

| RPC | Request | Response | Type | Description |
|-----|---------|----------|------|-------------|
| `GetAvailableMotions` | `GetMotionsRequest` | `GetMotionsResponse` | Unary | List all available motions and parameters |
| `ExecuteSequence` | `ExecuteSequenceRequest` | stream `SequenceProgress` | Server-streaming | Execute a motion sequence with real-time progress |
| `GetRobotState` | `GetRobotStateRequest` | `GetRobotStateResponse` | Unary | Get robot state (joints, body, FSM state) |
| `SetSpeedRatio` | `SetSpeedRatioRequest` | `SetSpeedRatioResponse` | Unary | Set/query speed ratio [10-100] |
| `SetObstacleAvoidance` | `SetObstacleAvoidanceRequest` | `SetObstacleAvoidanceResponse` | Unary | Enable/disable obstacle avoidance |

### SetSpeedRatio

```
SetSpeedRatioRequest {
  int32 speed_ratio = 1;  // [10-100], step 10. Pass 0 to query without change.
}

SetSpeedRatioResponse {
  bool success = 1;
  string message = 2;
  int32 current_speed_ratio = 3;  // Current value after operation
}
```

### SetObstacleAvoidance

```
SetObstacleAvoidanceRequest {
  bool enable = 1;  // true = enable, false = disable
}

SetObstacleAvoidanceResponse {
  bool success = 1;
  string message = 2;
  bool current_enabled = 3;  // Current state after operation
}
```

---

## FAQ

### Q: How to interrupt a running motion sequence?

Press `Ctrl+C` to cancel the current executing sequence. The client library handles graceful cancellation.

### Q: What if state switching fails?

1. Check if the current state supports the target transition
2. Use `path_to_state` for automatic pathfinding (recommended)
3. Ensure the robot is in a safe position

### Q: Why does the robot not move forward with velocity commands?

This is usually caused by the obstacle avoidance system blocking the forward velocity (vx). Try:
1. Disable obstacle avoidance: `robot.set_obstacle_avoidance(False)`
2. Ensure there are no obstacles in front of the robot
3. Note that vy (strafe) and vyaw (turn) are not affected by obstacle avoidance

### Q: How to make the robot move faster or slower?

Adjust the speed ratio: `robot.set_speed_ratio(80)` for faster, `robot.set_speed_ratio(30)` for slower. The default value is 50. See the velocity bounds table for maximum achievable velocities at different speed ratios.

### Q: What is the difference between E4 velocity sequence and E7/E8?

- **E4** (`walk_velocity_seq`, etc.): Full control over velocity profile. You specify exact velocities and durations for each segment.
- **E7** (`line_walk`): Simplified distance-based interface. Specify direction and distance; the system calculates velocity and duration.
- **E8** (`rotation`): Simplified angle-based interface. Specify direction and angle; the system calculates angular velocity and duration.

### Q: What is the difference between `set_speed_ratio` and `speed_ratio` parameter in walk functions?

- `set_speed_ratio(N)`: Sets the **base** speed ratio persistently. All subsequent operations use this value.
- `walk_forward(dist, speed_ratio=N)`: **Temporarily** overrides the speed ratio for that single operation, then restores the base value. If `speed_ratio` is omitted (default `None`/`-1`), the current base is used without any override.

---

## Back to README

[<- Back to README](../README.md)
