<div align="center">

<img src="assets/cover.png" alt="Dobot Quad SDK" style="max-width: 400px; margin-bottom: 20px;" />

<h1>Dobot Quad SDK</h1>

**Quadruped Robot Development Kit**  
High-performance robot control via CycloneDDS & gRPC  
Supports both legged and wheel-legged configurations

[简体中文](README.zh-CN.md) · [English](README.md) · [📖 High-Level Docs](docs/docs/api/high_level.md) · [📖 Low-Level Docs](docs/docs/api/low_level.md)

[![Platform](https://img.shields.io/badge/Platform-Linux-blue?style=flat-square)](https://www.linux.org/)
[![Architecture](https://img.shields.io/badge/Arch-x86__64%20%7C%20ARM64-green?style=flat-square)](https://github.com)
[![Language](https://img.shields.io/badge/Language-C%2B%2B%20%7C%20Python-orange?style=flat-square)](https://github.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

</div>

---

## Quick Start

### Prerequisites

- **OS**: Ubuntu 22.04
- **Python**: 3.10+, **CMake**: 3.16+, **Compiler**: GCC/G++ 9+
- **OpenCV**: 4.5.4 (tested)

### Network Connection

| Method                                    | Robot IP      | Subnet                            | Notes                        |
| ----------------------------------------- | ------------- | --------------------------------- | ---------------------------- |
| **Wired** (Ethernet)                      | `192.168.5.2` | Set your PC to `192.168.5.xxx/24` | Required for DDS (low-level) |
| **WiFi** (`Rover-*`, password `12345678`) | `192.168.1.6` | Auto                              | gRPC (high-level) only       |

### Installation

#### High-Level Control (gRPC)

**Python:**

```bash
cd high_level/python
pip install .          # or pip install -e . for development
```

**C++:**

```bash
sudo apt-get install -y libgrpc++-dev protobuf-compiler-grpc libprotobuf-dev pkg-config
cd high_level/cpp && mkdir -p build && cd build
cmake .. && make -j
```

#### Low-Level Control (DDS)

> ⚠️ DDS only works over **wired** Ethernet (`192.168.5.0/24`).

**Install DDS middleware:**

```bash
cd dist
sudo dpkg -i dds-middleware-with-thirdparty*.deb
export CYCLONEDDS_HOME="/usr/local/"
```

**Python:**

```bash
sudo apt install -y cyclonedds-dev
cd dist && pip install dds_middleware_python-*.whl
pip install cyclonedds opencv-python
```

**C++:**

```bash
sudo apt install -y libboost-dev libopencv-dev libyaml-cpp-dev cmake build-essential
cd low_level/cpp && mkdir -p build && cd build
cmake .. && make -j
```

**Configure DDS network interface** — edit [cyclonedds.xml](cyclonedds.xml), replace `<USER_PORT_INTERFACE>` with your interface name such as `enp2s0`:

```xml
<NetworkInterfaces>"enp2s0"</NetworkInterfaces>
```

```bash
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cyclonedds ps   # verify
```

---

## Running Examples

```bash
# High-level (Python)
cd high_level/python
python3 examples/e1_get_available_motions.py
python3 examples/e3_auto_state_switch.py

# High-level (C++)
cd high_level/cpp/build
./e1_get_available_motions

# Low-level (requires DDS env configured)
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cd low_level/python
python3 e4_imu_state_sub.py
```

---

## Docker (Optional)

```bash
docker build -t quad_sdk:latest .
docker run -it --network host quad_sdk:latest
```

Inside the container, configure DDS as above:

```bash
cd /root/dobot_quad_sdk
vim cyclonedds.xml
export CYCLONEDDS_URI=file:///root/dobot_quad_sdk/cyclonedds.xml
```

---

## Architecture

The SDK provides two independent control layers, each supporting C++ and Python:

### High-Level Control (gRPC)

Depends on the robot's main control program. Provides state machine management and motion planning:

| Feature                      | Description                                      |
| ---------------------------- | ------------------------------------------------ |
| Get Available Motions        | Query all motions and parameters                 |
| State Switch (Manual / Auto) | Follow state machine rules or auto-find path     |
| Velocity Sequence            | Send walking velocity commands                   |
| Robot State Query            | Joints, pose, battery, etc.                      |
| Balance Motion Control       | Posture control in balance stand (legged only)   |
| Wheel/Leg Mode Detection     | Check robot type via `is_quad_wheel()`           |
| Wheel Locomotion             | `wheel_loco()`, `change_mode()` for wheel-legged |
| Wheel-Specific Motions       | `drift()`, `handstand()` (wheel-legged only)     |

📖 [RobotClient API Docs](doc/robot_client_api.md) · [High-Level API Docs](doc/high_level_api.md)

### Low-Level Control (DDS)

Does NOT depend on the main control program. Direct hardware access:

| Feature                 | Description                |
| ----------------------- | -------------------------- |
| Camera (RGB / Depth)    | Subscribe to image streams |
| IMU / Motor / Battery   | Real-time sensor data      |
| LED / Voice / Motor Cmd | Actuator control           |

📖 [Low-Level API Docs](doc/low_level_api.md)

> ⚠️ Before using direct motor control (E9), you **must** stop the robot's main control program with the `kill_robot` tool. See below.

---

## Safely Shutdown Robot Controller

```bash
# Python
cd high_level/python
python3 examples/kill_robot.py 192.168.5.2:50051

# C++
cd high_level/cpp/build
./kill_robot 192.168.5.2:50051
```

This will: switch to PASSIVE state → wait 5 s → terminate controller processes.

⚠️ Required before low-level motor control (E9). Ensure the robot is in a safe position first.

---

## Project Structure

```
dobot_quad_sdk/
├── high_level/          # gRPC-based high-level control
│   ├── cpp/             # C++ client library + examples
│   └── python/          # pip-installable dobot_quad package + examples
├── low_level/           # DDS-based low-level control
│   ├── cpp/             # C++ subscribers/publishers + examples
│   └── python/          # Python subscribers/publishers + examples
├── resources/           # Robot URDF models (legged & wheel-legged)
├── doc/                 # API documentation
└── utils/               # Utility scripts
```

---

## License

[MIT License](LICENSE)

<div align="center">
<sub>Built by Dobot Team</sub>
</div>
