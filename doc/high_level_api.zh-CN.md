# 高级控制层 API 文档

[English](high_level_api.md) · [简体中文](high_level_api.zh-CN.md)

本文档详细介绍 Dobot Quad SDK 的高级控制层（gRPC）API，包括各示例程序的功能、原理和使用方法。

---

## 目录

- [概述](#概述)
- [状态机简介](#状态机简介)
- [Kill Robot 工具](#kill-robot-工具)
- [示例程序详解](#示例程序详解)
  - [E1: 获取可用动作](#e1-获取可用动作)
  - [E2: 手动状态切换](#e2-手动状态切换)
  - [E3: 自动状态切换](#e3-自动状态切换)
  - [E4: 速度序列控制](#e4-速度序列控制)
  - [E5: 机器人状态查询](#e5-机器人状态查询)
  - [E6: 平衡动作控制](#e6-平衡动作控制)

---

## 概述

高级控制层基于 gRPC 协议实现，提供以下核心功能：

- **状态机管理**：控制机器人在不同运动状态之间的切换
- **运动规划**：执行预定义的运动序列
- **状态查询**：实时获取机器人的各项状态数据
- **参数配置**：动态调整运动参数

### 连接方式

默认 gRPC 服务地址为 `192.168.5.2:50051`（机器人主机端口）。

```python
import grpc
from proto import grpc_service_pb2_grpc

channel = grpc.insecure_channel("192.168.5.2:50051")
stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
```

---

## 状态机简介

机器人采用有限状态机（FSM）管理运动状态。主要状态包括：

| 状态名称 | 说明 |
|----------|------|
| `PASSIVE` | 被动模式，电机失能 |
| `STAND_DOWN` | 趴下状态 |
| `STAND_UP` | 站立状态 |
| `BALANCE_STAND` | 平衡站立，支持姿态调整 |
| `WALK` | 步行模式 |
| `FLYING_TROT` | 飞步小跑（跑步步态） |
| `RL` | 强化学习控制模式 |
| `WAVE` | 挥手动作 |
| `DANCE0` | 舞蹈动作 |
| `JUMP` | 跳跃动作 |
| `BACKFLIP` | 后空翻动作 |

### 状态转换规则

状态机有严格的转换规则，不能从任意状态直接跳转到任意状态。例如：

- `PASSIVE` → `STAND_DOWN` → `STAND_UP` → `BALANCE_STAND`
- `BALANCE_STAND` → `WALK` / `FLYING_TROT` / `RL`

使用 `path_to_state` 动作可以自动寻找转换路径。

---

## 示例程序详解

### E1: 获取可用动作

**文件**: `high_level/python/e1_get_available_motions.py`

#### 功能说明

查询机器人支持的所有动作（Motion）及其参数。这是了解机器人能力的第一步，可以获取：

- 动作 ID 列表
- 每个动作的描述
- 每个动作支持的参数及默认值

#### 原理

通过 `GetAvailableMotions` RPC 调用，服务端返回 `MotionLibrary` 中注册的所有动作信息。

#### 运行方式

```bash
cd high_level/python
python3 e1_get_available_motions.py [server_address]

# 示例
python3 e1_get_available_motions.py 192.168.5.2:50051
```

#### 输出示例

```
Connected to server: 192.168.5.2:50051
Example 1: Get Available Motions
Successfully retrieved motion list
Found 15 motions:

  [passive]
    Description: Trigger FSM to PASSIVE once

  [stand_up]
    Description: Trigger FSM to STAND_UP once

  [walk]
    Description: Trigger FSM to WALK with velocity sequence support
    Parameters (default values):
      - velocity_sequence: "" (string)

  [balance_pitch]
    Description: Control robot pitch angle in balance stand with sinusoidal motion
    Parameters (default values):
      - beats: 1.0 (float)
      - amplitude: 1.0 (float)

  ......
```

#### 动作参数说明

| 动作类型 | 参数 | 说明 |
|----------|------|------|
| 状态切换动作 | 无参数 | `passive`, `stand_down`, `stand_up`, `balance_stand` 等 |
| 行走动作 | `velocity_sequence` | 速度序列字符串，格式见 E4 |
| 平衡动作 | `beats`, `amplitude` | 节拍数和幅度 |
| 自动寻路 | `target_state` | 目标状态名称 |

---

### E2: 手动状态切换

**文件**: `high_level/python/e2_direct_state_switch.py`

#### 功能说明

手动按照状态机规则切换机器人状态。用户需要知道当前状态下可以切换到哪些状态，并按顺序指定切换路径。

#### 与自动切换的区别

| 特性 | 手动切换 (E2) | 自动切换 (E3) |
|------|---------------|---------------|
| 路径规划 | 用户手动指定 | 系统自动寻路 |
| 适用场景 | 精确控制切换过程 | 快速到达目标状态 |
| 错误处理 | 错误路径会失败 | 自动找到可行路径 |

#### 原理

将多个状态切换动作组成 `MotionSequence`，按顺序执行。每个动作触发一次状态转换。

#### 示例代码

```python
# 创建动作序列
sequence = grpc_service_pb2.MotionSequence(
    sequence_id="demo_state_switch",
    sequence_name="Direct State Switch Demo",
    loop=False
)

# 按顺序添加状态切换动作
motion_ids = ["passive", "stand_down", "stand_up", "balance_stand"]
for motion_id in motion_ids:
    motion = sequence.motions.add()
    motion.motion_id = motion_id

# 执行序列
request = grpc_service_pb2.ExecuteSequenceRequest(
    sequence=sequence,
    immediate_start=True
)
response = stub.ExecuteSequence(request)
```

#### 运行方式

```bash
cd high_level/python
python3 e2_direct_state_switch.py [server_address]
```

#### 输出示例

```
✓ Connected to server: 192.168.5.2:50051
example 2: Direct State Switching Demo
STAND_DOWN -> STAND_UP -> BALANCE_STAND -> DANCE0

Sequence is running... Press Ctrl+C to stop.

State switching demo executed successfully
  Execution ID: exec_12345
  Message: Sequence completed
  Number of motions: 5
```

---

### E3: 自动状态切换

**文件**: `high_level/python/e3_auto_state_switch.py`

#### 功能说明

自动寻路到目标状态。无论机器人当前处于什么状态，系统会自动计算最短路径并执行状态切换。

#### 原理

使用 `path_to_state` 动作，内部调用 `StateRoute` 组件进行路径规划：

1. 获取当前状态
2. 计算到目标状态的最短路径
3. 依次执行路径上的状态转换
4. 等待每个状态稳定后再进行下一步

#### 示例代码

```python
sequence = grpc_service_pb2.MotionSequence(
    sequence_id="path_to_state",
    sequence_name="Auto State Switch Demo",
    loop=False
)

# 使用 path_to_state 动作
motion = sequence.motions.add()
motion.motion_id = "path_to_state"
motion.parameters.add(key="target_state", string_value="BALANCE_STAND")

request = grpc_service_pb2.ExecuteSequenceRequest(
    sequence=sequence,
    immediate_start=True
)
```

#### 支持的目标状态

```python
state_list = [
    "PASSIVE",
    "STAND_DOWN",
    "STAND_UP",
    "BALANCE_STAND",
    "WALK",
    "RL",
    "FLYING_TROT",
    "WAVE",
    "DANCE0",
    "BACK_FLIP",
    "JUMP",
]
```

#### 运行方式

```bash
cd high_level/python
python3 e3_auto_state_switch.py [server_address]
```

程序会提供交互式菜单让您选择目标状态。

---

### E4: 速度序列控制

**文件**: `high_level/python/e4_velocity_sequence.py`

#### 功能说明

在 `WALK` 或 `FLYING_TROT` 状态下，通过速度序列控制机器人的运动轨迹。

#### 速度序列格式

```
"vx,vy,vyaw,duration;vx,vy,vyaw,duration;..."
```

| 参数 | 单位 | 说明 |
|------|------|------|
| `vx` | m/s | X 方向线速度（前进/后退） |
| `vy` | m/s | Y 方向线速度（左移/右移） |
| `vyaw` | rad/s | 绕 Z 轴角速度（左转/右转） |
| `duration` | 秒 | 该速度指令的持续时间 |

#### 速度方向说明

- **vx > 0**：向前移动
- **vx < 0**：向后移动
- **vy > 0**：向左平移
- **vy < 0**：向右平移
- **vyaw > 0**：逆时针旋转（左转）
- **vyaw < 0**：顺时针旋转（右转）

#### 示例代码

```python
# 速度序列示例：原地旋转测试
velocity_sequence = (
    "0.0,0.0,0.2,2.5;"   # 原地右转 2.5 秒
    "0.0,0.0,-0.2,2.5;"  # 原地左转 2.5 秒
    "0.0,0.0,0.0,1.0"    # 停止 1 秒
)

# 创建动作序列
sequence = grpc_service_pb2.MotionSequence(
    sequence_id="demo_walk_velocity",
    sequence_name="Walk Velocity Demo",
    loop=False
)

# 先切换到 WALK 状态
motion1 = sequence.motions.add()
motion1.motion_id = "path_to_state"
motion1.parameters.add(key="target_state", string_value="WALK")

# 执行速度序列
motion2 = sequence.motions.add()
motion2.motion_id = "walk"  # 或 "flying_trot", "rl"
motion2.parameters.add(key="velocity_sequence", string_value=velocity_sequence)
```

#### 复杂运动示例

```python
# 前进、转弯、平移组合
velocity_sequence = (
    "0.0,0.5,0.0,2.0;"    # 前进 2 秒
    "0.0,0.5,0.3,2.0;"    # 前进 + 右转 2 秒
    "0.4,0.0,0.0,1.5;"    # 右平移 1.5 秒
    "0.0,-0.3,-0.3,2.0;"  # 后退 + 左转 2 秒
    "0.0,0.0,-0.5,1.5;"   # 原地左转 1.5 秒
    "0.0,0.0,0.0,1.0"     # 停止
)
```

#### 运行方式

```bash
cd high_level/python
python3 e4_velocity_sequence.py [server_address]
```

---

### E5: 机器人状态查询

**文件**: `high_level/python/e5_robot_state.py`

#### 功能说明

实时获取机器人的各项状态数据，包括：

- 关节位置、速度、力矩
- 机身位置和姿态
- 接触力信息
- 电池电压

#### 原理

通过 `GetRobotState` RPC 调用获取 `RobotState` 消息。

#### 输出数据说明

| 数据类别 | 字段 | 单位 | 说明 |
|----------|------|------|------|
| 腿部关节（实际值） | `jpos_leg` | rad | 关节实际位置（12个关节） |
| | `jvel_leg` | rad/s | 关节实际速度 |
| | `jtau_leg` | Nm | 关节实际力矩 |
| 腿部关节（期望值） | `jpos_leg_des` | rad | 关节期望位置 |
| | `jvel_leg_des` | rad/s | 关节期望速度 |
| | `jtau_leg_des` | Nm | 关节期望力矩 |
| 机身状态 | `pos_body（暂未开放）` | m | 机身位置 [x, y, z] |
| | `vel_body（暂未开放）` | m/s | 机身速度 [vx, vy, vz] |
| | `acc_body` | m/s² | 机身加速度 [ax, ay, az] |
| | `ori_body` | rad | 机身姿态 [roll, pitch, yaw] |
| | `omega_body` | rad/s | 机身角速度 [ωx, ωy, ωz] |
| 接触力（原始） | `grf_left（暂未公开）` | N | 左侧足端力 [fx, fy, fz] |
| | `grf_right（暂未公开）` | N | 右侧足端力 [fx, fy, fz] |
| 接触力（滤波） | `grf_vertical_filtered（暂未公开）` | N | 滤波后垂直接触力 [左脚, 右脚] |
| 接触力统计 | `temp[0]` | N | 左脚总接触力 |
| | `temp[1]` | N | 右脚总接触力 |
| | `temp[2]` | N | 双脚总接触力 |
| | `temp[3]` | N | X方向总地面反力 |
| 电源状态 | `temp[8]` | V | 电池1电压 |
| | `temp[9]` | V | 电池2电压 |

> **注意**：`temp[4]` 至 `temp[7]` 为保留字段，当前未使用。

#### 运行方式

```bash
cd high_level/python
python3 e5_robot_state.py [server_address]
```

#### 输出示例

```
Connected to server: 192.168.5.2:50051

Fetching robot state...

Robot state retrieved successfully
  Message: State retrieved

Robot State Data:

Leg Joints [rad] / [rad/s] / [Nm]:
  Positions [rad]: ['-0.05', '0.85', '-1.70', ...]
  Velocities [rad/s]: ['0.00', '0.01', '-0.02', ...]
  Torques [Nm]: ['0.12', '5.43', '-8.21', ...]

Body State:
  Position (x,y,z) [m]: ['0.00', '0.00', '0.32']
  Velocity [m/s]: ['0.00', '0.00', '0.00']
  Orientation (roll,pitch,yaw) [rad]: ['0.01', '-0.02', '0.00']

Contact Forces [N]:
  Left Foot [N]: ['0.00', '0.00', '45.23', '0.00', '0.00', '48.12']
  Right Foot [N]: ['0.00', '0.00', '44.89', '0.00', '0.00', '47.56']

Additional Data:
  Battery Voltage 1 [V]: 25.20
  Battery Voltage 2 [V]: 25.18
```

---

### E6: 平衡动作控制

**文件**: `high_level/python/e6_balance_motions.py`

#### 功能说明

在 `BALANCE_STAND` 状态下控制机器人的姿态，执行以下四种基本动作：

- **Pitch（俯仰）**：点头动作
- **Yaw（偏航）**：摇头动作
- **Roll（横滚）**：左右摇摆
- **Height（高度）**：蹲下/站高

#### 动作参数

| 参数 | 说明 | 范围 |
|------|------|------|
| `beats` | 动作持续的节拍数 | > 0 |
| `amplitude` | 动作幅度 | -1.0 ~ 1.0 |
| `bpm` | 每分钟节拍数（在序列级别设置） | > 0 |

#### 动作时间计算

```
实际持续时间 = beats × 60 / bpm
```

例如：`beats=1.0`, `bpm=120` → 持续时间 = 0.5 秒

#### 幅度说明

| 动作 | amplitude > 0 | amplitude < 0 |
|------|---------------|---------------|
| `balance_pitch` | 抬头 | 低头 |
| `balance_yaw` | 右转头 | 左转头 |
| `balance_roll` | 右倾 | 左倾 |
| `balance_height` | - | 蹲下（高度降低） |

> 注意：`balance_height` 的幅度通常使用负值（-1.0 ~ 0.0）

#### 示例代码

```python
sequence = grpc_service_pb2.MotionSequence(
    sequence_id="demo_balance_motions",
    sequence_name="Balance Motions Demo",
    bpm=120.0,  # 设置 BPM
    loop=False
)

# 先切换到 BALANCE_STAND 状态
motion = sequence.motions.add()
motion.motion_id = "path_to_state"
motion.parameters.add(key="target_state", string_value="BALANCE_STAND")

# 点头动作
motion = sequence.motions.add()
motion.motion_id = "balance_pitch"
motion.parameters.add(key="beats", float_value=1.0)
motion.parameters.add(key="amplitude", float_value=0.8)  # 抬头

motion = sequence.motions.add()
motion.motion_id = "balance_pitch"
motion.parameters.add(key="beats", float_value=1.0)
motion.parameters.add(key="amplitude", float_value=-0.8)  # 低头

# 摇头动作
motion = sequence.motions.add()
motion.motion_id = "balance_yaw"
motion.parameters.add(key="beats", float_value=1.0)
motion.parameters.add(key="amplitude", float_value=0.8)  # 右转

# 蹲下动作
motion = sequence.motions.add()
motion.motion_id = "balance_height"
motion.parameters.add(key="beats", float_value=2.0)
motion.parameters.add(key="amplitude", float_value=-0.8)  # 蹲下

# 回到中立位置
motion = sequence.motions.add()
motion.motion_id = "balance_neutral"
motion.parameters.add(key="beats", float_value=1.0)
```

#### 运行方式

```bash
cd high_level/python
python3 e6_balance_motions.py [server_address] [bpm]

# 示例：使用 120 BPM
python3 e6_balance_motions.py 192.168.5.2:50051 120
```

#### 输出示例

```
Connected to server: 192.168.5.2:50051

Example 6: Balance Motions Demo

Sequence is running... Press Ctrl+C to stop.

Balance motions demo executed successfully
  Execution ID: exec_67890
```
---
## Kill Robot 工具

**文件**: `high_level/python/kill_robot.py` / `high_level/cpp/kill_robot.cpp`

### 功能说明

`kill_robot` 是一个用于安全关闭机器人主控程序的实用工具。在使用某些底层控制功能（如直接电机控制、LED 控制）前，必须先使用此工具停止主控程序，以避免控制冲突和安全事故。

### 工作原理

该工具通过 gRPC 接口执行 `kill_robot` 运动指令，服务器端会按照以下步骤安全关闭：

1. **切换到 PASSIVE 状态**：将机器人切换到被动模式，电机失能
2. **等待 5 秒**：确保机器人已经安全停止，避免突然退出造成跌倒
3. **终止控制器进程**：杀死所有主控程序进程

### 使用方法

#### Python 版本

```bash
cd high_level/python
python3 kill_robot.py [服务器地址:端口]

# 示例
python3 kill_robot.py 192.168.5.2:50051
```

#### C++ 版本

```bash
cd high_level/cpp/build
./kill_robot [服务器地址:端口]

# 示例
./kill_robot 192.168.5.2:50051
```

默认服务器地址为 `192.168.5.2:50051`。

### 安全确认

执行时会要求用户确认：

```
Are you sure? (y/N):
```

只有输入 `y` 才会继续执行，避免误操作。

### 错误处理

由于 `kill_robot` 命令会关闭服务器进程，客户端可能会收到连接断开的错误（`StatusCode.UNAVAILABLE` 或 `Socket closed`）。这实际上表示命令已经成功执行，程序会将此情况视为成功并显示：

```
Kill robot command executed successfully (server shut down as expected).
```

### ⚠️ 重要说明

- **使用场景**：在使用底层电机控制（low_level E9）或 LED 控制（low_level E3）前必须执行
- **安全提示**：执行前请确保机器人处于安全位置（平坦地面，远离障碍物），避免因突然失能造成跌倒
- **恢复运行**：关闭后需要重新启动机器人的主控程序才能使用高级控制功能

---

## 常见问题

### Q: 如何中断正在执行的动作序列？

按 `Ctrl+C` 可以取消当前执行的序列。

### Q: 状态切换失败怎么办？

1. 检查当前状态是否支持目标转换
2. 使用 `path_to_state` 自动寻路
3. 确保机器人处于安全位置

---

## 返回

[← 返回 README](../README.zh-CN.md)
