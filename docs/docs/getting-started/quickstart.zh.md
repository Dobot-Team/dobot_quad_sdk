# 快速入门

本指南将帮助你运行第一个 Dobot Quad SDK 示例程序。

## 一、前提条件

确保你已完成 [安装指南](installation.zh.md)。

## 二、运行高层示例

### Python

```bash
# 高层控制 (Python)
cd high_level/python
python3 examples/e1_get_available_motions.py
python3 examples/e3_auto_state_switch.py
```

### C++

```bash
# 高层控制 (C++)
cd high_level/cpp/build
./e1_get_available_motions
```

## 三、运行底层示例

!!! note "需要 DDS 环境"
    运行底层示例前确保设置了 `CYCLONEDDS_URI` 环境变量。

```bash
export CYCLONEDDS_URI=file://$(pwd)/cyclonedds.xml
cd low_level/python
python3 e4_imu_state_sub.py
```

### 【重要】关闭机器人主控程序

在使用底层电机控制 (E9) 前，**必须**先停止机器人的主控程序：

```bash
# Python
cd high_level/python
python3 examples/kill_robot.py 192.168.5.2:50051

# C++
cd high_level/cpp/build
./kill_robot 192.168.5.2:50051
```

执行流程：切换到 PASSIVE 状态 → 等待 5 秒 → 终止控制器进程。

!!! warning "重要提示"
    底层电机控制 (E9) 前必须执行。请确保机器人处于安全位置。

## 下一步

- [高层 API 参考](../api/high_level.md) - 学习高层 API
- [底层 API 参考](../api/low_level.md) - 学习底层 API
