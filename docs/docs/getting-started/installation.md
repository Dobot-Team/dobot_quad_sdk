# Installation

This guide covers the installation of Dobot Quad SDK for both high-level (gRPC) and low-level (DDS) control.

## 1. Prerequisites

- **OS**: Ubuntu 22.04
- **Python**: 3.10+
- **CMake**: 3.16+
- **Compiler**: GCC/G++ 9+
- **OpenCV**: 4.5.4 (tested)

### Network Connection

| Method | Robot IP | Subnet | Notes |
|--------|----------|--------|-------|
| **Wired** (Ethernet) | `192.168.5.2` | Set your PC to `192.168.5.xxx/24` | Required for DDS (low-level) |
| **WiFi** (`Rover-*`, password `12345678`) | `192.168.1.6` | Auto | gRPC (high-level) only |

## 2. High-Level Setup (gRPC)

### Python

```bash
cd high_level/python
pip install .          # or pip install -e . for development
```

### C++

```bash
sudo apt-get install -y libgrpc++-dev protobuf-compiler-grpc libprotobuf-dev pkg-config
cd high_level/cpp && mkdir -p build && cd build
cmake .. && make -j
```

## 3. Low-Level Setup (DDS)

!!! warning "Wired Connection Required"
    DDS only works over **wired** Ethernet (`192.168.5.0/24`).

### Install DDS Middleware

```bash
cd dist
sudo dpkg -i dds-middleware-with-thirdparty*.deb
export CYCLONEDDS_HOME="/usr/local/"
```

### Configure DDS Network Interface

Edit [cyclonedds.xml](../../cyclonedds.xml) (place this file from the project onto the machine using the SDK, and replace `<USER_PORT_INTERFACE>` with your network interface name such as `enp2s0`):

```xml
<NetworkInterfaces>"<USER_PORT_INTERFACE>"</NetworkInterfaces>
```

```bash
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cyclonedds ps   # verify
```

### Python

```bash
cd dist && pip install dds_middleware_python-*.whl
pip install cyclonedds opencv-python
```

### C++

```bash
sudo apt install -y libboost-dev libopencv-dev libyaml-cpp-dev cmake build-essential
cd low_level/cpp && mkdir -p build && cd build
cmake .. && make -j
```

## 4. Docker Setup (Optional)

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

## Next Steps

- [Quick Start](quickstart.md) - Run your first example
- [High-Level API Reference](../api/high_level.md) - Learn the High-Level API
- [Low-Level API Reference](../api/low_level.md) - Learn the Low-Level API
