<div align="center">

<img src="assets/cover.png" alt="Dobot Quad SDK" style="max-width: 400px; margin-bottom: 20px;" />

<h1>Dobot Quad SDK</h1>

**四足机器人开发套件**  
基于 CycloneDDS & gRPC 的高性能机器人控制框架  
同时支持点足与轮足构型

[简体中文](README.zh-CN.md) · [English](README.md) · [📖 高层文档](docs/docs/api/high_level.zh.md) · [📖 底层文档](docs/docs/api/low_level.zh.md)

[![Platform](https://img.shields.io/badge/Platform-Linux-blue?style=flat-square)](https://www.linux.org/)
[![Architecture](https://img.shields.io/badge/Arch-x86__64%20%7C%20ARM64-green?style=flat-square)](https://github.com)
[![Language](https://img.shields.io/badge/Language-C%2B%2B%20%7C%20Python-orange?style=flat-square)](https://github.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

</div>

---

## 快速开始

### 环境要求

- **系统**: Ubuntu 22.04
- **Python**: 3.10+, **CMake**: 3.16+, **编译器**: GCC/G++ 9+
- **OpenCV**: 4.5.4 (测试版本)

### 网络连接

| 方式                                  | 机器人 IP     | 子网配置                   | 说明                  |
| ------------------------------------- | ------------- | -------------------------- | --------------------- |
| **有线** (网线)                       | `192.168.5.2` | PC 设为 `192.168.5.xxx/24` | DDS（底层）必须用有线 |
| **WiFi** (`Rover-*`，密码 `12345678`) | `192.168.1.6` | 自动                       | 仅 gRPC（高层）可用   |

### 安装

#### 高层 (gRPC)

**Python：**

```bash
cd high_level/python
pip install .          # 开发模式: pip install -e .
```

**C++：**

```bash
sudo apt-get install -y libgrpc++-dev protobuf-compiler-grpc libprotobuf-dev pkg-config
cd high_level/cpp && mkdir -p build && cd build
cmake .. && make -j
```

#### 底层控制层 (DDS)

> ⚠️ DDS 仅支持**有线**网络连接（`192.168.5.0/24`）。

**安装 DDS 中间件：**

```bash
cd dist
sudo dpkg -i dds-middleware-with-thirdparty*.deb
export CYCLONEDDS_HOME="/usr/local/"
```

**Python：**

```bash
sudo apt install -y cyclonedds-dev
cd dist && pip install dds_middleware_python-*.whl
pip install cyclonedds opencv-python
```

**C++：**

```bash
sudo apt install -y libboost-dev libopencv-dev libyaml-cpp-dev cmake build-essential
cd low_level/cpp && mkdir -p build && cd build
cmake .. && make -j
```

**配置 DDS 网络接口** — 编辑 [cyclonedds.xml](cyclonedds.xml)，将 `<USER_PORT_INTERFACE>` 替换为你的网卡名：

```xml
<NetworkInterfaces>"enp2s0"</NetworkInterfaces>
```

```bash
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cyclonedds ps   # 验证
```

---

## 运行示例

```bash
# 高层控制 (Python)
cd high_level/python
python3 examples/e1_get_available_motions.py
python3 examples/e3_auto_state_switch.py

# 高层控制 (C++)
cd high_level/cpp/build
./e1_get_available_motions

# 底层控制（需先配置 DDS 环境）
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cd low_level/python
python3 e4_imu_state_sub.py
```

---

## Docker（可选）

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

---

## 架构

SDK 提供两层独立的控制接口，均支持 C++ 和 Python：

### 高层 (gRPC)

依赖机器人主控程序，提供状态机管理和运动规划：

| 功能                  | 说明                                         |
| --------------------- | -------------------------------------------- |
| 获取可用动作          | 查询所有动作及参数                           |
| 状态切换（手动/自动） | 按状态机规则切换或自动寻路                   |
| 速度序列控制          | 发送行走速度指令                             |
| 机器人状态查询        | 关节、姿态、电池等                           |
| 平衡动作控制          | 平衡站立模式下的姿态控制（仅点足）           |
| 轮足/点足构型检测     | 通过 `is_quad_wheel()` 判断机器人类型        |
| 轮足运动模式          | `wheel_loco()`、`change_mode()` 切换运动模式 |
| 轮足专属动作          | `drift()`、`handstand()` 等（仅轮足）        |

📖 [RobotClient 接口文档](doc/robot_client_api.zh-CN.md) · [高层控制 API 文档](doc/high_level_api.zh-CN.md)

### 底层控制层 (DDS)

不依赖主控程序，直接访问硬件：

| 功能                  | 说明           |
| --------------------- | -------------- |
| 相机（RGB / 深度）    | 订阅图像流     |
| IMU / 电机 / 电池     | 实时传感器数据 |
| LED / 语音 / 电机指令 | 执行器控制     |

📖 [底层控制 API 文档](doc/low_level_api.zh-CN.md)

> ⚠️ 使用底层电机控制 (E9) 前，**必须**先用 `kill_robot` 工具停止主控程序。见下文。

---

## 安全关闭机器人主控程序

```bash
# Python
cd high_level/python
python3 examples/kill_robot.py 192.168.5.2:50051

# C++
cd high_level/cpp/build
./kill_robot 192.168.5.2:50051
```

执行流程：切换到 PASSIVE 状态 → 等待 5 秒 → 终止控制器进程。

⚠️ 底层电机控制 (E9) 前必须执行。请确保机器人处于安全位置。

---

## 项目结构

```
dobot_quad_sdk/
├── high_level/          # 基于 gRPC 的高层控制
│   ├── cpp/             # C++ 客户端库 + 示例
│   └── python/          # pip 可安装的 dobot_quad 包 + 示例
├── low_level/           # 基于 DDS 的底层控制
│   ├── cpp/             # C++ 订阅/发布 + 示例
│   └── python/          # Python 订阅/发布 + 示例
├── resources/           # 机器人 URDF 模型（点足 & 轮足）
├── doc/                 # API 文档
├── slam/                # SLAM 相关工具
└── utils/               # 实用脚本
```

---

## 许可证

[MIT 许可证](LICENSE)

<div align="center">
<sub>Built by Dobot Team</sub>
</div>
