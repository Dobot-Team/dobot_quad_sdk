# High-Level Control API Documentation

[English](high_level_api.md) · [简体中文](high_level_api.zh-CN.md)

This document provides detailed information about the Dobot Quad SDK's high-level control layer (gRPC) API, including functionality, principles, and usage of each example program.

---

## Table of Contents

- [Overview](#overview)
- [State Machine Introduction](#state-machine-introduction)
- [Kill Robot Tool](#kill-robot-tool)
- [Example Programs](#example-programs)
  - [E1: Get Available Motions](#e1-get-available-motions)
  - [E2: Direct State Switch](#e2-direct-state-switch)
  - [E3: Auto State Switch](#e3-auto-state-switch)
  - [E4: Velocity Sequence Control](#e4-velocity-sequence-control)
  - [E5: Robot State Query](#e5-robot-state-query)
  - [E6: Balance Motion Control](#e6-balance-motion-control)

---

## Overview

The high-level control layer is implemented using the gRPC protocol and provides the following core features:

- **State Machine Management**: Control transitions between different motion states
- **Motion Planning**: Execute predefined motion sequences
- **State Query**: Real-time retrieval of robot status data
- **Parameter Configuration**: Dynamic adjustment of motion parameters

### Connection

Default gRPC service address is `192.168.5.2:50051` (robot host port).

```python
import grpc
from proto import grpc_service_pb2_grpc

channel = grpc.insecure_channel("192.168.5.2:50051")
stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
```

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

## Kill Robot Tool

**Files**: `high_level/python/kill_robot.py` / `high_level/cpp/kill_robot.cpp`

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
python3 kill_robot.py [server_address:port]

# Example
python3 kill_robot.py 192.168.5.2:50051
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

### ⚠️ Important Notes

- **When to Use**: Must execute before using low-level motor control (low_level E9) or LED control (low_level E3)
- **Safety Reminder**: Before execution, ensure the robot is in a safe position (flat ground, away from obstacles) to avoid falls from sudden motor disable

---

## Example Programs

### E1: Get Available Motions

**File**: `high_level/python/e1_get_available_motions.py`

#### Description

Query all motions supported by the robot and their parameters. This is the first step to understanding robot capabilities, providing:

- Motion ID list
- Description for each motion
- Supported parameters and default values for each motion

#### Principle

Through the `GetAvailableMotions` RPC call, the server returns information about all motions registered in the `MotionLibrary`.

#### Running

```bash
cd high_level/python
python3 e1_get_available_motions.py [server_address]

# Example
python3 e1_get_available_motions.py 192.168.5.2:50051
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

  [walk]
    Description: Trigger FSM to WALK with velocity sequence support
    Parameters (default values):
      - velocity_sequence: "" (string)

  [balance_pitch]
    Description: Control robot pitch angle in balance stand with sinusoidal motion
    Parameters (default values):
      - beats: 1.0 (float)
      - amplitude: 1.0 (float)

  ......
```

#### Motion Parameter Reference

| Motion Type | Parameters | Description |
|-------------|------------|-------------|
| State switch motions | None | `passive`, `stand_down`, `stand_up`, `balance_stand`, etc. |
| Walking motions | `velocity_sequence` | Velocity sequence string, see E4 for format |
| Balance motions | `beats`, `amplitude` | Beat count and amplitude |
| Auto pathfinding | `target_state` | Target state name |

---

### E2: Direct State Switch

**File**: `high_level/python/e2_direct_state_switch.py`

#### Description

Manually switch robot states following state machine rules. Users need to know which states can be transitioned to from the current state and specify the transition path in order.

#### Difference from Auto Switch

| Feature | Direct Switch (E2) | Auto Switch (E3) |
|---------|-------------------|------------------|
| Path Planning | User-specified | System automatic |
| Use Case | Precise control over transition process | Quick navigation to target state |
| Error Handling | Invalid path will fail | Automatically finds valid path |

#### Principle

Multiple state switch motions are composed into a `MotionSequence` and executed in order. Each motion triggers one state transition.

#### Sample Code

```python
# Create motion sequence
sequence = grpc_service_pb2.MotionSequence(
    sequence_id="demo_state_switch",
    sequence_name="Direct State Switch Demo",
    loop=False
)

# Add state switch motions in order
motion_ids = ["passive", "stand_down", "stand_up", "balance_stand"]
for motion_id in motion_ids:
    motion = sequence.motions.add()
    motion.motion_id = motion_id

# Execute sequence
request = grpc_service_pb2.ExecuteSequenceRequest(
    sequence=sequence,
    immediate_start=True
)
response = stub.ExecuteSequence(request)
```

#### Running

```bash
cd high_level/python
python3 e2_direct_state_switch.py [server_address]
```

#### Sample Output

```
✓ Connected to server: 192.168.5.2:50051
example 2: Direct State Switching Demo
STAND_DOWN -> STAND_UP -> BALANCE_STAND -> DANCE0

Sequence is running... Press Ctrl+C to stop.

State switching demo executed successfully
  Execution ID: exec_12345
  Message: Sequence completed
  Number of motions: 5
```

---

### E3: Auto State Switch

**File**: `high_level/python/e3_auto_state_switch.py`

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
sequence = grpc_service_pb2.MotionSequence(
    sequence_id="path_to_state",
    sequence_name="Auto State Switch Demo",
    loop=False
)

# Use path_to_state motion
motion = sequence.motions.add()
motion.motion_id = "path_to_state"
motion.parameters.add(key="target_state", string_value="BALANCE_STAND")

request = grpc_service_pb2.ExecuteSequenceRequest(
    sequence=sequence,
    immediate_start=True
)
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
cd high_level/python
python3 e3_auto_state_switch.py [server_address]
```

The program provides an interactive menu to select the target state.

---

### E4: Velocity Sequence Control

**File**: `high_level/python/e4_velocity_sequence.py`

#### Description

Control the robot's motion trajectory through velocity sequences in `WALK` or `FLYING_TROT` state.

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

- **vx > 0**: Move forward
- **vx < 0**: Move backward
- **vy > 0**: Strafe left
- **vy < 0**: Strafe right
- **vyaw > 0**: Counter-clockwise rotation (turn left)
- **vyaw < 0**: Clockwise rotation (turn right)

#### Sample Code

```python
# Velocity sequence example: in-place rotation test
velocity_sequence = (
    "0.0,0.0,0.2,2.5;"   # Turn right in place for 2.5s
    "0.0,0.0,-0.2,2.5;"  # Turn left in place for 2.5s
    "0.0,0.0,0.0,1.0"    # Stop for 1s
)

# Create motion sequence
sequence = grpc_service_pb2.MotionSequence(
    sequence_id="demo_walk_velocity",
    sequence_name="Walk Velocity Demo",
    loop=False
)

# First switch to WALK state
motion1 = sequence.motions.add()
motion1.motion_id = "path_to_state"
motion1.parameters.add(key="target_state", string_value="WALK")

# Execute velocity sequence
motion2 = sequence.motions.add()
motion2.motion_id = "walk"  # or "flying_trot", "rl"
motion2.parameters.add(key="velocity_sequence", string_value=velocity_sequence)
```

#### Complex Motion Example

```python
# Forward, turning, strafing combination
velocity_sequence = (
    "0.0,0.5,0.0,2.0;"    # Forward for 2s
    "0.0,0.5,0.3,2.0;"    # Forward + turn right for 2s
    "0.4,0.0,0.0,1.5;"    # Strafe right for 1.5s
    "0.0,-0.3,-0.3,2.0;"  # Backward + turn left for 2s
    "0.0,0.0,-0.5,1.5;"   # Turn left in place for 1.5s
    "0.0,0.0,0.0,1.0"     # Stop
)
```

#### Running

```bash
cd high_level/python
python3 e4_velocity_sequence.py [server_address]
```

---

### E5: Robot State Query

**File**: `high_level/python/e5_robot_state.py`

#### Description

Real-time retrieval of robot status data, including:

- Joint positions, velocities, torques
- Body position and orientation
- Contact force information
- Battery voltage

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
| Body State | `pos_body (not yet available)` | m | Body position [x, y, z] |
| | `vel_body (not yet available)` | m/s | Body velocity [vx, vy, vz] |
| | `acc_body` | m/s² | Body acceleration [ax, ay, az] |
| | `ori_body` | rad | Body orientation [roll, pitch, yaw] |
| | `omega_body` | rad/s | Body angular velocity [ωx, ωy, ωz] |
| Contact Forces (Raw) | `grf_left (not yet available)` | N | Left foot forces [fx, fy, fz] |
| | `grf_right (not yet available)` | N | Right foot forces [fx, fy, fz] |
| Contact Forces (Filtered) | `grf_vertical_filtered (not yet available)` | N | Filtered vertical contact force [left, right] |
| Contact Force Statistics | `temp[0]` | N | Total contact force of left foot |
| | `temp[1]` | N | Total contact force of right foot |
| | `temp[2]` | N | Total contact force of both feet |
| | `temp[3]` | N | Total ground reaction force in X direction |
| Power Status | `temp[8]` | V | Battery 1 voltage |
| | `temp[9]` | V | Battery 2 voltage |

> **Note**: `temp[4]` to `temp[7]` are reserved fields and not currently used.

#### Running

```bash
cd high_level/python
python3 e5_robot_state.py [server_address]
```

#### Sample Output

```
Connected to server: 192.168.5.2:50051

Fetching robot state...

Robot state retrieved successfully
  Message: State retrieved

Robot State Data:

Leg Joints [rad] / [rad/s] / [Nm]:
  Positions [rad]: ['-0.05', '0.85', '-1.70', ...]
  Velocities [rad/s]: ['0.00', '0.01', '-0.02', ...]
  Torques [Nm]: ['0.12', '5.43', '-8.21', ...]

Body State:
  Position (x,y,z) [m]: ['0.00', '0.00', '0.32']
  Velocity [m/s]: ['0.00', '0.00', '0.00']
  Orientation (roll,pitch,yaw) [rad]: ['0.01', '-0.02', '0.00']

Contact Forces [N]:
  Left Foot [N]: ['0.00', '0.00', '45.23', '0.00', '0.00', '48.12']
  Right Foot [N]: ['0.00', '0.00', '44.89', '0.00', '0.00', '47.56']

Additional Data:
  Battery Voltage 1 [V]: 25.20
  Battery Voltage 2 [V]: 25.18
```

---

### E6: Balance Motion Control

**File**: `high_level/python/e6_balance_motions.py`

#### Description

Control robot posture in `BALANCE_STAND` state, executing four basic motions:

- **Pitch**: Nodding motion
- **Yaw**: Head shaking motion
- **Roll**: Side-to-side swaying
- **Height**: Squat/stand tall

#### Motion Parameters

| Parameter | Description | Range |
|-----------|-------------|-------|
| `beats` | Duration in beats | > 0 |
| `amplitude` | Motion amplitude | -1.0 ~ 1.0 |
| `bpm` | Beats per minute (set at sequence level) | > 0 |

#### Duration Calculation

```
Actual duration = beats × 60 / bpm
```

Example: `beats=1.0`, `bpm=120` → duration = 0.5 seconds

#### Amplitude Reference

| Motion | amplitude > 0 | amplitude < 0 |
|--------|---------------|---------------|
| `balance_pitch` | Look up | Look down |
| `balance_yaw` | Turn head right | Turn head left |
| `balance_roll` | Lean right | Lean left |
| `balance_height` | - | Squat (lower height) |

> Note: `balance_height` amplitude typically uses negative values (-1.0 ~ 0.0)

#### Sample Code

```python
sequence = grpc_service_pb2.MotionSequence(
    sequence_id="demo_balance_motions",
    sequence_name="Balance Motions Demo",
    bpm=120.0,  # Set BPM
    loop=False
)

# First switch to BALANCE_STAND state
motion = sequence.motions.add()
motion.motion_id = "path_to_state"
motion.parameters.add(key="target_state", string_value="BALANCE_STAND")

# Nod motion
motion = sequence.motions.add()
motion.motion_id = "balance_pitch"
motion.parameters.add(key="beats", float_value=1.0)
motion.parameters.add(key="amplitude", float_value=0.8)  # Look up

motion = sequence.motions.add()
motion.motion_id = "balance_pitch"
motion.parameters.add(key="beats", float_value=1.0)
motion.parameters.add(key="amplitude", float_value=-0.8)  # Look down

# Head shake motion
motion = sequence.motions.add()
motion.motion_id = "balance_yaw"
motion.parameters.add(key="beats", float_value=1.0)
motion.parameters.add(key="amplitude", float_value=0.8)  # Turn right

# Squat motion
motion = sequence.motions.add()
motion.motion_id = "balance_height"
motion.parameters.add(key="beats", float_value=2.0)
motion.parameters.add(key="amplitude", float_value=-0.8)  # Squat

# Return to neutral position
motion = sequence.motions.add()
motion.motion_id = "balance_neutral"
motion.parameters.add(key="beats", float_value=1.0)
```

#### Running

```bash
cd high_level/python
python3 e6_balance_motions.py [server_address] [bpm]

# Example: using 120 BPM
python3 e6_balance_motions.py 192.168.5.2:50051 120
```

#### Sample Output

```
Connected to server: 192.168.5.2:50051

Example 6: Balance Motions Demo

Sequence is running... Press Ctrl+C to stop.

Balance motions demo executed successfully
  Execution ID: exec_67890
```

---

## FAQ

### Q: How to interrupt a running motion sequence?

Press `Ctrl+C` to cancel the current executing sequence.

### Q: What if state switching fails?

1. Check if the current state supports the target transition
2. Use `path_to_state` for automatic pathfinding
3. Ensure the robot is in a safe position

---

## Back to README

[← Back to README](../README.md)
