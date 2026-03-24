# 高层 API 文档

[English](high_level_api.md) · [简体中文](high_level_api.zh-CN.md)

本文档详细介绍 Dobot Quad SDK 的高层（gRPC）API，包括各示例程序的功能、原理和使用方法。

---

## 目录

- [概述](#概述)
- [状态机简介](#状态机简介)
- [速度比与速度系统](#速度比与速度系统)
- [避障系统](#避障系统)
- [Kill Robot 工具](#kill-robot-工具)
- [示例程序详解](#示例程序详解)
  - [E1: 获取可用动作](#e1-获取可用动作)
  - [E2: 获取当前状态](#e2-获取当前状态)
  - [E3: 自动状态切换](#e3-自动状态切换)
  - [E4: 速度序列控制](#e4-速度序列控制)
  - [E5: 机器人状态查询](#e5-机器人状态查询)
  - [E6: 平衡动作控制](#e6-平衡动作控制)
  - [E7: 直线行走](#e7-直线行走)
  - [E8: 原地旋转](#e8-原地旋转)
  - [E9: 组合序列](#e9-组合序列)
  - [E10: 速度比与避障配置](#e10-速度比与避障配置)
- [RPC 接口参考](#rpc-接口参考)
- [常见问题](#常见问题)

---

## 概述

高层基于 gRPC 协议实现，提供以下核心功能：

- **状态机管理**：控制机器人在不同运动状态之间的切换
- **运动规划**：执行预定义的运动序列，支持实时进度流式推送
- **状态查询**：实时获取机器人的各项状态数据（关节、机身、FSM 状态）
- **参数配置**：动态调整速度比（Speed Ratio）和避障模式
- **速度控制**：使用物理单位（m/s、rad/s）直接指定速度指令

### 连接方式

默认 gRPC 服务地址为 `192.168.5.2:50051`（机器人主机端口）。

```python
import grpc
from dobot_quad.proto import grpc_service_pb2_grpc

channel = grpc.insecure_channel("192.168.5.2:50051")
stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
```

### 客户端库

提供两种即用的客户端库：

| 语言 | 文件 | 类名 |
|------|------|------|
| Python | `high_level/python/dobot_quad/robot_client.py` | `RobotClient` |
| C++ | `high_level/cpp/robot_client.h` | `robot::Client` |

两者均封装了所有 RPC 调用，内置进度显示、错误处理和 Ctrl+C 取消支持。

其中 Python 在 `high_level/python` 目录下执行 `pip install .` 即可安装 `dobot_quad` 包并自动生成 gRPC 绑定。示例代码位于 `examples/` 子目录。

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

## 速度比与速度系统

### 速度比 (Speed Ratio)

**速度比**控制机器人的整体速度缩放。可通过 `SetSpeedRatio` RPC 接口进行设置。

| 属性 | 值 |
|------|------|
| 范围 | 10 – 100 |
| 步长 | 10 |
| 默认值 | 50 |

设置为 0 时，RPC 仅返回当前值而不修改（查询模式）。

速度比影响速度管线中的**实际速度缩放系数**：

```
realSpeedScale = (1 - k_lower) × speedRatio / 100 + k_lower
```

其中 `k_lower` 是最低速度分数（因步态不同而异，见下表）。

### 步态速度上限

每种步态有各自的速度限制。最大可达速度取决于步态上限和当前速度比：

```
v_max = bound × realSpeedScale
```

| 步态 | 方向 | 上限 | k_lower | 最大值 @ ratio=50 | 最大值 @ ratio=100 |
|------|------|------|---------|------------------|-------------------|
| **WALK** | vx（前进） | 1.2 m/s | 0.4 | 0.84 m/s | 1.20 m/s |
| | vx（后退） | 0.8 m/s | 0.4 | 0.56 m/s | 0.80 m/s |
| | vy（横移） | 0.45 m/s | 0.4 | 0.315 m/s | 0.45 m/s |
| | vyaw（转向） | 1.8 rad/s | 0.4 | 1.26 rad/s | 1.80 rad/s |
| **FLYING_TROT** | vx（前进） | 2.0 m/s | 0.2 | 1.20 m/s | 2.00 m/s |
| | vx（后退） | 1.0 m/s | 0.2 | 0.60 m/s | 1.00 m/s |
| | vy（横移） | 0.55 m/s | 0.2 | 0.33 m/s | 0.55 m/s |
| | vyaw（转向） | 1.4 rad/s | 0.2 | 0.84 rad/s | 1.40 rad/s |
| **RL** | vx（前进） | 0.8 m/s | 0.3 | 0.52 m/s | 0.80 m/s |
| | vx（后退） | 0.6 m/s | 0.3 | 0.39 m/s | 0.60 m/s |
| | vy（横移） | 0.45 m/s | 0.3 | 0.293 m/s | 0.45 m/s |
| | vyaw（转向） | 1.2 rad/s | 0.3 | 0.78 rad/s | 1.20 rad/s |

> **注意**：当请求速度超过可达最大值时，内部会被钳位到上限。为获得最佳效果，请将速度值控制在 "最大值 @ ratio=N" 范围内。

### 设置速度比

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# 查询当前速度比（返回本地跟踪值）
current = robot.get_speed_ratio()
print(f"当前速度比: {current}")

# 设置速度比为 80
robot.set_speed_ratio(80)
```

```cpp
robot::Client client("192.168.5.2:50051");

// 查询当前速度比（返回本地跟踪值）
int current = client.get_speed_ratio();
std::cout << "当前: " << current << std::endl;

// 设置速度比为 80
client.set_speed_ratio(80);
```

> **注意：** `get_speed_ratio()` 和 `get_obstacle_avoidance()` 返回本地跟踪的值（从 `set_*()` RPC 响应中更新），而非每次都查询服务端。这避免了最终一致性 `GetRobotState` RPC 的过期读取问题。

---

## 避障系统

机器人内置避障系统，通过传感器检测障碍物并修改速度指令以防止碰撞。启用后，如果检测到前方有障碍物，避障系统可能会**将前进速度 (vx) 置零**。

> **重要提示**：避障主要影响前进方向 (vx)。横移速度 (vy) 和旋转速度 (vyaw) 不受避障系统影响。

### 开启/关闭避障

使用 `SetObstacleAvoidance` RPC 接口切换避障系统：

```python
robot = RobotClient("192.168.5.2:50051")

# 关闭避障
robot.set_obstacle_avoidance(False)

# 开启避障
robot.set_obstacle_avoidance(True)
```

```cpp
robot::Client client("192.168.5.2:50051");

// 关闭避障
client.set_obstacle_avoidance(false);

// 开启避障
client.set_obstacle_avoidance(true);
```

> **提示**：如果发现机器人无法前进，但横移和转向正常，很可能是避障系统阻断了 vx。可以尝试关闭避障进行测试。

---

## Kill Robot 工具

**文件**: `high_level/python/examples/kill_robot.py` / `high_level/cpp/kill_robot.cpp`

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
python3 examples/kill_robot.py [服务器地址:端口]

# 示例
python3 examples/kill_robot.py 192.168.5.2:50051
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

### 重要说明

- **使用场景**：在使用底层电机控制（low_level E9）或 LED 控制（low_level E3）前必须执行
- **安全提示**：执行前请确保机器人处于安全位置（平坦地面，远离障碍物），避免因突然失能造成跌倒

---

## 示例程序详解

### E1: 获取可用动作

**文件**: `high_level/python/examples/e1_get_available_motions.py` / `high_level/cpp/e1_get_available_motions.cpp`

#### 功能说明

查询机器人支持的所有动作（Motion）及其参数。这是了解机器人能力的第一步，可以获取：

- 动作 ID 列表
- 每个动作的描述
- 每个动作支持的参数及默认值

#### 原理

通过 `GetAvailableMotions` RPC 调用，服务端返回 `MotionLibrary` 中注册的所有动作信息。

#### 运行方式

```bash
# Python
cd high_level/python
python3 examples/e1_get_available_motions.py [服务器地址]

# C++
cd high_level/cpp/build
./e1_get_available_motions [服务器地址]
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

  [walk_velocity_seq]
    Description: Walk with velocity sequence control
    Parameters (default values):
      - velocity_sequence: "" (string)

  [balance_pitch]
    Description: Control robot pitch angle in balance stand
    Parameters (default values):
      - value: 0.0 (float)
      - duration: 2.0 (float)
      - mode: "dynamic" (string)

  ......
```

#### 动作参数说明

| 动作类型 | 动作 ID | 参数 | 说明 |
|----------|---------|------|------|
| 状态切换 | `passive`, `stand_down`, `stand_up`, `balance_stand` 等 | 无 | 单次状态转换 |
| 自动寻路 | `path_to_state` | `target_state` | 自动导航到目标状态 |
| 速度序列 | `walk_velocity_seq`, `flying_trot_velocity_seq` | `velocity_sequence` | 使用 m/s 和 rad/s 控制速度（详见 E4） |
| 平衡动作 | `balance_pitch`, `balance_yaw`, `balance_roll`, `balance_height`, `balance_neutral` | `value`, `duration`, `mode` | 在 BALANCE_STAND 状态下的姿态控制（详见 E6） |
| 直线行走 | `line_walk` | `direction`, `distance` | 按指定距离直线行走（详见 E7） |
| 原地旋转 | `rotation` | `direction`, `angle` | 按指定角度原地旋转（详见 E8） |
| 特殊指令 | `kill_robot` | 无 | 安全关闭控制器 |

---

### E2: 获取当前状态

**文件**: `high_level/python/examples/e2_get_current_state.py` / `high_level/cpp/e2_get_current_state.cpp`

#### 功能说明

查询机器人当前的 FSM 状态和基本遥测数据。在发送指令前，可以用来确认机器人当前处于什么模式。

#### 原理

通过 `GetRobotState` RPC 调用，返回当前 FSM 状态名称和传感器数据。

#### 运行方式

```bash
# Python
cd high_level/python
python3 examples/e2_get_current_state.py [服务器地址]

# C++
cd high_level/cpp/build
./e2_get_current_state [服务器地址]
```

#### 输出示例

```
Connected to server: 192.168.5.2:50051

Current state: STAND_DOWN
```

---

### E3: 自动状态切换

**文件**: `high_level/python/examples/e3_auto_state_switch.py` / `high_level/cpp/e3_auto_state_switch.cpp`

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
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# 从任意状态导航到 BALANCE_STAND
robot.execute("balance_stand")

# 导航到 WALK
robot.execute(("path_to_state", {"target_state": "WALK"}))
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
# Python（交互式菜单）
cd high_level/python
python3 examples/e3_auto_state_switch.py [服务器地址]

# C++
cd high_level/cpp/build
./e3_auto_state_switch [服务器地址]
```

程序会提供交互式菜单让您选择目标状态。

---

### E4: 速度序列控制

**文件**: `high_level/python/examples/e4_velocity_sequence.py` / `high_level/cpp/e4_velocity_sequence.cpp`

#### 功能说明

在 `WALK` 或 `FLYING_TROT` 状态下，通过速度序列控制机器人的运动轨迹。速度使用**物理单位**（m/s 和 rad/s）指定，内部会根据步态速度上限和当前速度比自动转换为控制器指令。

#### 动作 ID

| 动作 ID | 目标步态 |
|---------|----------|
| `walk_velocity_seq` | WALK |
| `flying_trot_velocity_seq` | FLYING_TROT |

每个动作会自动切换到所需的步态状态后再执行速度序列。

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

| 方向 | 条件 | 说明 |
|------|------|------|
| 前进 | vx > 0 | 向前移动 |
| 后退 | vx < 0 | 向后移动 |
| 左平移 | vy > 0 | 向左横移 |
| 右平移 | vy < 0 | 向右横移 |
| 左转 (逆时针) | vyaw > 0 | 逆时针旋转 |
| 右转 (顺时针) | vyaw < 0 | 顺时针旋转 |

#### 建议速度范围

详细的各步态最大速度请参见"步态速度上限"章节。以下是默认速度比 (50) 下的常用安全值：

| 步态 | vx | vy | vyaw |
|------|----|----|------|
| WALK | +/-0.5 m/s | +/-0.2 m/s | +/-0.8 rad/s |
| FLYING_TROT | +/-0.8 m/s | +/-0.3 m/s | +/-0.6 rad/s |

#### 示例代码

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# 步行演示：前进、后退、横移、转向
robot.execute(
    (
        "walk_velocity_seq",
        {
            "velocity_sequence":
            "0.5,0.0,0.0,2.0;"   # 前进 0.5 m/s 持续 2 秒
            "0.0,0.0,0.0,1.0;"   # 停止 1 秒
            "-0.4,0.0,0.0,2.0;"  # 后退 0.4 m/s 持续 2 秒
            "0.0,0.0,0.0,1.0;"   # 停止
            "0.0,0.2,0.0,2.0;"   # 左平移 0.2 m/s
            "0.0,0.0,0.0,1.0;"   # 停止
            "0.0,-0.2,0.0,2.0;"  # 右平移 0.2 m/s
            "0.0,0.0,0.0,1.0;"   # 停止
            "0.0,0.0,0.5,2.0;"   # 左转 0.5 rad/s
            "0.0,0.0,0.0,1.0;"   # 停止
            "0.0,0.0,-0.5,2.0;"  # 右转 0.5 rad/s
            "0.0,0.0,0.0,1.0;"   # 停止
        },
    ),
    "stand_down",
)
```

```python
# 飞步小跑演示：更快的速度
robot.execute(
    (
        "flying_trot_velocity_seq",
        {
            "velocity_sequence":
            "0.8,0.0,0.0,2.0;"  # 冲刺前进 0.8 m/s
            "0.0,0.0,0.0,1.0;"  # 停止
            "0.0,0.0,0.6,2.0;"  # 左转 0.6 rad/s
            "0.0,0.0,0.0,1.0;"  # 停止
        },
    ),
    "stand_down",
)
```

#### 运行方式

```bash
# Python（1=步行演示, 2=飞步小跑演示）
cd high_level/python
python3 examples/e4_velocity_sequence.py [服务器地址] [1|2]

# C++
cd high_level/cpp/build
./e4_velocity_sequence [服务器地址] [1|2]
```

#### 进度流式推送

执行过程中，服务端会流式推送实时进度更新。对于速度序列，消息中包含当前段索引和速度值：

```
Running... (Ctrl+C to stop)
  [1/2] walk_velocity_seq | state: WALK (VelSeg 1/12: vx=0.50 vy=0.00 vyaw=0.00)
  [1/2] walk_velocity_seq | state: WALK (VelSeg 2/12: vx=0.00 vy=0.00 vyaw=0.00)
  ...
  [1/2] walk_velocity_seq | state: WALK (VelSeg 12/12: vx=0.00 vy=0.00 vyaw=0.00)
Done.
```

---

### E5: 机器人状态查询

**文件**: `high_level/python/examples/e5_robot_state.py` / `high_level/cpp/e5_robot_state.cpp`

#### 功能说明

实时获取机器人的各项状态数据，包括：

- 关节位置、速度、力矩（实际值和期望值）
- 机身位置、速度、加速度、姿态、角速度
- 接触力信息
- 电池电压
- 当前 FSM 状态名称

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
| 机身状态 | `pos_body`（暂未开放） | m | 机身位置 [x, y, z] |
| | `vel_body`（暂未开放） | m/s | 机身速度 [vx, vy, vz] |
| | `acc_body` | m/s2 | 机身加速度 [ax, ay, az] |
| | `ori_body` | rad | 机身姿态 [roll, pitch, yaw] |
| | `omega_body` | rad/s | 机身角速度 |
| 接触力（原始） | `grf_left`（暂未开放） | N | 左侧足端力 [fx, fy, fz] |
| | `grf_right`（暂未开放） | N | 右侧足端力 [fx, fy, fz] |
| 接触力统计 | `temp[0]` | N | 左脚总接触力 |
| | `temp[1]` | N | 右脚总接触力 |
| | `temp[2]` | N | 双脚总接触力 |
| | `temp[3]` | N | X方向总地面反力 |
| 电源状态 | `temp[8]` | V | 电池1电压 |
| | `temp[9]` | V | 电池2电压 |
| FSM 状态 | `current_state` | -- | 当前 FSM 状态名（如 "WALK"） |

> **注意**：`temp[4]` 至 `temp[7]` 为保留字段，当前未使用。

#### 运行方式

```bash
# Python
cd high_level/python
python3 examples/e5_robot_state.py [服务器地址]

# C++
cd high_level/cpp/build
./e5_robot_state [服务器地址]
```

---

### E6: 平衡动作控制

**文件**: `high_level/python/examples/e6_balance_motions.py` / `high_level/cpp/e6_balance_motions.cpp`

#### 功能说明

在 `BALANCE_STAND` 状态下控制机器人的姿态，执行以下四种基本动作：

- **Pitch（俯仰）**：点头动作（抬头/低头）
- **Yaw（偏航）**：摇头动作（左转/右转）
- **Roll（横滚）**：左右摇摆（左倾/右倾）
- **Height（高度）**：蹲下/站高

#### 动作参数

| 参数 | 说明 | 范围 |
|------|------|------|
| `value` | 目标偏置值（rpy 为度，高度为米） | roll: `[-30, 30]`，pitch: `[-15, 15]`，yaw: `[-20, 20]`，height: `[-0.12, 0]` |
| `duration` | 动作时长（秒） | 单轴/批量平衡：`[0.5, 5]`；复合姿态（`dynamic_pose`/`static_pose`）：`[1, 5]` |
| `mode` | 动作模式 | `"dynamic"` / `"static"` |

#### 示例代码

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# 单轴接口
robot.balance_pitch(15.0, 2.0, "dynamic")
robot.balance_yaw(20.0, 2.0, "dynamic")
robot.balance_roll(-15.0, 2.0, "dynamic")
robot.balance_height(-0.05, 2.0, "dynamic")

# 批量接口
robot.balance_sequence([
  ("balance_pitch", 15.0, 2.0, "dynamic"),
  ("balance_yaw", 20.0, 2.0, "dynamic"),
  ("balance_roll", -15.0, 2.0, "dynamic"),
  ("balance_height", -0.05, 2.0, "dynamic"),
  ("balance_neutral", 0.0, 0.5, "dynamic"),
])

# 复合姿态接口
robot.dynamic_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
robot.static_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
robot.balance_neutral()
```

#### 运行方式

```bash
# Python
cd high_level/python
python3 examples/e6_balance_motions.py [服务器地址]

# C++
cd high_level/cpp/build
./e6_balance_motions [服务器地址]
```

---

### E7: 直线行走

**文件**: `high_level/python/examples/e7_line_walk.py` / `high_level/cpp/e7_line_walk.cpp`

#### 功能说明

控制机器人沿直线行走指定距离。机器人需处于 `BALANCE_STAND` 状态（或动作会自动导航到该状态）。系统会根据请求的距离自动计算合适的速度和持续时间。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `direction` | int | 0 | 方向：0=前进, 1=后退, 2=左平移, 3=右平移 |
| `distance` | float | 1.0 | 距离，单位米 |

#### 示例代码

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# 先直线行走，再 rotate_walk
robot.line_walk(0, 1.0)
robot.rotate_walk(angle=45, distance=1.0, speed_ratio=10)
```

#### 运行方式

```bash
# Python
cd high_level/python
python3 examples/e7_line_walk.py [服务器地址] [方向] [距离]

# 示例
python3 examples/e7_line_walk.py 192.168.5.2:50051 0 1.0

# C++
cd high_level/cpp/build
./e7_line_walk [服务器地址] [方向] [距离]
```

---

### E8: 原地旋转

**文件**: `high_level/python/examples/e8_rotation.py` / `high_level/cpp/e8_rotation.cpp`

#### 功能说明

控制机器人原地旋转指定角度。机器人需处于 `BALANCE_STAND` 状态（或动作会自动导航到该状态）。系统会自动计算合适的角速度和持续时间。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `direction` | int | 0 | 方向：0=左转/逆时针, 1=右转/顺时针 |
| `angle` | float | 90.0 | 旋转角度，单位度 |

#### 示例代码

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# 当前示例脚本中的演示
# robot.rotate(direction, angle)
robot.circle(direction="right", turns=3)
```

#### 运行方式

```bash
# Python
cd high_level/python
python3 examples/e8_rotation.py [服务器地址] [方向] [角度]

# 示例
python3 examples/e8_rotation.py 192.168.5.2:50051 0 90

# C++
cd high_level/cpp/build
./e8_rotation [服务器地址] [方向] [角度]
```

---

### E9: 组合序列

**文件**: `high_level/python/examples/e9_combo_sequence.py` / `high_level/cpp/e9_combo_sequence.cpp`

#### 功能说明

演示 Arduino 风格的阻塞式组合流程，依次调用高层接口执行：

- 状态切换（`passive`、`ready`、`balance_stand`、`walk`、`change_mode`）
- 前后左右 1 米移动与旋转动作
- 单轴平衡（`dynamic` / `static`）
- 复合姿态（`dynamic_pose`、`static_pose`）
- 基础动作状态（`wave`、`dance`、`recovery`、`stand_down`）

#### 运行方式

```bash
# Python
cd high_level/python
python3 examples/e9_combo_sequence.py [服务器地址]

# C++
cd high_level/cpp/build
./e9_combo_sequence [服务器地址]
```

---

### E10: 速度比与避障配置

**文件**: `high_level/python/examples/e10_config_demo.py` / `high_level/cpp/e10_config_demo.cpp`

#### 功能说明

演示如何查询和配置速度比和避障设置：

- **速度比**：使用 `get_speed_ratio()` 查询当前值，使用 `set_speed_ratio()` 设置持久基础值，使用行走函数的可选 `speed_ratio` 参数进行临时覆盖。
- **避障**：使用 `set_obstacle_avoidance()` 开关，使用 `get_obstacle_avoidance()` 查询。

#### 核心概念

- `get_speed_ratio()` 返回**本地跟踪**的值（从 `set_speed_ratio()` RPC 响应中更新），不会每次查询服务端。
- 当 `walk_forward(dist, speed_ratio=N)` 显式指定 `speed_ratio` 时，值会被临时应用并在执行后恢复。省略时使用当前基础速度比。
- `get_obstacle_avoidance()` 同样返回本地跟踪的状态。

#### 示例代码

```python
from dobot_quad import RobotClient

robot = RobotClient("192.168.5.2:50051")

# 查询当前速度比
print(f"速度比: {robot.get_speed_ratio()}")

# 设置基础速度比为 10（慢速）
robot.set_speed_ratio(10)
robot.walk_forward(1.0)              # 使用基础速度比 (10)

# 临时覆盖：以 speed_ratio=100 行走，然后恢复为 10
robot.walk_forward(1.0, speed_ratio=100)
print(f"执行后速度比: {robot.get_speed_ratio()}")  # 仍为 10

# 切换避障
robot.set_obstacle_avoidance(False)  # 或 "off"
print(f"OA 已启用: {robot.get_obstacle_avoidance()}")  # False
robot.set_obstacle_avoidance(True)   # 或 "on"
print(f"OA 已启用: {robot.get_obstacle_avoidance()}")  # True
```

#### 运行方式

```bash
# Python
cd high_level/python
python3 examples/e10_config_demo.py [服务器地址]

# C++
cd high_level/cpp/build
./e10_config_demo [服务器地址]
```

---

## RPC 接口参考

### 服务: gRPCService

| RPC 接口 | 请求 | 响应 | 类型 | 说明 |
|----------|------|------|------|------|
| `GetAvailableMotions` | `GetMotionsRequest` | `GetMotionsResponse` | 一元调用 | 列出所有可用动作及参数 |
| `ExecuteSequence` | `ExecuteSequenceRequest` | stream `SequenceProgress` | 服务端流式 | 执行动作序列，实时推送进度 |
| `GetRobotState` | `GetRobotStateRequest` | `GetRobotStateResponse` | 一元调用 | 获取机器人状态（关节、机身、FSM状态） |
| `SetSpeedRatio` | `SetSpeedRatioRequest` | `SetSpeedRatioResponse` | 一元调用 | 设置/查询速度比 [10-100] |
| `SetObstacleAvoidance` | `SetObstacleAvoidanceRequest` | `SetObstacleAvoidanceResponse` | 一元调用 | 开启/关闭避障 |
| `GetSensorList` | `GetSensorListRequest` | `GetSensorListResponse` | 一元调用 | 列出可用传感器 |
| `GetLidarData` | `GetLidarDataRequest` | `GetLidarDataResponse` | 一元调用 | 获取单次激光雷达扫描 |
| `StreamLidarData` | `GetLidarDataRequest` | stream `GetLidarDataResponse` | 服务端流式 | 流式获取激光雷达数据 |
| `GetCameraData` | `GetCameraDataRequest` | `GetCameraDataResponse` | 一元调用 | 获取单张相机图像 |
| `StreamCameraData` | `GetCameraDataRequest` | stream `GetCameraDataResponse` | 服务端流式 | 流式获取相机图像 |
| `GetDepthData` | `GetDepthDataRequest` | `GetDepthDataResponse` | 一元调用 | 获取深度相机数据 |

### SetSpeedRatio

```
SetSpeedRatioRequest {
  int32 speed_ratio = 1;  // [10-100]，步长 10。传 0 仅查询不修改。
}

SetSpeedRatioResponse {
  bool success = 1;
  string message = 2;
  int32 current_speed_ratio = 3;  // 操作后的当前值
}
```

### SetObstacleAvoidance

```
SetObstacleAvoidanceRequest {
  bool enable = 1;  // true = 开启, false = 关闭
}

SetObstacleAvoidanceResponse {
  bool success = 1;
  string message = 2;
  bool current_enabled = 3;  // 操作后的当前状态
}
```

---

## 常见问题

### Q: 如何中断正在执行的动作序列？

按 `Ctrl+C` 可以取消当前执行的序列。客户端库会处理优雅取消。

### Q: 状态切换失败怎么办？

1. 检查当前状态是否支持目标转换
2. 使用 `path_to_state` 自动寻路（推荐）
3. 确保机器人处于安全位置

### Q: 为什么机器人无法前进？

通常是避障系统阻断了前进速度 (vx) 导致的。可以尝试：
1. 关闭避障：`robot.set_obstacle_avoidance(False)`
2. 确保机器人前方没有障碍物
3. 注意横移 (vy) 和转向 (vyaw) 不受避障影响

### Q: 如何让机器人走得更快或更慢？

调整速度比：`robot.set_speed_ratio(80)` 加速，`robot.set_speed_ratio(30)` 减速。默认值为 50。详细的各速度比下最大速度请参见"步态速度上限"表格。

### Q: E4 速度序列与 E7/E8 有什么区别？

- **E4**（`walk_velocity_seq` 等）：完全控制速度曲线。您为每个段指定精确的速度和持续时间。
- **E7**（`line_walk`）：简化的基于距离的接口。指定方向和距离，系统自动计算速度和时间。
- **E8**（`rotation`）：简化的基于角度的接口。指定方向和角度，系统自动计算角速度和时间。

### Q: `set_speed_ratio` 和行走函数中的 `speed_ratio` 参数有什么区别？

- `set_speed_ratio(N)`：持久设置**基础**速度比。后续所有操作都使用此值。
- `walk_forward(dist, speed_ratio=N)`：仅为单次操作**临时**覆盖速度比，执行后恢复基础值。若省略 `speed_ratio`（默认 `None`/`-1`），则使用当前基础值无覆盖。

---

## 返回

[← 返回 README](../README.zh-CN.md)
