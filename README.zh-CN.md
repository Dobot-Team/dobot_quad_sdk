<div align="center">

<h1>🤖 Dobot Quad SDK</h1>

**四足机器人开发套件**  
基于 CycloneDDS & gRPC 的高性能机器人控制框架

[简体中文](README.zh-CN.md) · [English](README.md) · [📖 高级文档](doc/high_level_api.zh-CN.md) · [📖 底层文档](doc/low_level_api.zh-CN.md)

[![Platform](https://img.shields.io/badge/Platform-Linux-blue?style=flat-square)](https://www.linux.org/)
[![Architecture](https://img.shields.io/badge/Arch-x86__64%20%7C%20ARM64-green?style=flat-square)](https://github.com)
[![Language](https://img.shields.io/badge/Language-C%2B%2B%20%7C%20Python-orange?style=flat-square)](https://github.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

</div>

---

## 简介

Dobot Quad SDK 是一个用于四足机器人二次开发的软件开发套件。SDK 提供两层 API：

### 高级控制层 (gRPC)

**依赖于机器人的主控程序。** 提供状态机管理和运动规划功能：
- 控制机器人状态（如站立、行走、平衡等）
- 发送速度指令序列
- 查询机器人状态信息（位置、速度、加速度、关节角度等）
- 执行预定义动作

### 底层控制层 (DDS)

**不依赖于机器人的主控程序。** 提供直接的硬件访问能力：
- 订阅传感器数据：RGB/深度相机图像、IMU 数据、电机状态、电池状态
- 控制执行器：LED 灯、电机指令、音频播放
- 从麦克风采集音频

⚠️ **重要提示**：使用底层电机控制时，**必须**先停止机器人的主控程序，以避免控制冲突。SDK 提供了 `kill_robot` 工具用于安全地关闭主控程序，详见 [如何安全关闭机器人主控程序](#如何安全关闭机器人主控程序)。

两层 API 均支持 C++ 和 Python 双语言开发。

---

## 快速开始

### 系统要求

| 项目         | 要求                            |
| ------------ | ------------------------------- |
| **操作系统** | Linux (Ubuntu 22.04) |
| **CMake**    | 3.16+                           |
| **编译器**   | GCC/G++ 9+                      |
| **Python**   | 3.10+                           |
| **OpenCV**   | 4.5.4 (测试版本)                |

### 网络连接配置

运行本 SDK 中的程序前，需要配置计算机与机器狗之间的网络连接。支持以下两种方式：
⚠️ **重要提示**：**底层控制层（DDS）仅支持有线网络连接**，无线连接不可用。高级控制层（gRPC）支持有线和无线两种连接方式。
#### 方式一：有线网络连接

使用网线连接计算机与机器狗：

1. 将你的计算机网络接口 IP 地址设置为 `192.168.5.xxx` 范围内（如 `192.168.5.100`）
2. 子网掩码设置为 `255.255.255.0`
3. 机器狗的 IP 地址为 `192.168.5.2`


#### 方式二：无线网络连接（WiFi）

启动机器狗后，用户主机需要连接到一个 `Rover-` 开头的 WiFi 热点（例如Rover-1RXC1011A01017）：

1. 扫描并连接到以 `Rover-` 开头的 WiFi 网络
2. WiFi 密码：`12345678`
3. 连接后，机器狗的 IP 地址为 `192.168.1.6`
4. 确认你的计算机与机器狗在同一网段下

### 安装步骤

#### 1️⃣ 高级控制层 (gRPC) 环境配置

**Python 开发：**

```bash
conda create -n sdk python=3.10 -y
conda activate sdk
cd high_level/python
pip3 install -r requirements.txt
# 编译 gRPC 消息类型
./compile_grpc.sh
```

**C++ 开发：**

```bash
# 安装 gRPC（Ubuntu 22.04）
sudo apt-get install -y libgrpc++-dev protobuf-compiler-grpc libprotobuf-dev pkg-config

# 编译项目
cd high_level/cpp && mkdir build && cd build
cmake .. && make -j
```

#### 2️⃣ 底层控制环境（DDS）配置

⚠️ **重要**：底层控制层（DDS）仅支持有线网络连接，请确保使用网线连接并配置为 192.168.5.0/24 网段。

**安装 DDS 中间件：**

```bash
# 安装 DDS 中间件包
cd dist
sudo dpkg -i dds-middleware-with-thirdparty*.deb
export CYCLONEDDS_HOME="/usr/local/"
```

**Python 开发环境：**

```bash
conda create -n sdk python=3.10 -y
conda activate sdk
cd dist
pip install dds_middleware_python-*.whl
pip install cyclonedds opencv-python
```

**C++ 开发环境：**

```bash
# 安装依赖
sudo apt install -y libboost-dev libopencv-dev libyaml-cpp-dev cmake build-essential

# 编译项目
cd low_level/cpp && mkdir -p build && cd build
cmake .. && make -j
```

**配置 DDS 网络接口：**

编辑 [cyclonedds.xml](cyclonedds.xml)，将 `enp2s0` 替换为你的有线网络接口名称（如 eth0, eno1 等）：

```xml
<NetworkInterfaces>"enp2s0"</NetworkInterfaces>
```

设置环境变量并验证：

```bash
cd dobot_quad_sdk
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cyclonedds ps  # 查看所有可订阅的话题
```

---

## Docker 使用（可选）

如果希望使用 Docker 容器运行 SDK，可以通过以下方式构建和运行：

### 构建镜像

```bash
docker build -t quad_sdk:latest .
```

### 运行容器

```bash
docker run -it --network host quad_sdk:latest
```

⚠️ **容器内配置**：进入容器后，仍需配置 DDS 网络接口和环境变量：

```bash
# 编辑 cyclonedds.xml 配置网络接口
cd /root/dobot_quad_sdk
vim cyclonedds.xml  # 修改为你的网络接口名称

# 设置环境变量
export CYCLONEDDS_URI=file:///root/dobot_quad_sdk/cyclonedds.xml

# 验证配置
cyclonedds ps
```

---

## 快速运行

### 高级控制示例

```bash
# 设置环境变量（每次运行前需执行）
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml

# Python
cd high_level/python
python3 e1_get_available_motions.py    # 获取可用运动
python3 e3_auto_state_switch.py        # 自动状态切换
python3 e6_balance_motions.py          # 平衡运动

# C++
cd high_level/cpp/build
./e1_get_available_motions
```

### 底层控制示例

```bash
# 设置环境变量（每次运行前需执行）
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml

# Python
cd low_level/python
python3 e4_imu_state_sub.py            # IMU 数据
python3 e5_motor_state_sub.py          # 电机状态
python3 e6_bms_state_sub.py            # 电池状态

# C++
cd low_level/cpp/build
./e4_imu_state_sub
```

---

## 功能概览

### 高级控制层 (gRPC)

基于 gRPC 的高级运动控制接口，提供完整的状态机管理和运动规划功能。

| 功能               | 说明                             |
| ------------------ | -------------------------------- |
| **获取可用动作**   | 查询机器人支持的所有动作及其参数 |
| **手动状态切换**   | 按照状态机规则手动切换机器人状态 |
| **自动状态切换**   | 自动寻路到目标状态               |
| **速度序列控制**   | 发送速度指令序列控制行走         |
| **机器人状态查询** | 获取关节、姿态、电池等状态信息   |
| **平衡动作控制**   | 在平衡站立模式下控制姿态         |

📖 **详细文档**: [高级控制层 API 文档](doc/high_level_api.zh-CN.md)

---

### 底层控制层 (DDS)

基于 CycloneDDS 的底层硬件通信接口，提供实时传感器数据订阅和执行器控制。

| 功能             | 说明                         |
| ---------------- | ---------------------------- |
| **RGB 图像订阅** | 获取相机彩色图像             |
| **深度图像订阅** | 获取相机深度图像             |
| **LED 灯光控制** | 控制机器人 LED 灯效          |
| **IMU 数据订阅** | 获取惯性测量单元原始数据     |
| **电机状态订阅** | 获取 16 个电机的状态信息     |
| **电池状态订阅** | 获取电池管理系统状态         |
| **语音播放**     | 播放音频文件或音频流         |
| **语音采集**     | 从麦克风获取音频流           |
| **电机指令发布** | 直接控制电机（需停止主程序） |

📖 **详细文档**: [底层控制层 API 文档](doc/low_level_api.zh-CN.md)

---

## 如何安全关闭机器人主控程序

在使用某些底层控制功能（如直接电机控制、LED 控制）前，需要先关闭机器人的主控程序。SDK 提供了专用的 `kill_robot` 工具：

### Python 版本

```bash
cd high_level/python
python3 kill_robot.py [机器人IP:端口]

# 示例
python3 kill_robot.py 192.168.5.2:50051
```

### C++ 版本

```bash
cd high_level/cpp/build
./kill_robot [机器人IP:端口]

# 示例
./kill_robot 192.168.5.2:50051
```

### 功能说明

`kill_robot` 工具会：
1. 将机器人切换到 PASSIVE 状态（电机失能）
2. 等待 5 秒确保机器人安全停止
3. 终止所有控制器进程

⚠️ **使用场景**：
- 使用底层电机指令控制（E9）前**必须**执行
- 使用 LED 灯光控制时建议执行
- 需要完全关闭机器人控制系统时

✅ **安全提示**：执行前请确保机器人处于安全位置，避免突然失能造成跌倒。

---

## 许可证

本项目采用 [MIT 许可证](LICENSE)。

<div align="center">
<sub>Built by Dobot Team</sub>
</div>
