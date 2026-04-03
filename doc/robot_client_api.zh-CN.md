# Robot Client 函数接口 API 参考

[English](robot_client_api.md) · [简体中文](robot_client_api.zh-CN.md)

高层机器人客户端库的公开接口参考文档：

| 语言   | 文件                                           | 类              |
| ------ | ---------------------------------------------- | --------------- |
| Python | `high_level/python/dobot_quad/robot_client.py` | `RobotClient`   |
| C++    | `high_level/cpp/robot_client.h`                | `robot::Client` |

> **范围：** 仅高层状态/动作控制（gRPC）。  
> **传输协议：** `grpc_service.proto`（`grpc_comm` 包）。

---

## 1. 构造函数 / 连接

|          | Python                                  | C++                                |
| -------- | --------------------------------------- | ---------------------------------- |
| **签名** | `RobotClient(addr="192.168.5.2:50051")` | `Client(addr="192.168.5.2:50051")` |
| **返回** | `RobotClient` 实例                      | `Client` 实例                      |

| 参数   | 类型                  | 默认值                | 说明                         |
| ------ | --------------------- | --------------------- | ---------------------------- |
| `addr` | `str` / `std::string` | `"192.168.5.2:50051"` | gRPC 服务地址（`host:port`） |

**构造时行为：**

1. 打开到 `addr` 的非加密 gRPC 通道。
2. 通过 `get_state()` 向服务端查询当前速度比并存储到本地。
3. 开启避障（`set_obstacle_avoidance(true)`）并将结果存储到本地。

**上下文管理器（仅 Python）：**

```python
with RobotClient("192.168.5.2:50051") as robot:
    robot.balance_stand()
# 退出时自动关闭通道
```

---

## 2. 查询接口

### 2.1 `get_state`

返回服务端机器人完整遥测状态快照。

|          | Python                  | C++                                |
| -------- | ----------------------- | ---------------------------------- |
| **签名** | `get_state()`           | `get_state()`                      |
| **返回** | `GetRobotStateResponse` | `grpc_comm::GetRobotStateResponse` |

**`GetRobotStateResponse` 字段：**

| 字段                         | 类型         | 说明                                    |
| ---------------------------- | ------------ | --------------------------------------- |
| `success`                    | `bool`       | RPC 是否成功                            |
| `message`                    | `string`     | 状态 / 错误信息                         |
| `robot_state`                | `RobotState` | 关节、机体、接触力遥测数据（见 §2.1.1） |
| `current_state`              | `string`     | 当前 FSM 状态名（如 `"balance_stand"`） |
| `current_speed_ratio`        | `int32`      | 当前速度比 `[10–100]`                   |
| `obstacle_avoidance_enabled` | `bool`       | 避障是否处于激活状态                    |

#### 2.1.1 `RobotState` 消息体

| 字段                    | 类型      | 长度                      | 说明                                 |
| ----------------------- | --------- | ------------------------- | ------------------------------------ |
| `jpos_leg`              | `float[]` | `num_leg × num_leg_joint` | 腿部关节位置（rad）                  |
| `jpos_leg_des`          | `float[]` | 同上                      | 腿部关节期望位置（rad）              |
| `jvel_leg`              | `float[]` | 同上                      | 腿部关节速度（rad/s）                |
| `jvel_leg_des`          | `float[]` | 同上                      | 腿部关节期望速度（rad/s）            |
| `jtau_leg`              | `float[]` | 同上                      | 腿部关节力矩（Nm）                   |
| `jtau_leg_des`          | `float[]` | 同上                      | 腿部关节期望力矩（Nm）               |
| `pos_body`              | `float[]` | 3                         | 机体位置 `[x, y, z]`（m）            |
| `vel_body`              | `float[]` | 3                         | 机体线速度（m/s）                    |
| `acc_body`              | `float[]` | 3                         | 机体线加速度（m/s²）                 |
| `omega_body`            | `float[]` | 3                         | 机体角速度（rad/s）                  |
| `ori_body`              | `float[]` | 3                         | 机体姿态 `[roll, pitch, yaw]`（rad） |
| `grf_left`              | `float[]` | 3                         | 左脚地面反力（N）                    |
| `grf_right`             | `float[]` | 3                         | 右脚地面反力（N）                    |
| `grf_vertical_filtered` | `float[]` | 2                         | 滤波后垂直接触力（N）                |
| `temp`                  | `float[]` | 4                         | `[0–3]`：脚接触力合力 & grf_x 总量   |

### 2.2 `get_motions`

返回服务端注册的动作库。

|          | Python               | C++                             |
| -------- | -------------------- | ------------------------------- |
| **签名** | `get_motions()`      | `get_motions()`                 |
| **返回** | `GetMotionsResponse` | `grpc_comm::GetMotionsResponse` |

**`GetMotionsResponse` 字段：**

| 字段           | 类型                  | 说明                           |
| -------------- | --------------------- | ------------------------------ |
| `motions`      | `Motion[]`            | 可用动作列表（含默认参数）     |
| `descriptions` | `map<string, string>` | `motion_id → description` 映射 |
| `success`      | `bool`                | RPC 是否成功                   |
| `message`      | `string`              | 状态 / 错误信息                |

### 2.3 `get_current_state_name`

便捷封装：仅返回 FSM 状态名字符串。

|          | Python                            | C++                                       |
| -------- | --------------------------------- | ----------------------------------------- |
| **签名** | `get_current_state_name() -> str` | `get_current_state_name() -> std::string` |
| **返回** | FSM 状态名；失败时返回 `""`       | 同左                                      |

### 2.4 `get_speed_ratio`

返回本地跟踪的速度比。该值在每次调用 `set_speed_ratio()` 时从 RPC 响应中更新。**不会**每次都向服务端查询，因为 `GetRobotState` 在 `SetSpeedRatio` RPC 之后可能返回过期值。

|          | Python                     | C++                        |
| -------- | -------------------------- | -------------------------- |
| **签名** | `get_speed_ratio() -> int` | `get_speed_ratio() -> int` |
| **返回** | 速度比 `[10–100]`          | 同左                       |

### 2.5 `get_obstacle_avoidance`

返回本地跟踪的避障状态。该值在每次调用 `set_obstacle_avoidance()` 时从 RPC 响应中更新。**不会**每次都向服务端查询。

|          | Python                             | C++                                |
| -------- | ---------------------------------- | ---------------------------------- |
| **签名** | `get_obstacle_avoidance() -> bool` | `get_obstacle_avoidance() -> bool` |
| **返回** | `True`/`true` 表示已启用           | 同左                               |

---

## 3. 配置接口

### 3.1 `set_speed_ratio`

设置机器人速度比。超出 `[10, 100]` 的值会被静默钳位。

|          | Python                        | C++                                |
| -------- | ----------------------------- | ---------------------------------- |
| **签名** | `set_speed_ratio(ratio: int)` | `set_speed_ratio(int ratio)`       |
| **返回** | `SetSpeedRatioResponse`       | `grpc_comm::SetSpeedRatioResponse` |

| 参数    | 类型  | 范围               | 说明     |
| ------- | ----- | ------------------ | -------- |
| `ratio` | `int` | `[10–100]`（钳位） | 速度比值 |

**`SetSpeedRatioResponse` 字段：**

| 字段                  | 类型     | 说明               |
| --------------------- | -------- | ------------------ |
| `success`             | `bool`   | RPC 是否成功       |
| `message`             | `string` | 状态信息           |
| `current_speed_ratio` | `int32`  | 调用后的实际速度比 |

### 3.2 `set_obstacle_avoidance`

启用或禁用避障。

> 服务端行为：客户端通过 RPC 切换避障时，现在也会触发语音提示
> （`avoid_obstacle_on.wav` / `avoid_obstacle_off.wav`），与手柄触发路径保持一致。

|          | Python                           | C++                                                 |
| -------- | -------------------------------- | --------------------------------------------------- |
| **签名** | `set_obstacle_avoidance(enable)` | `set_obstacle_avoidance(bool enable)`               |
| **重载** | —                                | `set_obstacle_avoidance(const std::string& enable)` |
| **返回** | `SetObstacleAvoidanceResponse`   | `grpc_comm::SetObstacleAvoidanceResponse`           |

| 参数     | 类型           | 合法值                         | 说明                             |
| -------- | -------------- | ------------------------------ | -------------------------------- |
| `enable` | `bool` / `str` | `True`/`False`、`"on"`/`"off"` | 启用或禁用；非法字符串将抛出错误 |

**`SetObstacleAvoidanceResponse` 字段：**

| 字段              | 类型     | 说明             |
| ----------------- | -------- | ---------------- |
| `success`         | `bool`   | RPC 是否成功     |
| `message`         | `string` | 状态信息         |
| `current_enabled` | `bool`   | 调用后的实际状态 |

---

## 4. 执行接口

### 4.1 `execute`

底层入口：向服务端发送动作序列并实时流式返回执行进度。

|          | Python                                              | C++                                                             |
| -------- | --------------------------------------------------- | --------------------------------------------------------------- |
| **签名** | `execute(*motions, loop=False, show_progress=True)` | `execute(ExecuteSequenceRequest& req, bool show_progress=true)` |
| **返回** | 最终 `SequenceProgress`，或 `None`（取消/RPC 失败） | `bool`（`true` = 成功）                                         |

**Python `motions` 参数格式：**

| 形式    | 示例                                               | 说明               |
| ------- | -------------------------------------------------- | ------------------ |
| `str`   | `"balance_stand"`                                  | 无参数的动作 ID    |
| `tuple` | `("line_walk", {"direction": 0, "distance": 3.0})` | 动作 ID + 参数字典 |

**通用运行时行为：**

- `show_progress=true` 时实时打印进度到 stdout。
- `Ctrl+C` 可优雅取消执行。
- 中断时自动向服务端发送 `TryCancel`。

**`SequenceProgress` 字段（流式传输）：**

| 字段                | 类型     | 说明                                 |
| ------------------- | -------- | ------------------------------------ |
| `current_index`     | `int32`  | 当前执行动作的零基索引               |
| `total_motions`     | `int32`  | 序列中动作总数                       |
| `current_motion_id` | `string` | 当前执行的动作 ID                    |
| `current_state`     | `string` | 当前 FSM 状态                        |
| `is_final`          | `bool`   | 最终进度消息时为 `true`              |
| `success`           | `bool`   | 整体执行结果（仅 `is_final` 时有效） |
| `message`           | `string` | 状态 / 错误信息                      |
| `execution_id`      | `string` | 唯一执行标识符                       |

---

## 5. 状态切换接口

所有状态切换方法内部调用 `execute()` 并传入对应的动作 ID。
方法使用简洁命名（无 `set_` 前缀）。

| Python 返回                  | C++ 返回 |
| ---------------------------- | -------- |
| `SequenceProgress` 或 `None` | `bool`   |

### 5.1 通用入口

| 方法                      | 参数                                      | 说明                                              |
| ------------------------- | ----------------------------------------- | ------------------------------------------------- |
| `set_target_state(state)` | `state`：FSM 状态名字符串（不区分大小写） | 切换到任意指定状态。未知状态名抛出 `ValueError`。 |

**合法状态名：** `passive`、`ready`、`stand_down`、`balance_stand`、`walk`、`flying_trot`、`rl`、`dance0`、`wave`、`jump`、`backflip`、`recovery`。

### 5.2 预定义状态

| 方法              | FSM 状态        | 别名          | 备注                           |
| ----------------- | --------------- | ------------- | ------------------------------ |
| `passive()`       | `passive`       | —             | 阻尼 / 预备模式                |
| `emergency()`     | `passive`       | —             | `passive()` 的别名，紧急停止   |
| `ready()`         | `ready`         | —             | 缓慢趴下（安全停止）           |
| `stand_down()`    | `stand_down`    | —             | 趴下                           |
| `stand_up()`      | `stand_up`      | —             | 站立                           |
| `balance_stand()` | `balance_stand` | —             | 平衡站立（多数动作的前置条件） |
| `walk()`          | `walk`          | —             | 行走状态                       |
| `rl()`            | `rl`            | —             | RL 状态                        |
| `flying_trot()`   | `flying_trot`   | —             | 奔跑步态                       |
| `change_mode()`   | `change_mode`   | —             | 腿部构型切换（平行 ↔ X 型）    |
| `dance0()`        | `dance0`        | `dance()`     | 跳舞动作                       |
| `wave()`          | `wave`          | `wave_hand()` | 打招呼动作                     |
| `jump()`          | `jump`          | —             | 跳跃动作                       |
| `backflip()`      | `backflip`      | —             | 后空翻动作                     |
| `recovery()`      | `recovery`      | —             | 恢复动作                       |

### 5.3 腿部构型

| 方法          | Python 签名     | C++ 签名        | 说明                                                      |
| ------------- | --------------- | --------------- | --------------------------------------------------------- |
| `change_mode` | `change_mode()` | `change_mode()` | 切换腿部构型（平行 ↔ X 型）。无参数，在两种构型之间切换。 |

---

## 6. 移动接口

### 6.1 直线行走

当显式提供 `speed_ratio` 时，方法会临时设置速度比并关闭避障，完成后恢复此前的值。当省略 `speed_ratio`（默认 `None` / `-1`）时，使用当前基础速度比，不进行保存/恢复操作。

| 方法            | Python 签名                                              | C++ 签名                                                              |
| --------------- | -------------------------------------------------------- | --------------------------------------------------------------------- |
| `line_walk`     | `line_walk(direction=0, distance=3.0, speed_ratio=None)` | `line_walk(int direction=0, float distance=3.0f, int speed_ratio=-1)` |
| `walk_forward`  | `walk_forward(distance=3.0, speed_ratio=None)`           | `walk_forward(float dist=3.0f, int sr=-1)`                            |
| `walk_backward` | `walk_backward(distance=3.0, speed_ratio=None)`          | `walk_backward(float dist=3.0f, int sr=-1)`                           |
| `move_left`     | `move_left(distance=3.0, speed_ratio=None)`              | `move_left(float dist=3.0f, int sr=-1)`                               |
| `move_right`    | `move_right(distance=3.0, speed_ratio=None)`             | `move_right(float dist=3.0f, int sr=-1)`                              |

**`line_walk` 参数：**

| 参数          | 类型                | 范围                                                           | 说明                                         |
| ------------- | ------------------- | -------------------------------------------------------------- | -------------------------------------------- |
| `direction`   | `int` / `str`（Py） | `0`/`"forward"`、`1`/`"backward"`、`2`/`"left"`、`3`/`"right"` | 行走方向。无效值抛出 `ValueError`。          |
| `distance`    | `float`             | `[0, 3]` 米（钳位）                                            | 行走距离（米）                               |
| `speed_ratio` | `int` 或 `None`     | `None`（使用当前值）或 `[10, 100]`（钳位）                     | 可选速度比覆盖。提供时临时设置，执行后恢复。 |

### 6.2 旋转

| 方法           | Python 签名                                              | C++ 签名                                                                                                 |
| -------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `rotate`       | `rotate(direction="left", angle=90.0)`                   | `rotate(int direction=0, float angle=90.0f)` / `rotate(const std::string& direction, float angle=90.0f)` |
| `rotate_left`  | `rotate_left(angle=90.0)`                                | `rotate_left(float angle=90.0f)`                                                                         |
| `rotate_right` | `rotate_right(angle=90.0)`                               | `rotate_right(float angle=90.0f)`                                                                        |
| `circle`       | `circle(direction="left", turns=1)`                      | `circle(const std::string& direction="left", int turns=1)`                                               |
| `rotate_walk`  | `rotate_walk(angle=0.0, distance=0.0, speed_ratio=None)` | `rotate_walk(float angle_deg=0.0f, float distance_m=0.0f, int speed_ratio=-1)`                           |

**`rotate` 参数：**

| 参数        | 类型          | 合法值                                 | 说明                                |
| ----------- | ------------- | -------------------------------------- | ----------------------------------- |
| `direction` | `str` / `int` | `"left"` / `"right"`（兼容 `0` / `1`） | 旋转方向。无效值抛出 `ValueError`。 |
| `angle`     | `float`       | `[0, 360]` 度（钳位）                  | 旋转角度                            |

**`circle` 参数：**

| 参数        | 类型  | 范围                 | 说明     |
| ----------- | ----- | -------------------- | -------- |
| `direction` | `str` | `"left"` / `"right"` | 方向     |
| `turns`     | `int` | `[1, 10]`（钳位）    | 转圈圈数 |

**`rotate_walk` 参数：**

| 参数          | 类型            | 范围                                       | 说明                                                     |
| ------------- | --------------- | ------------------------------------------ | -------------------------------------------------------- |
| `angle`       | `float`         | `[-180, 180]` 度（钳位）                   | 朝向角度。正数 = 逆时针（左转），负数 = 顺时针（右转）。 |
| `distance`    | `float`         | `[0, 3]` 米（钳位）                        | 旋转后前进的距离                                         |
| `speed_ratio` | `int` 或 `None` | `None`（使用当前值）或 `[10, 100]`（钳位） | 可选速度比覆盖                                           |

### 6.3 速度序列

直接速度控制。当显式提供 `speed_ratio` 时，临时设置速度比并关闭避障，完成后恢复。当省略（默认 `None` / `-1`）时，使用当前基础速度比，不进行保存/恢复。

|          | Python                                                                             | C++                                                                                                                     |
| -------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **签名** | `velocity_sequence(vel_seq, gait="walk", speed_ratio=None, stand_down_after=True)` | `velocity_sequence(const std::string& vel_seq, ...)` / `velocity_sequence(const std::vector<VelocityStep>& steps, ...)` |
| **返回** | `SequenceProgress` / `None`                                                        | `bool`                                                                                                                  |

**参数：**

| 参数               | 类型                                                                              | 说明                                                                   |
| ------------------ | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `vel_seq`          | `str` 或 `list[tuple]`（Py）/ `std::string` 或 `std::vector<VelocityStep>`（C++） | 速度指令；字符串格式：`"vx,vy,vyaw,dur;..."`                           |
| `gait`             | `str`                                                                             | `"walk"` 或 `"flying_trot"`。无效步态抛出 `ValueError`。               |
| `speed_ratio`      | `int` 或 `None`                                                                   | 可选速度比覆盖 `[10–100]`（钳位）。默认 `None`/`-1` = 使用当前基础值。 |
| `stand_down_after` | `bool`                                                                            | 是否在末尾追加 `stand_down` 动作                                       |

**`VelocityStep` 结构体（C++）：**

| 字段       | 类型    | 说明                                |
| ---------- | ------- | ----------------------------------- |
| `vx`       | `float` | 前进（+）/ 后退（−）速度（m/s）     |
| `vy`       | `float` | 左移（+）/ 右移（−）速度（m/s）     |
| `vyaw`     | `float` | 左转（+）/ 右转（−）角速度（rad/s） |
| `duration` | `float` | 该步持续时间（s）                   |

---

## 7. 姿态 / 平衡接口

所有平衡方法均需 `balance_stand` 状态作为前提（内部自动处理）。

**两种模式：**

- `"dynamic"` — 正弦扫描：0 → 目标值 → 0，在指定时长内完成。
- `"static"` — 缓慢过渡到目标值（0.5s），保持指定时长，缓慢过渡回 0（0.5s）。

### 7.1 单轴平衡动作

| 方法              | Python 签名                                           | C++ 签名                                                                              | 说明                                           |
| ----------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `balance_pitch`   | `balance_pitch(value, duration=2.0, mode="dynamic")`  | `balance_pitch(float value, float duration=2.0f, const std::string& mode="dynamic")`  | 俯仰（点头）。`>0` 前倾，`<0` 后仰。单位：度。 |
| `balance_yaw`     | `balance_yaw(value, duration=2.0, mode="dynamic")`    | `balance_yaw(float value, float duration=2.0f, const std::string& mode="dynamic")`    | 偏航（转头）。`>0` 向右，`<0` 向左。单位：度。 |
| `balance_roll`    | `balance_roll(value, duration=2.0, mode="dynamic")`   | `balance_roll(float value, float duration=2.0f, const std::string& mode="dynamic")`   | 横滚（侧倾）。`>0` 向左，`<0` 向右。单位：度。 |
| `balance_height`  | `balance_height(value, duration=2.0, mode="dynamic")` | `balance_height(float value, float duration=2.0f, const std::string& mode="dynamic")` | 高度增量。`<0` 下蹲。单位：米。                |
| `balance_neutral` | `balance_neutral(duration=0.5)`                       | `balance_neutral(float duration=0.5f)`                                                | 所有轴回中                                     |

| 参数       | 类型    | 范围                                                                                       | 说明                              |
| ---------- | ------- | ------------------------------------------------------------------------------------------ | --------------------------------- |
| `value`    | `float` | `roll: [-30, 30]°`、`pitch: [-15, 15]°`、`yaw: [-20, 20]°`、`height: [-0.12, 0]` 米 — 钳位 | 目标偏置值，度（rpy）或米（高度） |
| `duration` | `float` | `[0.5, 5]` 秒（钳位）                                                                      | 持续时间（秒）                    |
| `mode`     | `str`   | `"dynamic"` / `"static"`                                                                   | 运动模式                          |

**合法 `motion_id` 值：** `balance_pitch`、`balance_yaw`、`balance_roll`、`balance_height`、`balance_neutral`。非法 ID 抛出 `ValueError`。

### 7.2 批量平衡序列

单次 RPC 调用执行多个平衡动作——比逐个调用更高效。

|          | Python                      | C++                                                           |
| -------- | --------------------------- | ------------------------------------------------------------- |
| **签名** | `balance_sequence(motions)` | `balance_sequence(const std::vector<BalanceMotion>& motions)` |
| **返回** | `SequenceProgress` / `None` | `bool`                                                        |

**`motions` 格式：**

| 语言   | 格式                                                                                 |
| ------ | ------------------------------------------------------------------------------------ |
| Python | `list[tuple(motion_id: str, value: float, duration: float, mode: str)]`              |
| C++    | `std::vector<BalanceMotion>`，其中 `BalanceMotion{motion_id, value, duration, mode}` |

会校验 `motion_id` 并将 `value` 钳位到对应轴的合法范围。

### 7.3 复合姿势：`dynamic_pose` / `static_pose`

同时控制 roll、pitch、yaw 和高度——所有轴在**一个**服务端动作中同步执行。

- `dynamic_pose` — 所有轴正弦扫描：0 → 目标值 → 0，在指定时长内完成。
- `static_pose` — 所有轴缓慢过渡至目标值，保持指定时长，再缓慢过渡回 0。

|          | Python                                                                       | C++                                                                                                    |
| -------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **签名** | `dynamic_pose(duration=2.0, roll_deg=0, pitch_deg=0, yaw_deg=0, height_m=0)` | `dynamic_pose(float duration, float roll_deg=0, float pitch_deg=0, float yaw_deg=0, float height_m=0)` |
|          | `static_pose(duration=2.0, roll_deg=0, pitch_deg=0, yaw_deg=0, height_m=0)`  | `static_pose(float duration, float roll_deg=0, float pitch_deg=0, float yaw_deg=0, float height_m=0)`  |
| **返回** | `SequenceProgress` / `None`                                                  | `bool`                                                                                                 |

| 参数        | 类型    | 范围                    | 说明                                         |
| ----------- | ------- | ----------------------- | -------------------------------------------- |
| `duration`  | `float` | `[1, 5]` 秒（钳位）     | 持续时间（秒）                               |
| `roll_deg`  | `float` | `[-30, 30]°`（钳位）    | 横滚角度。`0` = 不动。                       |
| `pitch_deg` | `float` | `[-15, 15]°`（钳位）    | 俯仰角度。`0` = 不动。                       |
| `yaw_deg`   | `float` | `[-20, 20]°`（钳位）    | 偏航角度。`>0` 向右，`<0` 向左，`0` = 不动。 |
| `height_m`  | `float` | `[-0.12, 0]` 米（钳位） | 高度增量。`0` = 不动。                       |

---

## 8. 安全与资源管理

### 8.1 `enable_safety_ready`

注册 Ctrl+C 处理器。当按下 Ctrl+C 时，当前动作被取消，机器人在进程退出前切换到 `ready` 状态。

|          | Python                        | C++                                  |
| -------- | ----------------------------- | ------------------------------------ |
| **签名** | `robot.enable_safety_ready()` | `robot::enable_safety_ready(client)` |
| **返回** | `None`                        | `void`                               |

> **注意：** 处理器仅在 Ctrl+C（SIGINT）时触发。程序正常退出**不会**调用 `ready()`。

### 8.2 资源管理

|                | Python                   | C++                                      |
| -------------- | ------------------------ | ---------------------------------------- |
| 关闭通道       | `close()`                | _（析构函数）_                           |
| 上下文管理器   | `__enter__` / `__exit__` | —                                        |
| 原始 stub 访问 | —                        | `operator->()` 返回 `gRPCService::Stub*` |

---

## 9. 参数校验规则总结

| 参数                                | 钳位范围                                                                            | 错误处理                                           |
| ----------------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------- |
| `speed_ratio`                       | `[10, 100]`                                                                         | 静默钳位                                           |
| `set_target_state` 状态名           | 必须为合法状态                                                                      | `ValueError`（Py）/ `std::invalid_argument`（C++） |
| `velocity_sequence` 步态            | `"walk"` / `"flying_trot"`                                                          | `ValueError`（Py）/ `std::invalid_argument`（C++） |
| `line_walk` 方向                    | `0–3` 或 `"forward"/"backward"/"left"/"right"`                                      | 无效值抛出 `ValueError`                            |
| `line_walk` 距离                    | `[0, 3]` 米                                                                         | 静默钳位                                           |
| `line_walk` 速度比                  | `None`（使用当前值）或 `[10, 100]`                                                  | 提供时静默钳位                                     |
| `rotate` 角度                       | `[0, 360]`                                                                          | 静默钳位                                           |
| `rotate` 方向                       | `"left"` / `"right"`（兼容 `0` / `1`）                                              | 无效值抛出 `ValueError`                            |
| `circle` 圈数                       | `[1, 10]`                                                                           | 静默钳位                                           |
| `rotate_walk` 角度                  | `[-180, 180]`                                                                       | 静默钳位                                           |
| `rotate_walk` 距离                  | `[0, 3]` 米                                                                         | 静默钳位                                           |
| `rotate_walk` 速度比                | `None`（使用当前值）或 `[10, 100]`                                                  | 提供时静默钳位                                     |
| 平衡 `value`                        | `roll: [-30, 30]°`、`pitch: [-15, 15]°`、`yaw: [-20, 20]°`、`height: [-0.12, 0]` 米 | 静默钳位                                           |
| 平衡 `duration`                     | `[0.5, 5]` 秒                                                                       | 静默钳位                                           |
| 平衡 `motion_id`                    | 必须为合法平衡动作                                                                  | 非法 ID 抛出 `ValueError`                          |
| `dynamic_pose` / `static_pose` 角度 | `roll: [-30, 30]°`、`pitch: [-15, 15]°`、`yaw: [-20, 20]°`                          | 静默钳位                                           |
| `dynamic_pose` / `static_pose` 高度 | `[-0.12, 0]` 米                                                                     | 静默钳位                                           |
| `dynamic_pose` / `static_pose` 时长 | `[1, 5]` 秒                                                                         | 静默钳位                                           |
| `set_obstacle_avoidance` 字符串     | 仅 `"on"` / `"off"`                                                                 | `ValueError`（Py）/ `std::invalid_argument`（C++） |

---

## 10. 积木块名 → API 速查表

| 积木块名               | Python API                              | C++ API                                 |
| ---------------------- | --------------------------------------- | --------------------------------------- |
| passive                | `passive()`                             | `passive()`                             |
| emergency              | `emergency()`                           | `emergency()`                           |
| ready                  | `ready()`                               | `ready()`                               |
| stand_down             | `stand_down()`                          | `stand_down()`                          |
| balance_stand          | `balance_stand()`                       | `balance_stand()`                       |
| walk                   | `walk()`                                | `walk()`                                |
| rl                     | `rl()`                                  | `rl()`                                  |
| flying_trot            | `flying_trot()`                         | `flying_trot()`                         |
| change_mode            | `change_mode()`                         | `change_mode()`                         |
| change_mode            | `change_mode()`                         | `change_mode()`                         |
| walk_forward           | `walk_forward(distance, speed_ratio)`   | `walk_forward(dist, sr)`                |
| walk_backward          | `walk_backward(distance, speed_ratio)`  | `walk_backward(dist, sr)`               |
| move_left              | `move_left(distance, speed_ratio)`      | `move_left(dist, sr)`                   |
| move_right             | `move_right(distance, speed_ratio)`     | `move_right(dist, sr)`                  |
| set_speed_ratio        | `set_speed_ratio(ratio)`                | `set_speed_ratio(ratio)`                |
| get_speed_ratio        | `get_speed_ratio()`                     | `get_speed_ratio()`                     |
| set_obstacle_avoidance | `set_obstacle_avoidance("on"/"off")`    | `set_obstacle_avoidance("on"/"off")`    |
| get_obstacle_avoidance | `get_obstacle_avoidance()`              | `get_obstacle_avoidance()`              |
| rotate                 | `rotate("left"/"right", angle)`         | `rotate("left"/"right", angle)`         |
| circle                 | `circle("left"/"right", turns)`         | `circle("left"/"right", turns)`         |
| rotate_walk            | `rotate_walk(angle, distance)`          | `rotate_walk(angle, distance)`          |
| dynamic_pose           | `dynamic_pose(duration, ...)`           | `dynamic_pose(duration, ...)`           |
| static_pose            | `static_pose(duration, ...)`            | `static_pose(duration, ...)`            |
| balance_pitch          | `balance_pitch(value, duration, mode)`  | `balance_pitch(value, duration, mode)`  |
| balance_yaw            | `balance_yaw(value, duration, mode)`    | `balance_yaw(value, duration, mode)`    |
| balance_roll           | `balance_roll(value, duration, mode)`   | `balance_roll(value, duration, mode)`   |
| balance_height         | `balance_height(value, duration, mode)` | `balance_height(value, duration, mode)` |
| balance_neutral        | `balance_neutral(duration)`             | `balance_neutral(duration)`             |
| dance                  | `dance()`                               | `dance()`                               |
| jump                   | `jump()`                                | `jump()`                                |
| wave_hand              | `wave_hand(duration=5.0)`               | `wave_hand(int duration_sec=5)`         |
| backflip               | `backflip()`                            | `backflip()`                            |
| enable_safety_ready    | `robot.enable_safety_ready()`           | `robot::enable_safety_ready(client)`    |

---

## 11. 变更日志

### 2026-03-18

| 类型     | 变更                                                                                                                                                                                 |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **变更** | 更新平衡钳位范围：`roll ±30°`、`pitch ±15°`、`yaw ±20°`、`height [-0.12, 0]m`；单轴时长 `[0.5, 5]s`，复合姿势时长 `[1, 5]s`。                                                        |
| **变更** | `set_obstacle_avoidance` 在客户端 RPC 路径下也会触发避障开/关语音提示。                                                                                                              |
| **变更** | `E3` 增加 `change_mode` 作为可交互/命令行动作选项。                                                                                                                                  |
| **变更** | `E6` 明确演示 `balance_pitch/yaw/roll/height` 单轴接口（dynamic + static），以及 `balance_sequence`、`dynamic_pose`、`static_pose`。                                                 |
| **变更** | `E9` 现按最新脚本顺序演示组合流程：状态切换（`walk` + `change_mode` 切换）、前后左右各 1 米、左右 90°/180° 旋转、转圈 1 圈、四个单轴平衡动作（dynamic + static）和两个复合平衡动作。 |

### 2026-07-22

| 类型     | 变更                                                                                                                      |
| -------- | ------------------------------------------------------------------------------------------------------------------------- |
| **新增** | `dynamic_pose(duration, roll_deg, pitch_deg, yaw_deg, height_m)` — 复合正弦姿势，在单个服务端动作中同时控制所有轴。       |
| **新增** | `static_pose(duration, roll_deg, pitch_deg, yaw_deg, height_m)` — 复合保持姿势，在单个服务端动作中同时控制所有轴。        |
| **新增** | `ready()` — 缓慢趴下状态切换。                                                                                            |
| **新增** | `emergency()` — `passive()` 的别名。                                                                                      |
| **新增** | `enable_safety_ready()` — Ctrl+C 时自动执行 `ready()`（安全处理器）。仅在 SIGINT 时触发，程序正常退出不触发。             |
| **变更** | 平衡动作现使用 `value`（rpy 为度，高度为米）、`duration`（秒）和 `mode`（"dynamic"/"static"）替代原来的 amplitude/beats。 |
| **变更** | `dynamic_pose` 不再接受 `mode` 参数——始终为 "dynamic"。如需 "static" 模式，请使用 `static_pose`。                         |
| **移除** | `set_bpm()` / `bpm()` — 不再使用 BPM。平衡计时现基于时长（秒）。                                                          |
| **移除** | 构造函数和 `execute()` 中的 `bpm` 参数。                                                                                  |
| **修复** | C++ 程序正常退出时的段错误（atexit 处理器访问已析构的 client）。                                                          |
| **修复** | Python `enable_safety_ready()` 不再在正常退出时触发 `ready()`——仅在 Ctrl+C 时触发。                                       |

### 2026-07-20

| 类型     | 变更                                                                                                                                                                                                                                                           |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **变更** | `line_walk`、`walk_forward`、`walk_backward`、`move_left`、`move_right`、`velocity_sequence`、`rotate_walk` 的 `speed_ratio` 参数默认值从 `80` 改为 `None`（Python）/ `-1`（C++）。省略时使用当前基础速度比，不进行保存/恢复。显式提供时临时覆盖，执行后恢复。 |
| **变更** | `get_speed_ratio()` 和 `get_obstacle_avoidance()` 现在返回本地跟踪的值，而非向服务端查询。值从 `set_*` RPC 响应中更新。避免了最终一致性 `GetRobotState` RPC 的过期读取问题。                                                                                   |
| **变更** | 构造函数现在通过 `get_state()` 获取初始速度比，而非 `get_speed_ratio()`，并将值存储在本地而非通过服务端查询缓存。                                                                                                                                              |

### 2026-07-18

| 类型     | 变更                                                                                                                                                                                                                            |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **新增** | `x_leg(mode)` — 切换 `"std"`（平行）和 `"x"`（X 形）腿部模式                                                                                                                                                                    |
| **变更** | `walk_left` → `move_left`、`walk_right` → `move_right`                                                                                                                                                                          |
| **变更** | `line_walk` / `rotate_walk` 距离范围：`[0, 10]` → `[0, 3]` 米                                                                                                                                                                   |
| **变更** | `circle` 圈数范围：`[1, 5]` → `[1, 10]`                                                                                                                                                                                         |
| **变更** | 提取可复用验证工具函数（`clamp_speed_ratio`、`clamp_distance`、`clamp_angle`、`clamp_turns`、`clamp_amplitude`、`validate_state`、`validate_balance_motion`、`validate_gait`、`resolve_direction`、`resolve_rotate_direction`） |
| **变更** | C++ 状态方法现可不带 `set_` 前缀调用（如 `balance_stand()` 与 `set_balance_stand()` 并存）                                                                                                                                      |
| **变更** | 构造函数改为查询 `get_speed_ratio()` 而非 `set_speed_ratio(0)`                                                                                                                                                                  |
| **移除** | `rl` 步态已从 `velocity_sequence` 中移除                                                                                                                                                                                        |

---

## 12. 版本

本文档对应当前工作区实现（**2026-07-22**）。
