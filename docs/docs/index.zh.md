# Dobot Quad SDK

**四足机器人开发套件** - 使用 CycloneDDS & gRPC 通信中间件实现的高性能开发套件，方便使用者基于 Dobot 四足机器人进行二次开发。

[![Platform](https://img.shields.io/badge/Platform-Linux-blue?style=flat-square)](https://www.linux.org/)
[![Architecture](https://img.shields.io/badge/Arch-x86__64%20%7C%20ARM64-green?style=flat-square)](https://github.com)
[![Language](https://img.shields.io/badge/Language-C%2B%2B%20%7C%20Python-orange?style=flat-square)](https://github.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

## 一、套件架构

![SDK整体架构](./index/structure.png){ align=center }

### 1. 高层控制 (gRPC) [高层 API 参考](api/high_level.md)

依赖机器人主控程序，提供状态机管理和运动规划。

- 获取可用动作 - 查询所有动作及参数
- 状态切换（手动/自动） - 按状态机规则切换或自动寻路
- 速度序列控制 - 发送行走速度指令
- 机器人状态查询 - 关节、姿态、电池等
- 平衡动作控制 - 平衡站立模式下的姿态控制

### 2. 底层控制 (DDS) [底层 API 参考](api/low_level.md)

不依赖主控程序，直接访问硬件。

- 相机（RGB / 深度） - 订阅图像流
- IMU / 电机 / 电池 - 实时传感器数据
- LED / 语音 / 电机指令 - 执行器控制

## 二、特性

- **双层控制接口** - 高层（gRPC）和底层（DDS）控制
- **多语言支持** - Python 和 C++ 客户端库
- **实时通信** - 低延迟数据传输
- **跨平台** - 支持 x86_64 和 ARM64 架构
- **丰富示例** - 即用的示例程序
