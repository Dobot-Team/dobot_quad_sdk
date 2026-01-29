# Low-Level Control API Documentation

[English](low_level_api.md) · [简体中文](low_level_api.zh-CN.md)

This document provides detailed information about the Dobot Quad SDK's low-level control layer (DDS) API, including functionality, QoS configuration, principles, and usage of each example program.

---

## Table of Contents

- [Overview](#overview)
- [QoS Configuration](#qos-configuration)
- [Example Programs](#example-programs)
  - [E1: RGB Image Subscription](#e1-rgb-image-subscription)
  - [E2: Depth Image Subscription](#e2-depth-image-subscription)
  - [E3: LED Light Control](#e3-led-light-control)
  - [E4: IMU Data Subscription](#e4-imu-data-subscription)
  - [E5: Motor State Subscription](#e5-motor-state-subscription)
  - [E6: Battery State Subscription](#e6-battery-state-subscription)
  - [E7: Voice Playback](#e7-voice-playback)
  - [E8: Voice Capture](#e8-voice-capture)
  - [E9: Motor Command Publishing](#e9-motor-command-publishing)

---

## Overview

The low-level control layer is implemented using CycloneDDS, providing direct access to robot hardware:

- **Sensor Subscription**: IMU, motor state, battery state, images, etc.
- **Actuator Control**: LED lights, motor commands, voice playback
- **Low-Latency Communication**: Millisecond-level real-time data transmission

### Initialization

```python
import dds_middleware_python as dds

# Initialize with config file
middleware = dds.PyDDSMiddleware("config/dds_config.yaml")

# Or initialize with Domain ID
middleware = dds.PyDDSMiddleware(0)
```

---

## QoS Configuration

DDS QoS (Quality of Service) configuration determines the reliability and performance characteristics of data transmission.

### Default Configuration File

Configuration file located at `low_level/python/config/dds_config.yaml`:

| Configuration | Writer Default | Reader Default | Description |
|---------------|----------------|----------------|-------------|
| `domain_id` | 0 | 0 | DDS domain ID |
| `reliability` | `reliable` | `best_effort` | Reliability policy |
| `history_kind` | `keep_last` | `keep_last` | History type |
| `history_depth` | 10 | 10 | History depth |
| `durability` | `volatile` | `volatile` | Durability policy |
| `liveliness` | `automatic` | `automatic` | Liveliness policy |
| `deadline` | `infinite` | `infinite` | Deadline |

### QoS Parameter Reference

| Parameter | Values | Description |
|-----------|--------|-------------|
| `reliability` | `reliable` / `best_effort` | reliable guarantees delivery, best_effort allows packet loss |
| `history_kind` | `keep_last` / `keep_all` | keep_last retains only latest N, keep_all retains all |
| `history_depth` | integer | Number of historical messages to retain |
| `durability` | `volatile` / `transient_local` | volatile doesn't save history, transient_local saves for late subscribers |

### Recommended Configurations

| Scenario | Reliability | History Depth | Description |
|----------|-------------|---------------|-------------|
| Real-time sensor data | best_effort | 1-5 | Low latency, allows packet loss |
| Control commands | reliable | 1-5 | Guaranteed delivery |
| Image data | best_effort | 1-5 | Large data, prioritize low latency |

---

## Example Programs

### E1: RGB Image Subscription

**File**: `low_level/python/e1_rgb_image_sub.py`

#### Description

Subscribe to compressed RGB color image data from the robot camera.

#### QoS Configuration

```python
# Uses default reader QoS from config file
# reliability: best_effort
# history_kind: keep_last
# history_depth: 10
# durability: volatile
```

#### Topic

| Topic Name | Message Type | Description |
|------------|--------------|-------------|
| `rt/camera/camera2/image_compressed` | `CompressedImage` | Compressed RGB image |

#### Image Saving

The example automatically saves received images to the `rgb_images/` directory:

**Python Version:**
- Uses OpenCV (`cv2.imdecode`) to decode compressed JPEG data into raw image format
- Saves as lossless PNG format for better quality
- Filename format: `rgb_{timestamp_sec}_{timestamp_nanosec}.png`

**C++ Version:**
- Uses `cv::imdecode` to decode compressed data into `cv::Mat`
- Saves as PNG format using `cv::imwrite`
- Same filename format as Python version

#### Sample Code

```python
import dds_middleware_python as dds
import cv2
import numpy as np
import os

def image_callback(data):
    print(f"Received RGB CompressedImage:")
    print(f"  Timestamp: {data.header().stamp().sec()}.{data.header().stamp().nanosec():09d} (sec.nanosec)")
    print(f"  Frame ID: {data.header().frame_id()}")
    print(f"  Format: {data.format()}")
    print(f"  Data size: {len(data.data())} bytes")
    
    # Decode compressed image
    np_arr = np.array(data.data(), dtype=np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    if image is not None:
        filename = f"rgb_images/rgb_{data.header().stamp().sec()}_{data.header().stamp().nanosec()}.png"
        cv2.imwrite(filename, image)
        print(f"Saved raw image to {filename}")

# Create save directory
os.makedirs("rgb_images", exist_ok=True)

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeCompressedImage("rt/camera/camera2/image_compressed", image_callback)
```

#### Sample Output

```
Subscribed to RGB image topic. Waiting for messages...
Received RGB CompressedImage:
  Timestamp: 1706000000.123456789 (sec.nanosec)
  Frame ID: camera2_optical_frame
  Format: jpeg
  Data size: 45678 bytesSaved raw image to rgb_images/rgb_1706000000_123456789.png---
```

#### Running

```bash
cd low_level/python
python3 e1_rgb_image_sub.py
```

---

### E2: Depth Image Subscription

**File**: `low_level/python/e2_depth_image_sub.py`

#### Description

Subscribe to raw depth image data from the robot depth camera.

#### QoS Configuration

```python
qos_config = {
    "reliability": "best_effort",
    "history_kind": "keep_last",
    "history_depth": 5,
    "durability": "volatile"
}
```

#### Topic

| Topic Name | Message Type | Description |
|------------|--------------|-------------|
| `rt/camera/camera2/image_depth` | `Image` | Raw depth image |

#### Depth Image Visualization

The example processes and saves depth images to the `depth_images/` directory:

**Visualization processing:**
1. **Normalization**: Use `cv2.normalize` to stretch depth values to 0-255 range
2. **Pseudo-color**: Apply Jet colormap (red/warm = near, blue/cold = far)
3. **Save**: Save processed visualization as PNG file

**Python Version:**
- Converts raw bytes to numpy array with `view(np.uint16)`
- Applies normalization and colormap using OpenCV
- Filename format: `depth_{timestamp_sec}_{timestamp_nanosec}.png`

**C++ Version:**
- Creates `cv::Mat` directly from raw data pointer
- Uses `cv::normalize` and `cv::applyColorMap` for visualization
- Same filename format as Python version

#### Sample Code

```python
import dds_middleware_python as dds
import cv2
import numpy as np
import os

def depth_image_callback(depth_msg):
    print(f"Received Image message:")
    print(f"  Timestamp: {depth_msg.header().stamp().sec()}.{depth_msg.header().stamp().nanosec():09d}")
    print(f"  Frame ID: {depth_msg.header().frame_id()}")
    print(f"  Encoding: {depth_msg.encoding()}")
    print(f"  Data size: {len(depth_msg.data())} bytes")
    
    if "16UC1" in depth_msg.encoding():
        # Convert to 16-bit depth map
        raw_data = np.array(depth_msg.data(), dtype=np.uint8)
        depth_img = raw_data.view(np.uint16).reshape((depth_msg.height(), depth_msg.width()))
        
        # Normalize and apply colormap
        depth_vis = cv2.normalize(depth_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
        
        filename = f"depth_images/depth_{depth_msg.header().stamp().sec()}_{depth_msg.header().stamp().nanosec()}.png"
        cv2.imwrite(filename, depth_color)
        print(f"Saved visibility depth map to {filename}")

# Create save directory
os.makedirs("depth_images", exist_ok=True)

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeImage("rt/camera/camera2/image_depth", depth_image_callback, qos_config)
```

#### Sample Output

```
Starting DDS Python Image subscriber...
Subscribing to topic: rt/camera/camera2/image_depth
Using QoS config: {'reliability': 'best_effort', 'history_kind': 'keep_last', 'history_depth': 5, 'durability': 'volatile'}
Image subscriber started, waiting for messages...
Received Image message:
  Timestamp: 1706000000.123456789
  Image size: 640x480
  Encoding: 16UC1
  Data size: 614400 bytes
  Step: 1280
  Big endian: False
---
```

#### Running

```bash
cd low_level/python
python3 e2_depth_image_sub.py
```

---

### E3: LED Light Control

**File**: `low_level/python/e3_led_control_pub.py`

#### Description

Control the 6 LED lights on the robot, supporting RGB color settings and breathing light effects.

#### ⚠️ Important Warning

**You must stop the robot's main control program before running this program!** Otherwise, LED control may not take effect.

How to stop the main control program (recommended using SDK tool):

```bash
# Recommended: Use kill_robot tool
cd high_level/python
python3 kill_robot.py 192.168.5.2:50051

# Or use C++ version
cd high_level/cpp/build
./kill_robot 192.168.5.2:50051
```

The `kill_robot` tool will safely switch the robot to PASSIVE state and terminate controller processes. See [README shutdown section](../README.md#how-to-safely-shutdown-robot-controller) for details.

#### QoS Configuration

```python
qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}
```

#### Topic

| Topic Name | Message Type | Description |
|------------|--------------|-------------|
| `rt/leds/cmd` | `LedsCmd` | LED control command |

#### LED Names

| LED Name | Location | Description |
|----------|----------|-------------|
| `leg_light1` | Leg light 1 | - |
| `leg_light2` | Leg light 2 | - |
| `leg_light3` | Leg light 3 | - |
| `leg_light4` | Leg light 4 | - |
| `fill_light1` | Front light | Illumination light at the front of the robot |
| `fill_light2` | Fill light 2 | Currently unavailable |
| `fill_light3` | Rear light | Illumination light at the rear of the robot |

#### Sample Code

```python
import dds_middleware_python as dds
import math
import time

middleware = dds.PyDDSMiddleware(0)

qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}

middleware.createLedsCmdWriter("rt/leds/cmd", qos_config)

# Create LED control command
led_cmd = dds.LedsCmd()
leds = []

# LED1 - Red
led1 = dds.LEDControl()
led1.name("leg_light1")
led1.mode(0)  # RGB mode
led1.brightness(255)
led1.r(255)
led1.g(0)
led1.b(0)
led1.priority(0)
leds.append(led1)

led_cmd.leds(leds)
middleware.publishLedsCmd(led_cmd)
```

#### Sample Output

```
LED control publisher started, press Ctrl+C to exit...
Published LED control command: Intensity: 50% LED1 (R:127 G:0 B:0) LED2 (R:0 G:127 B:0) ...
Published LED control command: Intensity: 100% LED1 (R:255 G:0 B:0) LED2 (R:0 G:255 B:0) ...
Program finished after 15000ms
```

#### Running

```bash
cd low_level/python
python3 e3_led_control_pub.py
```

---

### E4: IMU Data Subscription

**File**: `low_level/python/e4_imu_state_sub.py`

#### Description

Get raw IMU (Inertial Measurement Unit) data directly from the low level, including quaternion, gyroscope, and accelerometer data.

#### QoS Configuration

```python
# Uses default reader QoS from config file
# reliability: best_effort
# history_kind: keep_last
# history_depth: 10
# durability: volatile
```

#### Topic

| Topic Name | Message Type | Description |
|------------|--------------|-------------|
| `rt/lower/state` | `LowerState` | Lower-level state (includes IMU data) |

#### Data Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `quaternion` | float[4] | - | Orientation quaternion [w, x, y, z] |
| `gyroscope` | float[3] | rad/s | Gyroscope angular velocity [x, y, z] |
| `accelerometer` | float[3] | m/s² | Accelerometer [x, y, z] |
| `rpy` | float[3] | rad | Euler angles [roll, pitch, yaw] |

#### Sample Code

```python
import dds_middleware_python as dds
import time

def lower_state_callback(state):
    imu_state = state.imu_state()
    print(f"IMU State:")
    print(f"  Quaternion: {list(imu_state.quaternion())}")
    print(f"  Gyroscope (rad/s): {list(imu_state.gyroscope())}")
    print(f"  Accelerometer (m/s²): {list(imu_state.accelerometer())}")
    print(f"  RPY (roll, pitch, yaw in rad): {list(imu_state.rpy())}")

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeLowerState("rt/lower/state", lower_state_callback)
```

#### Sample Output

```
Received LowerState #100
IMU State:
  Quaternion: [0.9998, 0.0012, -0.0156, 0.0023]
  Gyroscope (rad/s): [0.0021, -0.0034, 0.0012]
  Accelerometer (m/s²): [0.12, -0.08, 9.78]
  RPY (roll, pitch, yaw in rad): [0.0024, -0.0312, 0.0046]
```

#### Running

```bash
cd low_level/python
python3 e4_imu_state_sub.py
```

---

### E5: Motor State Subscription

**File**: `low_level/python/e5_motor_state_sub.py`

#### Description

Get status data for all 16 motors directly from the low level, including position, velocity, torque, and temperature information.

#### QoS Configuration

```python
# Uses default reader QoS from config file
# reliability: best_effort
# history_kind: keep_last
# history_depth: 10
# durability: volatile
```

#### Topic

| Topic Name | Message Type | Description |
|------------|--------------|-------------|
| `rt/lower/state` | `LowerState` | Lower-level state (includes motor data) |

#### Motor Data Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `mode` | uint8 | - | Mode: 0-disabled, 1-error, 2-offline, 3-enabled, 4-controlled, 5-homing |
| `q` | float | rad | Angular position |
| `dq` | float | rad/s | Angular velocity |
| `ddq` | float | rad/s² | Angular acceleration |
| `tau_est` | float | Nm | Estimated torque |
| `q_raw` | float | rad | Raw angular position |
| `dq_raw` | float | rad/s | Raw angular velocity |
| `ddq_raw` | float | rad/s² | Raw angular acceleration |
| `motor_temp` | uint8 | °C | Motor temperature |

#### Motor Numbering

The robot has 16 motors, numbered 0-15, distributed across four legs:

| Leg | Motor IDs |
|-----|-----------|
| Front Left | 0, 1, 2, 3 |
| Front Right | 4, 5, 6, 7 |
| Rear Left | 8, 9, 10, 11 |
| Rear Right | 12, 13, 14, 15 |

#### Sample Code

```python
import dds_middleware_python as dds

def lower_state_callback(state):
    motor_states = state.motor_state()
    print(f"Received Motor States")
    for i in range(16):
        motor = motor_states[i]
        print(f"Motor[{i}]: mode={motor.mode()}, q={motor.q():.4f} rad, "
              f"dq={motor.dq():.4f} rad/s, tau_est={motor.tau_est():.4f} Nm, "
              f"temp={motor.motor_temp()}°C")

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeLowerState("rt/lower/state", lower_state_callback)
```

#### Sample Output

```
Received Motor States #50
Motor[0]: mode=4, q(rad)=-0.0523, dq(rad/s)=0.0012, ddq(rad/s²)=0.0001, tau_est(N·m)=0.12345, q_raw(rad)=-0.0523, dq_raw(rad/s)=0.0012, ddq_raw(rad/s²)=0.0001, motor_temp(°C)=35
Motor[1]: mode=4, q(rad)=0.8542, dq(rad/s)=-0.0034, ...
...
```

#### Running

```bash
cd low_level/python
python3 e5_motor_state_sub.py
```

---

### E6: Battery State Subscription

**File**: `low_level/python/e6_bms_state_sub.py`

#### Description

Get Battery Management System (BMS) status information.

#### ⚠️ Note

**The Python version of E6 currently only outputs battery_level information.** For complete BMS data, please refer to the C++ version.

#### QoS Configuration

```python
# Uses default reader QoS from config file
# reliability: best_effort
# history_kind: keep_last
# history_depth: 10
# durability: volatile
```

#### Topic

| Topic Name | Message Type | Description |
|------------|--------------|-------------|
| `rt/lower/state` | `LowerState` | Lower-level state (includes BMS data) |

#### Sample Code

```python
import dds_middleware_python as dds

def lower_state_callback(state):
    bms = state.bms_state()
    print(f"Received BMS State")
    print(f"Battery Level: {bms.battery_level()}")

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeLowerState("rt/lower/state", lower_state_callback)
```

#### Sample Output

```
Received BMS State #100
Battery Level: 85
```

#### Running

```bash
cd low_level/python
python3 e6_bms_state_sub.py
```

---

### E7: Voice Playback

**File**: `low_level/python/e7_voice_pub.py`

#### Description

Send voice playback commands to the robot, supporting two modes:

1. **File mode**: Play audio files located on the robot host
2. **Streaming mode**: Send real-time audio stream data

#### QoS Configuration

```python
qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 5,
    "durability": "volatile"
}
```

#### Topic

| Topic Name | Message Type | Description |
|------------|--------------|-------------|
| `rt/voice/cmd` | `VoiceCmd` | Voice command |

#### File Mode

Play audio files on the robot host.

**Important**: Audio files must exist on the robot host, not on the development machine!

```python
import dds_middleware_python as dds

middleware = dds.PyDDSMiddleware(0)

qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 5,
    "durability": "volatile"
}

middleware.createVoiceCmdWriter("rt/voice/cmd", qos_config)

# ⚠️ IMPORTANT: Sleep for ~1 second before publishing
# Reason: DDS is a distributed middleware that requires time to discover entities.
# The discovery process (Entity Discovery) is conducted through network protocol handshakes,
# typically requiring 100-1000ms. If you publish immediately, the remote endpoint may not
# have fully discovered the Writer yet, causing message loss.
import time
time.sleep(1)

# File mode
voice_cmd = dds.VoiceCmd()
voice_cmd.type("file")
voice_cmd.path("/root/test.wav")  # File path on robot host
voice_cmd.data([])

middleware.publishVoiceCmd(voice_cmd)
```

Supported audio formats:
- WAV
- FLAC
- MP3

#### Streaming Mode

Send real-time audio stream data, suitable for TTS or real-time audio transmission scenarios.

Audio requirements:
- Sample rate: 24kHz
- Bit depth: 16bit
- Channels: Mono

```python
# Streaming mode
voice_cmd = dds.VoiceCmd()
voice_cmd.type("streaming")
voice_cmd.path("")
voice_cmd.data(audio_bytes)  # PCM audio data

middleware.publishVoiceCmd(voice_cmd)
```

#### Running

```bash
cd low_level/python

# File mode
python3 e7_voice_pub.py file

# Streaming mode (capture from microphone)
python3 e7_voice_pub.py streaming
```

---

### E8: Voice Capture

**File**: `low_level/python/e8_voice_sub.py`

#### Description

Subscribe to audio stream data from the robot microphone.

Audio specifications:
- Sample rate: 24kHz
- Bit depth: 16bit
- Channels: Mono

#### QoS Configuration

```python
qos_config = {
    "reliability": "best_effort",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}
```

#### Topic

| Topic Name | Message Type | Description |
|------------|--------------|-------------|
| `rt/voice/state` | `VoiceState` | Voice state/audio stream |

#### Sample Code

```python
import dds_middleware_python as dds

def voice_state_callback(voice_state_msg):
    print(f"Received VoiceState message:")
    print(f"  Data size: {len(voice_state_msg.data_())} bytes")

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeVoiceState("rt/voice/state", voice_state_callback, qos_config)
```

#### Sample Output

```
Starting DDS Python VoiceState subscriber...
Subscribing to topic: rt/voice/state
VoiceState subscriber started, waiting for voice state messages...
Received VoiceState message:
  Data size: 4800 bytes
---
```

#### Running

```bash
cd low_level/python
python3 e8_voice_sub.py
```

---

### E9: Motor Command Publishing

**File**: `low_level/python/e9_motor_cmd_pub.py`

#### Description

Send control commands directly to motors. This example demonstrates sinusoidal position control testing.

#### 🚨 CRITICAL SAFETY WARNING

**You MUST stop the robot's main control program before running this program!**

Directly controlling motors without stopping the main program **WILL CAUSE SERIOUS SAFETY HAZARDS**, potentially resulting in:
- ⚠️ **Control Conflicts**: Main program and your code sending conflicting commands simultaneously
- 🤖 **Robot Out of Control**: Unpredictable and dangerous movements
- 🔥 **Hardware Damage**: Motor overload, overheating, mechanical collisions
- 👥 **Personal Injury**: Unexpected robot movements causing harm

#### ✅ Proper Shutdown Procedure (MANDATORY!)

**Use the `kill_robot` tool provided by the SDK**:

```bash
# Python version (recommended)
cd high_level/python
python3 kill_robot.py 192.168.5.2:50051

# C++ version
cd high_level/cpp/build
./kill_robot 192.168.5.2:50051
```

The `kill_robot` tool will safely:
1. ✅ Switch robot to **PASSIVE** state (motors disabled)
2. ⏱️ Wait **5 seconds** to ensure safe shutdown
3. 🚫 Terminate all controller processes

For details, see: [README - How to Safely Shutdown Robot Controller](../README.md#how-to-safely-shutdown-robot-controller)

#### 🛡️ Pre-Execution Checklist

Before running motor control programs, confirm:

- [ ] Main control program stopped using `kill_robot` tool
- [ ] Robot in safe position (flat ground, away from obstacles)
- [ ] Area clear of personnel and valuables
- [ ] Understand what commands your code will send
- [ ] Emergency stop ready (Ctrl+C)

#### Publish/Subscribe Topics

| Topic Name | Type | Message Type | Description |
|------------|------|--------------|-------------|
| `rt/lower/cmd` | Publish | `LowerCmd` | Motor control command |
| `rt/lower/state` | Subscribe | `LowerState` | Motor state feedback |

#### Motor Command Parameters

| Parameter | Type | Unit | Description |
|-----------|------|------|-------------|
| `mode` | uint8 | - | Control mode |
| `q` | float | rad | Target position |
| `dq` | float | rad/s | Target velocity |
| `tau` | float | Nm | Feedforward torque |
| `kp` | float | - | Position gain |
| `kd` | float | - | Velocity gain |

#### Control Formula

```
τ = kp × (q_des - q) + kd × (dq_des - dq) + τ_ff
```

Where:
- `τ` - Final output torque
- `q_des`, `dq_des` - Desired position and velocity
- `q`, `dq` - Actual position and velocity
- `τ_ff` - Feedforward torque
- `kp`, `kd` - Gain parameters

#### Sample Code

```python
import dds_middleware_python as dds
import math

# Motor index mapping
NUM_MOTORS = 12
ABS2HW = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14]
MOTOR_OFFSET = [
    -0.05, -0.5, 1.17, 0.0, 0.05, -0.5, 1.17, 0.0, 
    -0.05, 0.5, -1.17, 0.0, 0.05, 0.5, -1.17, 0.0
]

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")

qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}

middleware.createLowerCmdWriter("rt/lower/cmd", qos_config)

# Create sinusoidal control command
def create_swing_cmd(s, q_init):
    cmd = dds.LowerCmd()
    for i in range(NUM_MOTORS):
        hw = ABS2HW[i]
        qdes = q_init[hw] + math.sin(2 * math.pi * s) * 0.2 + MOTOR_OFFSET[hw]
        cmd[hw].mode(0)
        cmd[hw].q(qdes)
        cmd[hw].dq(0.0)
        cmd[hw].tau(0.0)
        cmd[hw].kp(30.0)
        cmd[hw].kd(1.2)
    return cmd
```

#### Running

```bash
cd low_level/python
python3 e9_motor_cmd_pub.py
```

#### Sample Output

```
Waiting for initial position collection...
Initial position collection completed: -0.0500 0.8500 -1.7000 ...
Starting control loop
[0] Initialization phase
[10] Starting swing
[5000] Swing completed, entering damping mode
```

---

## FAQ

### Q: Not receiving any data?

1. Check if `CYCLONEDDS_URI` environment variable is set
2. Check if network interface configuration is correct
3. Use `cyclonedds ps` to view available topics

### Q: LED control has no effect?

You must stop the main control program first. See the warning in E3 section.

### Q: Motor control not responding?

1. Must stop the main control program first
2. Confirm motor initial position collection is complete

### Q: Severe image data packet loss?

Use `best_effort` reliability and smaller `history_depth` to prioritize low latency.

---

## Back

[← Back to README](../README.md)
