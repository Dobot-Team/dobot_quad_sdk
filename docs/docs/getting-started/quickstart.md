# Quick Start

This guide will help you run your first Dobot Quad SDK example program.

## 1. Prerequisites

Make sure you have completed the [Installation](installation.md) guide.

## 2. Running High-Level Examples

### Python

```bash
# High-level (Python)
cd high_level/python
python3 examples/e1_get_available_motions.py
python3 examples/e3_auto_state_switch.py
```

### C++

```bash
# High-level (C++)
cd high_level/cpp/build
./e1_get_available_motions
```

## 3. Running Low-Level Examples

!!! note "DDS Environment Required"
    Make sure `CYCLONEDDS_URI` environment variable is set before running low-level examples.

```bash
cd low_level/python
python3 e4_imu_state_sub.py
```

### [Important] Shutdown Robot Controller

Before using low-level motor control (E9), you **must** stop the robot's main control program:

```bash
# Python
cd high_level/python
python3 examples/kill_robot.py 192.168.5.2:50051

# C++
cd high_level/cpp/build
./kill_robot 192.168.5.2:50051
```

This will: switch to PASSIVE state → wait 5 s → terminate controller processes.

!!! warning "Important"
    Required before low-level motor control (E9). Ensure the robot is in a safe position first.

## Next Steps

- [High-Level API](../api/high_level.md) - Explore high-level examples
- [Low-Level API](../api/low_level.md) - Explore low-level examples
