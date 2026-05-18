# 安装指南

本指南介绍 Dobot Quad SDK 的高层（gRPC）和底层（DDS）控制的安装方法。

## 一、环境要求

- **系统**: Ubuntu 22.04
- **Python**: 3.10+
- **CMake**: 3.16+
- **编译器**: GCC/G++ 9+
- **OpenCV**: 4.5.4 (测试版本)

### 网络连接

| 方式 | 机器人 IP | 子网配置 | 说明 |
|------|----------|----------|------|
| **有线** (网线) | `192.168.5.2` | PC 设为 `192.168.5.xxx/24` | DDS（底层）必须用有线 |
| **WiFi** (`Rover-*`，密码 `12345678`) | `192.168.1.6` | 自动 | 仅 gRPC（高层）可用 |

## 二、高层控制环境部署（gRPC）

### Python

```bash
cd high_level/python
pip install .          # 开发模式: pip install -e .
```

### C++

```bash
sudo apt-get install -y libgrpc++-dev protobuf-compiler-grpc libprotobuf-dev pkg-config
cd high_level/cpp && mkdir -p build && cd build
cmake .. && make -j
```

## 三、底层控制环境部署（DDS）

!!! warning "有线连接必需"
    DDS 仅支持**有线**网络连接（`192.168.5.0/24`）。

### 安装 DDS 中间件

```bash
cd dist
sudo dpkg -i dds-middleware-with-thirdparty*.deb
export CYCLONEDDS_HOME="/usr/local/"
```

### 配置 DDS 网络接口

编辑 [cyclonedds.xml](../../cyclonedds.xml)（将项目中的此文件放到使用SDK的机器上，将 `<USER_PORT_INTERFACE>` 替换为你的网卡名，如 `enp2s0`）：

```xml
<NetworkInterfaces>"<USER_PORT_INTERFACE>"</NetworkInterfaces>
```

```bash
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cyclonedds ps   # 验证
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

## 四、Docker环境部署（可选）

```bash
docker build -t quad_sdk:latest .
docker run -it --network host quad_sdk:latest
```

容器内配置 DDS：

```bash
cd /root/dobot_quad_sdk
vim cyclonedds.xml
export CYCLONEDDS_URI=file:///root/dobot_quad_sdk/cyclonedds.xml
```

## 下一步

- [快速入门](quickstart.zh.md) - 运行你的第一个示例
- [高层 API 参考](../api/high_level.md) - 学习高层 API
- [底层 API 参考](../api/low_level.md) - 学习底层 API
