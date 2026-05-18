# Dobot Quad SDK

**Quadruped Robot Development Kit** - A high-performance development kit using CycloneDDS & gRPC middleware, designed for secondary development based on Dobot quadruped robots.

[![Platform](https://img.shields.io/badge/Platform-Linux-blue?style=flat-square)](https://www.linux.org/)
[![Architecture](https://img.shields.io/badge/Arch-x86__64%20%7C%20ARM64-green?style=flat-square)](https://github.com)
[![Language](https://img.shields.io/badge/Language-C%2B%2B%20%7C%20Python-orange?style=flat-square)](https://github.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

## 1. SDK Architecture

![SDK Architecture](./index/structure.png){ align=center }

Dobot Quad SDK provides a comprehensive development kit for quadruped robot control. It offers two independent control layers:

### 1. High-Level Control (gRPC) [High-Level API Reference](api/high_level.md)

Depends on the robot's main control program. Provides state machine management and motion planning:

- Get Available Motions - Query all motions and parameters
- State Switch (Manual / Auto) - Follow state machine rules or auto-find path
- Velocity Sequence - Send walking velocity commands
- Robot State Query - Joints, pose, battery, etc.
- Balance Motion Control - Posture control in balance stand

### 2. Low-Level Control (DDS) [Low-Level API Reference](api/low_level.md)

Does NOT depend on the main control program. Direct hardware access.

- Camera (RGB / Depth) - Subscribe to image streams
- IMU / Motor / Battery - Real-time sensor data
- LED / Voice / Motor Cmd - Actuator control

## 2. Features

- **Dual Control Layers** - High-level (gRPC) and low-level (DDS) control
- **Multi-Language Support** - Python and C++ client libraries
- **Real-time Communication** - Low-latency data transmission
- **Cross-Platform** - Supports x86_64 and ARM64 architectures
- **Comprehensive Examples** - Ready-to-use example programs
