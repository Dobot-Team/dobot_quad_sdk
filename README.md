<div align="center">

<h1>🤖 Dobot Quad SDK</h1>

**Quadruped Robot Development Kit**  
High-performance robot control framework based on CycloneDDS & gRPC

[简体中文](README.zh-CN.md) · [English](README.md) · [📖 High-Level Docs](doc/high_level_api.md) · [📖 Low-Level Docs](doc/low_level_api.md)

[![Platform](https://img.shields.io/badge/Platform-Linux-blue?style=flat-square)](https://www.linux.org/)
[![Architecture](https://img.shields.io/badge/Arch-x86__64%20%7C%20ARM64-green?style=flat-square)](https://github.com)
[![Language](https://img.shields.io/badge/Language-C%2B%2B%20%7C%20Python-orange?style=flat-square)](https://github.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

</div>

---

## Introduction

Dobot Quad SDK is a software development kit for quadruped robot secondary development. The SDK provides two layers of APIs:

### High-Level Control Layer (gRPC)

**Depends on the robot's main control program.** Provides state machine management and motion planning capabilities:
- Control robot states (e.g., stand, walk, balance)
- Send velocity command sequences
- Query robot state information (position, velocity, acceleration, joint angles, battery status, etc.)
- Execute predefined motions

### Low-Level Control Layer (DDS)

**Does NOT depend on the robot's main control program.** Provides direct hardware access:
- Subscribe to sensor data: RGB/depth camera images, IMU data, motor states, battery status
- Control actuators: LED lights, motor commands, audio playback
- Capture audio from microphone

⚠️ **Important**: When using low-level motor control, you **MUST** first stop the robot's control processes to avoid conflicts. The SDK provides a `kill_robot` tool for safely shutting down the main control program. See [How to Safely Shutdown Robot Controller](#how-to-safely-shutdown-robot-controller) for details.

Both layers support C++ and Python development.

---

## Quick Start

### System Requirements

| Item | Requirement |
|------|-------------|
| **Operating System** | Linux (Ubuntu 22.04 or higher) |
| **CMake** | 3.16+ |
| **Compiler** | GCC/G++ 9+ |
| **Python** | 3.10+ |
| **OpenCV** | 4.5.4 (tested) |

### Network Connection Configuration

Before running programs from this SDK, you need to configure network connection between your computer and the quadruped robot. Two connection methods are supported:

⚠️ **Important**: **The low-level control layer (DDS) only supports wired network connection**; wireless connection is not available. This is because low-level control involves high-frequency sensor data reading and actuator command transmission (such as IMU, motor states, image data, etc.), requiring a stable low-latency network environment that wireless connections cannot provide. The high-level control layer (gRPC) supports both wired and wireless connections.

#### Method 1: Wired Network Connection

Use an Ethernet cable to connect your computer to the robot:

1. Set your computer's network interface IP address to the `192.168.5.xxx` range (e.g., `192.168.5.100`)
2. Set the subnet mask to `255.255.255.0`
3. The robot's IP address is `192.168.5.2`


#### Method 2: Wireless Network Connection (WiFi)

After powering on the robot, your computer needs to connect to a WiFi hotspot starting with `Rover-` (e.g., Rover-1RXC1011A01017):

1. Scan and connect to a WiFi network starting with `Rover-`
2. WiFi password: `12345678`
3. After connecting, the robot's IP address is `192.168.1.6`
4. Confirm that your computer is on the same network segment as the robot


### Installation

#### 1️⃣ Configure DDS Network Interface

⚠️ **Important**: The low-level control layer (DDS) only supports wired network connection. Please ensure you use an Ethernet cable and configure it to the 192.168.5.0/24 subnet. Due to high-frequency data transmission in low-level control (sensor data subscription, motor command publishing, etc.), the latency and stability of wireless connections cannot meet real-time control requirements.

Edit [cyclonedds.xml](cyclonedds.xml), replace `<USER_PORT_INTERFACE>` with your wired network interface name:

```xml
<CycloneDDS>
  <Domain>
    <General>
      <!-- Replace with your network interface name, e.g., eth0 (wired connection), wlan0 (wireless connection), etc. -->
      <NetworkInterfaces>"enp2s0"</NetworkInterfaces>
    </General>
  </Domain>
</CycloneDDS>
```

Replace `enp2s0` with your actual wired network interface name (such as eth0, eno1, etc.).

Set environment variable:

```bash
cd dobot_quad_sdk
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cyclonedds ps  # Verify configuration
```

#### 2️⃣ High-Level Control Layer (gRPC) Configuration

**Python Development:**

```bash
conda create -n sdk python=3.10 -y
conda activate sdk
cd high_level/python
pip3 install -r requirements.txt
# Compile gRPC message types
./compile_grpc.sh
```

**C++ Development:**

```bash
# Install gRPC (Ubuntu 22.04)
sudo apt-get install -y libgrpc++-dev protobuf-compiler-grpc libprotobuf-dev pkg-config

# Build project
cd high_level/cpp && mkdir build && cd build
cmake .. && make -j
```

#### 3️⃣ Low-Level Control Environment (DDS) Configuration

```bash
# System environment installation
sudo apt install python3 python3-pip
pip install cyclonedds

# Python
conda create -n sdk python=3.10 -y
conda activate sdk
cd dist && pip3 install dds_middleware_python-*.whl

# C++
cd dist && sudo dpkg -i dds_middleware_project_*_amd64.deb  # x86_64
```

---

## Feature Overview

### High-Level Control Layer (gRPC)

High-level motion control interface based on gRPC, providing complete state machine management and motion planning capabilities.

| Feature | Description |
|---------|-------------|
| **Get Available Motions** | Query all supported motions and their parameters |
| **Direct State Switch** | Manually switch robot states following state machine rules |
| **Auto State Switch** | Automatically find path to target state |
| **Velocity Sequence Control** | Send velocity command sequences for walking |
| **Robot State Query** | Get joint, pose, battery and other status information |
| **Balance Motion Control** | Control posture in balance stand mode |

📖 **Documentation**: [High-Level Control API Documentation](doc/high_level_api.md)

---

### Low-Level Control Layer (DDS)

Low-level hardware communication interface based on CycloneDDS, providing real-time sensor data subscription and actuator control.

| Feature | Description |
|---------|-------------|
| **RGB Image Subscription** | Get camera color images |
| **Depth Image Subscription** | Get camera depth images |
| **LED Light Control** | Control robot LED effects |
| **IMU Data Subscription** | Get raw IMU data |
| **Motor State Subscription** | Get status of 16 motors |
| **Battery State Subscription** | Get battery management system status |
| **Voice Playback** | Play audio files or audio streams |
| **Voice Capture** | Capture audio from microphone |
| **Motor Command Publishing** | Directly control motors (requires stopping main program) |

📖 **Documentation**: [Low-Level Control API Documentation](doc/low_level_api.md)

---

## Quick Run

### High-Level Control Examples

```bash
# Python
cd high_level/python
python3 e1_get_available_motions.py    # Get available motions
python3 e3_auto_state_switch.py        # Auto state switch
python3 e6_balance_motions.py          # Balance motions

# C++
cd high_level/cpp/build
./e1_get_available_motions
```

### Low-Level Control Examples

```bash
# Python
cd low_level/python
python3 e4_imu_state_sub.py            # IMU data
python3 e5_motor_state_sub.py          # Motor state
python3 e6_bms_state_sub.py            # Battery state

# C++
cd low_level/cpp/build
./e4_imu_state_sub
```

### DDS Debugging Tools

```bash
cyclonedds ps                      # View all published topics
cyclonedds typeof <topic_name>     # Check topic type information
cyclonedds sub <topic_name>        # Subscribe to specific topic
```

---

## How to Safely Shutdown Robot Controller

Before using certain low-level control features (such as direct motor control, LED control), you need to stop the robot's main control program. The SDK provides a dedicated `kill_robot` tool:

### Python Version

```bash
cd high_level/python
python3 kill_robot.py [robot_ip:port]

# Example
python3 kill_robot.py 192.168.5.2:50051
```

### C++ Version

```bash
cd high_level/cpp/build
./kill_robot [robot_ip:port]

# Example
./kill_robot 192.168.5.2:50051
```

### What It Does

The `kill_robot` tool will:
1. Switch robot to PASSIVE state (motor disable)
2. Wait 5 seconds to ensure safe shutdown
3. Terminate all controller processes

⚠️ **When to Use**:
- **MUST** execute before using low-level motor control (E9)
- Recommended before LED light control
- When you need to completely shutdown the robot control system

✅ **Safety Note**: Ensure the robot is in a safe position before execution to avoid falls due to sudden motor disable.

---

## License

This project is licensed under the [MIT License](LICENSE).

<div align="center">
<sub>Built by Dobot Team</sub>
</div>
