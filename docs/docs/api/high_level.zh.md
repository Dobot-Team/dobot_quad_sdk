# 高层 API 文档

高层机器人客户端库的公开接口参考与示例程序文档。

| 语言   | 文件                                           | 类              |
| ------ | ---------------------------------------------- | --------------- |
| Python | `high_level/python/dobot_quad/robot_client.py` | `RobotClient`   |
| C++    | `high_level/cpp/robot_client.h`                | `robot::Client` |

!!! info "传输协议"
`grpc_service.proto`（`grpc_comm` 包），所有调用均通过 gRPC。

## 一、快速上手

=== "Python"

    ```python
    from dobot_quad import RobotClient

    robot = RobotClient("192.168.5.2:50051")

    robot.balance_stand()            # 切换到平衡站立
    robot.walk_forward(2.0)          # 向前走 2 米
    robot.move_left(1.0)             # 向左移动 1 米
    robot.rotate("left", 90)         # 左转 90°
    robot.change_mode()              # 切换腿部构型
    robot.dance()                    # 跳舞
    robot.stand_down()               # 趴下
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"

    robot::Client client("192.168.5.2:50051");

    client.balance_stand();           // 切换到平衡站立
    client.walk_forward(2.0);         // 向前走 2 米
    client.move_left(1.0);            // 向左移动 1 米
    client.rotate("left", 90);        // 左转 90°
    client.change_mode();             // 切换腿部构型
    client.dance();                   // 跳舞
    client.stand_down();              // 趴下
    ```

### 轮足机器人快速上手

!!! info "机型自动检测"
SDK 通过 `get_robot_type()` 自动检测连接的机器人类型（点足 `miniQuad` 或轮足 `miniQuadW`）。
`line_walk`、`rotate`、`velocity_sequence` 等接口在两种机型上通用，服务端会自动选择对应的运动控制器。

=== "Python"

    ```python
    from dobot_quad import RobotClient

    robot = RobotClient("192.168.5.2:50051")

    print(robot.get_robot_type())     # "miniQuadW"
    print(robot.is_quad_wheel())      # True

    robot.wheel_loco()                # 切换到轮式运动
    robot.walk_forward(2.0)           # 向前走 2 米
    robot.move_left(1.0)              # 向左移动 1 米
    robot.rotate("left", 90)          # 左转 90°
    robot.drift()                     # 切换到漂移模式
    robot.change_mode()               # 切换腿部构型
    robot.handstand()                 # 倒立
    robot.stand_down()                # 趴下
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"

    robot::Client client("192.168.5.2:50051");

    std::cout << client.get_robot_type();  // "miniQuadW"
    std::cout << client.is_quad_wheel();   // true

    client.wheel_loco();                // 切换到轮式运动
    client.walk_forward(2.0);           // 向前走 2 米
    client.move_left(1.0);              // 向左移动 1 米
    client.rotate("left", 90);          // 左转 90°
    client.drift();                     // 切换到漂移模式
    client.change_mode();               // 切换腿部构型
    client.handstand();                 // 倒立
    client.stand_down();                // 趴下
    ```

## 二、接口说明

## 1. 构造函数 / 连接接口

=== "Python"

    ```python
    RobotClient(addr="192.168.5.2:50051")
    ```

=== "C++"

    ```cpp
    Client(addr="192.168.5.2:50051")
    ```

| 参数   | 类型   | 默认值                | 说明          |
| ------ | ------ | --------------------- | ------------- |
| `addr` | string | `"192.168.5.2:50051"` | gRPC 服务地址 |

**构造时行为：**

1. 打开到 `addr` 的 gRPC 通道。
2. 通过 `get_state()` 查询当前速度比并存储到本地。
3. 开启避障（`set_obstacle_avoidance(true)`）并将结果存储到本地。

=== "Python"

    ```python
    # 上下文管理器（推荐）
    with RobotClient("192.168.5.2:50051") as robot:
        robot.balance_stand()
    # 退出时自动关闭通道
    ```

=== "C++"

    ```cpp
    robot::Client client("192.168.5.2:50051");
    client.balance_stand();
    // 析构时自动清理
    ```

## 2. 查询接口

### 2.1 get_state()

返回机器人完整遥测状态快照。

| 返回字段                     | 类型       | 说明                   |
| ---------------------------- | ---------- | ---------------------- |
| `success`                    | bool       | RPC 是否成功           |
| `current_state`              | string     | 当前 FSM 状态名        |
| `current_speed_ratio`        | int32      | 当前速度比 [10–100]    |
| `obstacle_avoidance_enabled` | bool       | 避障是否激活           |
| `robot_state`                | RobotState | 关节、机体、接触力遥测 |

`RobotState` 消息体：

| 字段                      | 类型     | 说明                               |
| ------------------------- | -------- | ---------------------------------- |
| `jpos_leg / jpos_leg_des` | float[]  | 腿部关节位置 / 期望位置（rad）     |
| `jvel_leg / jvel_leg_des` | float[]  | 腿部关节速度 / 期望速度（rad/s）   |
| `jtau_leg / jtau_leg_des` | float[]  | 腿部关节力矩 / 期望力矩（Nm）      |
| `pos_body`                | float[3] | 机体位置 [x, y, z]（m）            |
| `vel_body`                | float[3] | 机体线速度（m/s）                  |
| `acc_body`                | float[3] | 机体线加速度（m/s²）               |
| `omega_body`              | float[3] | 机体角速度（rad/s）                |
| `ori_body`                | float[3] | 机体姿态 [roll, pitch, yaw]（rad） |
| `grf_left / grf_right`    | float[3] | 左/右脚地面反力（N）               |
| `grf_vertical_filtered`   | float[2] | 滤波后垂直接触力（N）              |

### 2.2 get_motions()

返回服务端已注册的动作库列表。

### 2.3 get_current_state_name() → string

获取当前 FSM 状态名。失败时返回空字符串。

### 2.4 get_speed_ratio() → int

返回本地跟踪的速度比。该值在每次调用 `set_speed_ratio()` 时从 RPC 响应中更新。

### 2.5 get_obstacle_avoidance() → bool

返回本地跟踪的避障状态。该值在每次调用 `set_obstacle_avoidance()` 时从 RPC 响应中更新。

### 2.6 get_robot_type() → string

返回机器人类型标识字符串。点足返回 `"miniQuad"`，轮足返回 `"miniQuadW"`。首次调用后缓存结果。

### 2.7 is_quad() → bool

返回是否为点足机器人（`robot_type == "miniQuad"`）。

### 2.8 is_quad_wheel() → bool

返回是否为轮足机器人（`robot_type == "miniQuadW"`）。

## 3. 配置接口

### 3.1 set_speed_ratio(ratio)

设置速度比，自动钳位到 **[10, 100]**。

=== "Python"

    ```python
    set_speed_ratio(ratio: int)
    ```

=== "C++"

    ```cpp
    set_speed_ratio(int ratio)
    ```

### 3.2 set_obstacle_avoidance(enable)

启用/禁用避障。接受 `bool` 或 `"on"/"off"` 字符串。

客户端通过 RPC 切换避障时，服务端会同步触发语音提示：`avoid_obstacle_on.wav` / `avoid_obstacle_off.wav`。

## 4. 动作执行接口

### 4.1 execute(\*motions, loop=False)

执行动作序列并实时流式输出进度。每个参数可以是：

- `str` — 动作 ID
- `(str, dict)` — 动作 ID + 参数字典

按 **ctrl+c** 可随时取消。

## 5. 状态切换接口

### 5.1 set_target_state(state_name)

通过名称切换状态（大小写不敏感）。无效名称抛出 `ValueError`。

**有效状态 / 函数列表：**

| #   | 函数                      | 说明                 | 备注                    |
| --- | ------------------------- | -------------------- | ----------------------- |
| 1   | `passive()`               | 被动模式（电机断电） |                         |
| 2   | `emergency()`             | 紧急停止             | `passive()` 的别名      |
| 3   | `ready()`                 | 缓慢趴下（安全停止） | :material-new-box: 新增 |
| 4   | `stand_down()`            | 趴下                 |                         |
| 5   | `balance_stand()`         | 平衡站立             |                         |
| 6   | `walk()`                  | 切换到行走模式       |                         |
| 7   | `rl()`                    | 切换到 RL 模式       |                         |
| 8   | `flying_trot()`           | 切换到奔跑模式       |                         |
| 9   | `gongxi()`                | 切换到恭喜（作揖）状态 | 原名 `choreo()`         |
| 10  | `change_mode()`           | 行走⇄奔跑平滑切换    | :material-new-box: 新增 |
| 11  | `dance()`                 | 跳舞（别名：dance0） |                         |
| 12  | `jump()`                  | 跳跃                 |                         |
| 13  | `wave_hand(duration=5.0)` | 打招呼（别名：wave） |                         |
| 14  | `backflip()`              | 后空翻               |                         |
| 15  | `recovery()`              | 恢复/自救            |                         |

**轮足机器人（miniQuadW）有效状态 / 函数列表：**

| #   | 函数            | 说明                 | 备注                        |
| --- | --------------- | -------------------- | --------------------------- |
| 1   | `passive()`     | 被动模式（电机断电） | 共用                        |
| 2   | `emergency()`   | 紧急停止             | `passive()` 的别名          |
| 3   | `ready()`       | 缓慢趴下（安全停止） | 共用                        |
| 4   | `stand_down()`  | 趴下                 | 共用                        |
| 5   | `wheel_loco()`  | 轮式运动             | :material-new-box: 轮足专用 |
| 6   | `drift()`       | 漂移模式             | :material-new-box: 轮足专用 |
| 7   | `handstand()`   | 倒立                 | :material-new-box: 轮足专用 |
| 8   | `change_mode()` | 切换腿部构型         | 共用                        |

!!! warning "注意"
所有状态切换方法已移除 `set_` 前缀。请使用 `robot.balance_stand()` 而非 `robot.set_balance_stand()`。

!!! note "更名：`choreo()` → `gongxi()`"
    `choreo` 状态自 v1.3.0 起更名为 `gongxi`。旧代码仍然可用：

    - Python `robot.choreo()` 与 C++ `client.choreo()` / `client.set_choreo()` 会转发到
      `gongxi()`，并发出废弃告警。
    - `robot.set_target_state("choreo")` 会被接受并映射为 `gongxi`。

    请尽快改用 `gongxi()`；废弃名称将在后续版本中移除。

### 5.2 change_mode()

切换腿部构型（平行 ↔ X 型）。无参数，在两种构型之间切换。

=== "Python"

    ```python
    robot.change_mode()    # 切换腿部构型
    robot.change_mode()    # 再次调用切换回另一种
    ```

=== "C++"

    ```cpp
    client.change_mode();    // 切换腿部构型
    client.change_mode();    // 再次调用切换回另一种
    ```

## 6. 速度序列接口

### 6.1 velocity_sequence(vel_seq, gait, speed_ratio, stand_down_after)

执行速度序列。当显式提供 `speed_ratio` 时临时设置并执行后恢复；省略时使用当前基础速度比。

| 参数               | 类型          | 默认      | 说明                                                            |
| ------------------ | ------------- | --------- | --------------------------------------------------------------- |
| `vel_seq`          | string / list | —         | `"vx,vy,vyaw,dur;..."` 或元组列表                               |
| `gait`             | string        | `"walk"`  | 点足：`"walk"` / `"flying_trot"` / `"rl"`；轮足：`"wheel_loco"` |
| `speed_ratio`      | int           | `None/-1` | 可选 [10, 100]，省略时使用当前基础值                            |
| `stand_down_after` | bool          | `true`    | 序列结束后是否趴下                                              |

=== "Python"

    ```python
    steps = [
        (0.8, 0, 0, 2),   # 前进 2s
        (0, 0, 0, 1),     # 停止 1s
        (-0.8, 0, 0, 2),  # 后退 2s
    ]
    robot.velocity_sequence(steps, gait="walk", speed_ratio=60)
    ```

=== "C++"

    ```cpp
    std::vector<robot::VelocityStep> steps = {
        {0.8f, 0, 0, 2},   // 前进 2s
        {0, 0, 0, 1},      // 停止 1s
        {-0.8f, 0, 0, 2},  // 后退 2s
    };
    client.velocity_sequence(steps, "walk", 60);
    ```

## 7. 直线行走接口

### 7.1 line_walk(direction, distance, speed_ratio)

当显式提供 `speed_ratio` 时临时设置并执行后恢复；省略时使用当前基础速度比。

!!! info "轮足机器人支持"
轮足机器人在 **WHEEL_LOCO**（`knee_mode=0`）和 **DRIFT**（`knee_mode=1`）两种状态下均支持直线行走。服务端会根据当前 `knee_mode` 自动选择目标状态。
注意：DRIFT 模式下**不支持**左右横移（`move_left` / `move_right`），仅支持前进和后退。

| 参数          | 类型         | 范围              | 说明                                           |
| ------------- | ------------ | ----------------- | ---------------------------------------------- |
| `direction`   | int / string | 0-3               | 0="forward", 1="backward", 2="left", 3="right" |
| `distance`    | float        | **[0, 3] m**      | 行走距离（米）                                 |
| `speed_ratio` | int / None   | None 或 [10, 100] | 可选速度比覆盖                                 |

### 7.2 方向快捷函数

| 函数                      | 等价调用                 | 说明     |
| ------------------------- | ------------------------ | -------- |
| `walk_forward(distance)`  | `line_walk(0, distance)` | 向前走   |
| `walk_backward(distance)` | `line_walk(1, distance)` | 向后走   |
| `move_left(distance)`     | `line_walk(2, distance)` | 向左移动 |
| `move_right(distance)`    | `line_walk(3, distance)` | 向右移动 |

!!! warning "Breaking Change"
`walk_left` → `move_left`，`walk_right` → `move_right`。距离上限从 10m 改为 **3m**。

## 8. 旋转控制接口

!!! info "轮足机器人支持"
旋转接口在轮足机器人上仅在 **WHEEL_LOCO** 状态下可用（DRIFT 模式不支持原地旋转）。
`rotate_walk` 由旋转 + 直线行走组合而成，同样受此限制。

### 8.1 rotate(direction, angle)

| 参数        | 类型         | 范围                  | 说明     |
| ----------- | ------------ | --------------------- | -------- |
| `direction` | string / int | "left"/"right" 或 0/1 | 旋转方向 |
| `angle`     | float        | [0, 3600]°             | 旋转角度 |

快捷函数：`rotate_left(angle)`，`rotate_right(angle)`

### 8.2 circle(direction, turns)

旋转指定圈数。

| 参数        | 范围           | 说明     |
| ----------- | -------------- | -------- |
| `direction` | "left"/"right" | 旋转方向 |
| `turns`     | **[1, 10]**    | 圈数     |

### 8.3 rotate_walk(angle, distance)

朝指定方向角度行走。

| 参数       | 范围             | 说明                             |
| ---------- | ---------------- | -------------------------------- |
| `angle`    | **[-180, 180]°** | 目标方向角度（正数=右，负数=左） |
| `distance` | **[0, 3] m**     | 行走距离                         |

## 9. 平衡动作接口

!!! warning "仅限点足机器人"
平衡动作接口（balance_pitch / balance_yaw / balance_roll / balance_height / balance_neutral / balance_sequence）以及复合姿势接口（dynamic_pose / static_pose）仅在点足机器人（miniQuad）的 BALANCE_STAND 状态下可用。轮足机器人不支持这些接口。

!!! info "模式说明"
`"dynamic"` — 正弦扫描到目标值 → 保持；
`"static"` — 斜坡到目标值，保持，斜坡回中。

### 9.1 单轴控制

| 函数                                    | value 范围   | 说明                   |
| --------------------------------------- | ------------ | ---------------------- |
| `balance_pitch(value, duration, mode)`  | [-11.5, 11.5]°   | 俯仰。>0 前倾，<0 后仰 |
| `balance_yaw(value, duration, mode)`    | [-11.5, 11.5]°   | 偏航。>0 右看，<0 左看 |
| `balance_roll(value, duration, mode)`   | [-17.0, 17.0]°   | 横滚。>0 左倾，<0 右倾 |
| `balance_height(value, duration, mode)` | [-0.08, 0] m     | 高度。<0 下蹲          |
| `balance_neutral(duration)`             | —            | 回到中位               |

| 参数       | 类型   | 范围                 | 说明                                                                    |
| ---------- | ------ | -------------------- | ----------------------------------------------------------------------- |
| `value`    | float  | 见上表               | 目标偏置值（从初始姿态到目标姿态的变化量），单位：度（rpy）或米（高度） |
| `duration` | float  | [0.5, 5] s           | 持续时间（秒），默认 2.0                                                |
| `mode`     | string | "dynamic" / "static" | 运动模式，默认 "dynamic"                                                |

### 9.2 批量执行

`balance_sequence(motions)` — 在单次 RPC 中批量执行多个平衡动作。motions 格式：`(motion_id, value, duration, mode)`

=== "Python"

    ```python
    robot.balance_sequence([
        ("balance_pitch",  11.5, 2.0, "dynamic"),   # 前倾 11.5°
        ("balance_pitch", -11.5, 2.0, "dynamic"),   # 后仰 11.5°
        ("balance_neutral", 0.0, 0.5, "dynamic"),   # 回中位
    ])
    ```

=== "C++"

    ```cpp
    client.balance_sequence({
        {"balance_pitch",   11.5f, 2.0f, "dynamic"},
        {"balance_pitch",  -11.5f, 2.0f, "dynamic"},
        {"balance_neutral",  0.0f, 0.5f, "dynamic"},
    });
    ```

## 10. 复合姿势接口

包含 dynamic_pose / static_pose。同时控制 roll、pitch、yaw、height — 所有轴在一个服务端动作中同步执行。

| 参数        | 范围         | 说明                                 |
| ----------- | ------------ | ------------------------------------ |
| `duration`  | [1, 5] s     | 持续时间（秒）                       |
| `roll_deg`  | [-17.0, 17.0]°   | 横滚角度，0 = 不动                   |
| `pitch_deg` | [-11.5, 11.5]°   | 俯仰角度，0 = 不动                   |
| `yaw_deg`   | [-11.5, 11.5]°   | 偏航角度，>0 向右，<0 向左，0 = 不动 |
| `height_m`  | [-0.08, 0] m | 高度增量，0 = 不动                   |

!!! tip "区别"
`dynamic_pose` — 正弦扫描到目标；
`static_pose` — 斜坡到目标，保持，斜坡回中。

=== "Python"

    ```python
    # 正弦扫描：同时控制多轴
    robot.dynamic_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)

    # 保持姿势：斜坡到目标，保持 5 秒
    robot.static_pose(5.0, pitch_deg=15, height_m=-0.03)

    # 回中位
    robot.balance_neutral()
    ```

=== "C++"

    ```cpp
    // 正弦扫描：同时控制多轴
    client.dynamic_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);

    // 保持姿势：斜坡到目标，保持 5 秒
    client.static_pose(5.0f, 15.0f, 0.0f, 0.0f, -0.03f);

    // 回中位
    client.balance_neutral();
    ```

## 11. 特殊动作接口

| 函数                      | 说明                      |
| ------------------------- | ------------------------- |
| `dance()`                 | 跳舞（内部调用 `dance0`） |
| `jump()`                  | 跳跃                      |
| `wave_hand(duration=5.0)` | 打招呼（内部调用 `wave`） |
| `backflip()`              | 后空翻                    |

## 12. 安全处理器接口

### enable_safety_ready()

注册 **Ctrl+C** 处理器。当按下 **Ctrl+C** 时，取消当前动作并在进程退出前切换到 `ready` 状态。

=== "Python"

    ```python
    robot.enable_safety_ready()
    ```

=== "C++"

    ```cpp
    robot::enable_safety_ready(client)
    ```

!!! warning "注意"
处理器仅在 Ctrl+C（SIGINT）时触发。程序正常退出**不会**调用 `ready()`。

## 13. 腿灯控制接口

通过高层 API 控制机器人四条腿上的 RGB 灯。设置任一腿灯即覆盖机器狗内置灯光逻辑；调用 `reset_legs()` 后恢复默认灯光。

### 腿灯标识

| 标识 | 说明 |
|------|------|
| `Leg.FL` | 左前腿 |
| `Leg.FR` | 右前腿 |
| `Leg.RL` | 左后腿 |
| `Leg.RR` | 右后腿 |

### 预定义颜色

```python
Color.OFF, Color.RED, Color.ORANGE, Color.YELLOW, Color.GREEN,
Color.CYAN, Color.BLUE, Color.PURPLE, Color.WHITE
```

=== "Python"

    ```python
    from dobot_quad import Leg, Color

    # 全部设为红色
    robot.set_all_legs_color(Color.RED)

    # 前腿蓝色，后腿绿色
    robot.set_legs_rgb([Leg.FL, Leg.FR], Color.BLUE)
    robot.set_legs_rgb([Leg.RL, Leg.RR], Color.GREEN)

    # 单腿设置原始 RGB
    robot.set_leg_rgb(Leg.FL, 255, 0, 128)

    # 亮度控制
    robot.set_leg_brightness(Leg.RR, 128)  # 50%

    # 恢复默认灯光
    robot.reset_legs()
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"
    using namespace robot;

    // 全部设为红色
    client.set_all_legs_color(Color::RED);

    // 前腿蓝色，后腿绿色
    client.set_legs_rgb({Leg::FL, Leg::FR}, Color::BLUE);
    client.set_legs_rgb({Leg::RL, Leg::RR}, Color::GREEN);

    // 单腿设置原始 RGB
    client.set_leg_rgb(Leg::FL, 255, 0, 128);

    // 亮度控制
    client.set_leg_brightness(Leg::RR, 128);  // 50%

    // 恢复默认灯光
    client.reset_legs();
    ```

## 14. 原子编舞动作（仅点足构型）

八个单一编舞动作，自动处理状态切换，完成后返回 `WALK` 模式。

| 方法 | 描述 | 时长 |
|------|------|------|
| `twirl_jump()` | 跳跃转体 | ~0.7s |
| `diag_step()` | 对角迈步 | ~5.9s |
| `hop_step()` | 前腿蹦跳迈步 | ~3s |
| `groove()` | 摇摆律动 | ~8s |
| `bounce()` | 点头弹跳 | ~6s |
| `body_wave()` | 身体波浪 | ~8s |
| `hip_circle()` | 扭臀画圆 | ~8s |
| `head_circle()` | 扭头画圆 | ~8s |

=== "Python"

    ```python
    robot.twirl_jump()
    robot.groove()
    robot.hip_circle()

    # 通用接口
    robot.atomic_action("body_wave")
    ```

=== "C++"

    ```cpp
    client.twirl_jump();
    client.groove();
    client.hip_circle();

    // 通用接口
    client.atomic_action("body_wave");
    ```

!!! info "轮足构型（MINI_QUAD_WHEEL）"
    这些动作仅支持点足构型（`is_quad() == True`）。

## 15. 视频流获取

想实时看到机器狗上的相机画面，可以这样做：先用 `open()` 把流开起来，它会返回一个
**可以直接播放的 RTSP 地址**；画面怎么显示、怎么解码由你决定——OpenCV、ffmpeg、
VLC、GStreamer 都能直接打开这个地址，SDK 不取帧、不解码。

相机：`CameraId.FRONT_RGB`（前置）、`CameraId.REAR_RGB`（后置）。

=== "Python"

    ```python
    from dobot_quad import CameraId, RobotClient

    robot = RobotClient("192.168.5.2:50051")
    uri = robot.video.open(CameraId.FRONT_RGB)   # 开流，等到真的在推数据才返回
    print(uri)                                   # rtsp://192.168.5.2:8554/camera1

    # 把地址交给任意播放器 / 解码器，例如
    #   cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
    #   ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay <uri>

    robot.video.close(CameraId.FRONT_RGB)        # 用完释放这一路
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"
    #include "video/video_client.h"     // 视频接口在这个头文件里

    robot::Client client("192.168.5.2:50051");
    std::string uri = client.video().open(robot::video::CameraId::FrontRgb);
    std::cout << uri << std::endl;              // rtsp://192.168.5.2:8554/camera1

    client.video().close(robot::video::CameraId::FrontRgb);
    ```

    用了视频功能就多 include 一个头 `video/video_client.h`，链接时多带一个
    `Threads::Threads`（视频模块是纯头文件，不需要别的库，也不依赖 gRPC）。Python
    不需要额外 include，功能就在现有的 `robot.video` 上。

!!! tip "OpenCV 记得设低延迟参数"
    OpenCV 只能通过环境变量传解码参数，且要在创建 `VideoCapture` **之前**设置，否则画面延迟会
    明显偏大：

    ```python
    import os

    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
        "|reorder_queue_size;0|probesize;32|analyzeduration;0")
    ```

    C++ 用同一个环境变量 `setenv(...)`；用播放器时等价写法是
    `ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay <uri>`。

完整的可运行示例（两个相机窗口、无窗口取帧）见[典型场景](../scenarios.zh.md#_1)。

### 15.1 全部接口

`robot.video` 一共 8 个方法，日常用到的主要是前两个。凡是需要指定相机的方法都带一个
`camera` 参数（`CameraId.FRONT_RGB` / `CameraId.REAR_RGB`）：

| 方法 | 作用 |
| ---- | ---- |
| `open()` | **开流并返回 RTSP 地址**：等到相机真的在推数据才返回（通常一瞬间，最坏约 8 秒）。同一相机重复调用很轻（**只增加引用计数**），返回同一个地址。 |
| `close()` | 释放这一路，**与 `open()` 一一配对**：引用计数归零、并且确认没有别人在看时才真的停流。退出前务必调用。 |
| `close_all()` | 释放全部本地状态（**不会让机器人停流**）。程序退出时推荐用它。 |
| `list_cameras()` | 列出可用相机（`CameraId` 列表）。 |
| `is_streaming()` | 这一路现在是否在推流。 |
| <code style="white-space:nowrap">get_stream_info()</code> | 读取这一路的信息：地址、谁开的流、码率、最近一次错误说明。`close()` 之后仍可读到最后一次状态。 |
| <code style="white-space:nowrap">on_state_change()</code> | 注册流事件回调（断流 / 被外部停掉 / 已恢复）。回调跑在 SDK 的线程上，不要在回调里调用 `open()`。 |
| `stop_stream()` | 强制停流，即使有人在看也会打断。拿不准时用 `close()`。 |

返回的数据对象只有两个：`CameraStreamInfo`（`get_stream_info()` 的结果）和
`StreamEvent`（回调参数）；出错时抛 `VideoError` 及其子类。

### 15.2 几条要知道的行为

- **`open()` 与 `close()` 是配对的（引用计数）。** 同一相机 `open()` 两次就要 `close()` 两次；
  只 `close()` 一次时流会继续推、也不会有任何事件——这不是故障。
- **首帧需要 1~2 秒。** `open()` 返回的地址已经能播，但你自己的解码器还要做 RTSP 握手和缓冲，
  这一阶段通常需要 1~2 秒，之后是稳定的约 30 fps、约 2.8 Mbps。
- **流可能已经在推了。** 如果相机已经在推流（例如手机 App 正在看画面），`open()`
  会直接采用这条流、不会重新开一遍；代价是要先确认一个采样间隔内 `bytes_recv`
  **在增长**（通常约 0.3 s），不是「看到有人推就算」。
- **卡住的流不会被采用。** 刚 `stop_stream()` 之后，流服务可能还留着正在关闭的
  producer（`bytes_recv` 是历史值、不再增长）：这时 `open()` 不会借它，而是自己
  下发一次 `start` 接管（通常约 0.5 s），避免把一个 404 的地址交给你的播放器。
- **`close()` 不会掐掉别人的画面。** 它只在确认没有其他人（手机 App、播放器）在看时
  才停流；要强制停用 `stop_stream()`。
- **断流会自愈。** 网络抖动、被外部停流等情况 SDK 会自动续流或重启，并通过
  `on_state_change()` 通知你；`get_stream_info().message` 会说明发生了什么。
- **网络要求。** 画面走 RTSP、端口 8554，开流用的 HTTP 服务是端口 22000 —— 运行程序的
  机器必须能访问到机器人（先 `ping <ip>` 确认一遍）。
- **异常类型按原因分。** 接不到机器人（`port_unreachable`）抛 `VideoConnectionError`，
  等不到数据（`no_data`）抛 `VideoTimeoutError`，相机参数不对抛
  `UnsupportedCameraError`；其余情况（卡住、被外部停掉、自己取消）是基类 `VideoError`。
  只 catch `VideoError` 也照常管用，细分是为了让你能分流处理。

## 三、示例程序详解

所有示例均提供 Python 和 C++ 两个版本，位于 `high_level/python/examples/` 和 `high_level/cpp/` 目录下。

### E1: 获取可用动作

列出服务端所有可用动作及其参数。

=== "Python"

    ```python
    from dobot_quad import RobotClient

    robot = RobotClient("192.168.5.2:50051")
    res = robot.get_motions()

    for m in res.motions:
        print(f"  [{m.motion_id}]")
        for p in m.parameters:
            print(f"      {p.key}: {p.float_value or p.int_value or p.string_value}")
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"

    robot::Client client("192.168.5.2:50051");
    auto res = client.get_motions();

    for (const auto& m : res.motions())
        std::cout << "  [" << m.motion_id() << "]" << std::endl;
    ```

### E2: 获取当前状态

=== "Python"

    ```python
    robot = RobotClient("192.168.5.2:50051")
    state = robot.get_current_state_name()
    print(f"当前状态: {state}")
    ```

=== "C++"

    ```cpp
    robot::Client client("192.168.5.2:50051");
    auto state = client.get_current_state_name();
    std::cout << "当前状态: " << state << std::endl;
    ```

### E3: 状态切换

支持命令行参数或交互式选择。程序会根据机器人类型自动显示对应的状态列表。

=== "Python（点足）"

    ```python
    robot.set_target_state("balance_stand")
    robot.walk()
    robot.flying_trot()
    robot.change_mode()
    ```

=== "Python（轮足）"

    ```python
    robot.wheel_loco()
    robot.drift()
    robot.handstand()
    robot.change_mode()
    ```

=== "C++（点足）"

    ```cpp
    client.balance_stand();
    client.walk();
    client.flying_trot();
    client.change_mode();
    ```

=== "C++（轮足）"

    ```cpp
    client.wheel_loco();
    client.drift();
    client.handstand();
    client.change_mode();
    ```

### E4: 速度序列

=== "Python（点足）"

    ```python
    steps = [
        (0.8, 0, 0, 2),   # 前进 2s
        (0, 0, 0, 1),     # 停止 1s
        (-0.8, 0, 0, 2),  # 后退 2s
        (0, 0, 0, 1),     # 停止 1s
    ]
    robot.velocity_sequence(steps, gait="walk", speed_ratio=60)
    # 也支持 flying_trot:
    robot.velocity_sequence(steps, gait="flying_trot")
    ```

=== "Python（轮足）"

    ```python
    steps = [
        (0.8, 0, 0, 2),    # 前进 2s
        (0, 0.3, 0, 2),    # 左移 2s
        (0, 0, 0.4, 2),    # 左转 2s
        (0, 0, 0, 1),      # 停止 1s
    ]
    robot.velocity_sequence(steps, gait="wheel_loco", speed_ratio=60)
    ```

=== "C++（点足）"

    ```cpp
    std::vector<robot::VelocityStep> steps = {
        {0.8f, 0, 0, 2},   // 前进 2s
        {0, 0, 0, 1},      // 停止 1s
        {-0.8f, 0, 0, 2},  // 后退 2s
        {0, 0, 0, 1},      // 停止 1s
    };
    client.velocity_sequence(steps, "walk", 60);
    ```

=== "C++（轮足）"

    ```cpp
    std::vector<robot::VelocityStep> steps = {
        {0.8f, 0, 0, 2},     // 前进 2s
        {0, 0.3f, 0, 2},     // 左移 2s
        {0, 0, 0.4f, 2},     // 左转 2s
        {0, 0, 0, 1},        // 停止 1s
    };
    client.velocity_sequence(steps, "wheel_loco", 60);
    ```

### E5: 机器人遥测

=== "Python"

    ```python
    res = robot.get_state()
    print(f"当前状态: {res.current_state}")
    print(f"速度比:   {res.current_speed_ratio}")

    s = res.robot_state
    print(f"机体位置: {list(s.pos_body)}")
    print(f"腿部力矩: {list(s.jtau_leg)}")
    ```

=== "C++"

    ```cpp
    auto res = client.get_state();
    std::cout << "当前状态: " << res.current_state() << std::endl;
    const auto& s = res.robot_state();
    // s.pos_body(), s.jtau_leg(), 等
    ```

### E6: 平衡动作

!!! warning "仅限点足"
平衡动作仅在点足机器人（miniQuad）上可用。轮足机器人调用时会提示不支持并退出。

=== "Python"

    ```python
    # 单轴函数（dynamic）
    robot.balance_pitch(15.0, 2.0, "dynamic")
    robot.balance_yaw(20.0, 2.0, "dynamic")
    robot.balance_roll(-15.0, 2.0, "dynamic")
    robot.balance_height(-0.05, 2.0, "dynamic")

    # 单轴函数（static）
    robot.balance_pitch(-15.0, 2.5, "static")
    robot.balance_yaw(-20.0, 2.5, "static")
    robot.balance_roll(15.0, 2.5, "static")
    robot.balance_height(-0.08, 2.5, "static")

    # balance_sequence
    robot.balance_sequence([
        ("balance_pitch", 15.0, 2.0, "dynamic"),
        ("balance_yaw", 20.0, 2.0, "dynamic"),
        ("balance_roll", -15.0, 2.0, "dynamic"),
        ("balance_height", -0.05, 2.0, "dynamic"),
        ("balance_neutral", 0.0, 0.5, "dynamic"),
    ])

    # 两个复合姿势
    robot.dynamic_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
    robot.static_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
    robot.balance_neutral()
    ```

=== "C++"

    ```cpp
    // 单轴函数（dynamic）
    client.balance_pitch(15.0f, 2.0f, "dynamic");
    client.balance_yaw(20.0f, 2.0f, "dynamic");
    client.balance_roll(-15.0f, 2.0f, "dynamic");
    client.balance_height(-0.05f, 2.0f, "dynamic");

    // 单轴函数（static）
    client.balance_pitch(-15.0f, 2.5f, "static");
    client.balance_yaw(-20.0f, 2.5f, "static");
    client.balance_roll(15.0f, 2.5f, "static");
    client.balance_height(-0.08f, 2.5f, "static");

    // balance_sequence
    client.balance_sequence({
        {"balance_pitch", 15.0f, 2.0f, "dynamic"},
        {"balance_yaw", 20.0f, 2.0f, "dynamic"},
        {"balance_roll", -15.0f, 2.0f, "dynamic"},
        {"balance_height", -0.05f, 2.0f, "dynamic"},
        {"balance_neutral", 0.0f, 0.5f, "dynamic"},
    });

    // 两个复合姿势
    client.dynamic_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.static_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.balance_neutral();
    ```

### E7: 直线行走

=== "Python"

    ```python
    robot.walk_forward(2.0)       # 向前 2m（最大 3m）
    robot.walk_backward(1.5)      # 向后 1.5m
    robot.move_left(1.0)          # 向左 1m（原 walk_left）
    robot.move_right(1.0)         # 向右 1m（原 walk_right）

    # 使用通用接口:
    robot.line_walk("forward", 2.0)
    robot.line_walk(2, 1.0)       # direction=2 (left)
    ```

=== "C++"

    ```cpp
    client.walk_forward(2.0);       // 向前 2m（最大 3m）
    client.walk_backward(1.5);      // 向后 1.5m
    client.move_left(1.0);          // 向左 1m（原 walk_left）
    client.move_right(1.0);         // 向右 1m（原 walk_right）

    // 使用通用接口:
    client.line_walk(0, 2.0);       // direction=0 (forward)
    ```

### E8: 旋转

=== "Python"

    ```python
    robot.rotate("left", 90)         # 左转 90°
    robot.rotate_right(45)           # 右转 45°
    robot.circle("left", turns=3)    # 左转 3 圈（最大 10 圈）
    robot.rotate_walk(-45, 2.0)      # 朝 -45° 方向走 2m（向左）
    ```

=== "C++"

    ```cpp
    client.rotate("left", 90);       // 左转 90°
    client.rotate_right(45);         // 右转 45°
    client.circle("left", 3);        // 左转 3 圈（最大 10 圈）
    client.rotate_walk(-45, 2.0);    // 朝 -45° 方向走 2m（向左）
    ```

### E9: 组合序列

Arduino 风格的顺序阻塞调用 — 每个函数会阻塞直到动作完成。程序会根据机器人类型执行不同的流程。

=== "Python（点足）"

    ```python
    # 全流程：状态切换 + change_mode + 运动 + 平衡
    robot.passive(); robot.ready(); robot.balance_stand()
    robot.walk(); robot.change_mode(); robot.change_mode()

    robot.walk_forward(1.0); robot.walk_backward(1.0)
    robot.move_left(1.0); robot.move_right(1.0)

    robot.rotate_left(90); robot.rotate_left(180)
    robot.rotate_right(90); robot.rotate_right(180)
    robot.circle("left", 1)

    robot.balance_pitch(15.0, 2.0, "dynamic"); robot.balance_pitch(-15.0, 2.5, "static")
    robot.balance_yaw(20.0, 2.0, "dynamic");   robot.balance_yaw(-20.0, 2.5, "static")
    robot.balance_roll(15.0, 2.0, "dynamic");  robot.balance_roll(-15.0, 2.5, "static")
    robot.balance_height(-0.05, 2.0, "dynamic"); robot.balance_height(-0.08, 2.5, "static")

    robot.dynamic_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
    robot.static_pose(3.0, roll_deg=10, pitch_deg=10, yaw_deg=15, height_m=-0.05)
    robot.balance_neutral()

    robot.wave_hand(); robot.dance(); robot.recovery()
    robot.stand_down()
    ```

=== "Python（轮足）"

    ```python
    # 轮足全流程：状态切换 + 运动
    robot.passive(); robot.ready()
    robot.wheel_loco()
    robot.change_mode(); robot.change_mode()

    robot.walk_forward(1.0); robot.walk_backward(1.0)
    robot.move_left(1.0); robot.move_right(1.0)

    robot.rotate_left(90); robot.rotate_right(90)
    robot.circle("left", 1)

    # 轮足专用状态切换
    robot.drift()
    robot.wheel_loco()
    robot.handstand()

    robot.stand_down()
    ```

=== "C++（点足）"

    ```cpp
    // 全流程：状态切换 + change_mode + 运动 + 平衡
    client.passive(); client.ready(); client.balance_stand();
    client.walk(); client.change_mode(); client.change_mode();

    client.walk_forward(1.0f); client.walk_backward(1.0f);
    client.move_left(1.0f); client.move_right(1.0f);

    client.rotate_left(90.0f); client.rotate_left(180.0f);
    client.rotate_right(90.0f); client.rotate_right(180.0f);
    client.circle("left", 1);

    client.balance_pitch(15.0f, 2.0f, "dynamic"); client.balance_pitch(-15.0f, 2.5f, "static");
    client.balance_yaw(20.0f, 2.0f, "dynamic");   client.balance_yaw(-20.0f, 2.5f, "static");
    client.balance_roll(15.0f, 2.0f, "dynamic");  client.balance_roll(-15.0f, 2.5f, "static");
    client.balance_height(-0.05f, 2.0f, "dynamic"); client.balance_height(-0.08f, 2.5f, "static");

    client.dynamic_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.static_pose(3.0f, 10.0f, 10.0f, 15.0f, -0.05f);
    client.balance_neutral();

    client.wave_hand(); client.dance(); client.recovery();
    client.stand_down();
    ```

=== "C++（轮足）"

    ```cpp
    // 轮足全流程：状态切换 + 运动
    client.passive(); client.ready();
    client.wheel_loco();
    client.change_mode(); client.change_mode();

    client.walk_forward(1.0f); client.walk_backward(1.0f);
    client.move_left(1.0f); client.move_right(1.0f);

    client.rotate_left(90.0f); client.rotate_right(90.0f);
    client.circle("left", 1);

    // 轮足专用状态切换
    client.drift();
    client.wheel_loco();
    client.handstand();

    client.stand_down();
    ```

### E10: 配置演示

=== "Python"

    ```python
    # 查询当前速度比（返回本地跟踪值）
    sr = robot.get_speed_ratio()
    print(f"速度比: {sr}")

    # 设置基础速度比
    robot.set_speed_ratio(30)

    # 不指定 speed_ratio，使用当前基础值 (30)
    robot.walk_forward(2.0)

    # 显式指定 speed_ratio=100，临时覆盖，执行后恢复为 30
    robot.walk_forward(2.0, speed_ratio=100)

    # 避障开关
    robot.set_obstacle_avoidance(True)    # 或 "on"
    robot.set_obstacle_avoidance(False)   # 或 "off"
    ```

=== "C++"

    ```cpp
    // 查询当前速度比（返回本地跟踪值）
    int sr = client.get_speed_ratio();
    std::cout << "速度比: " << sr << std::endl;

    // 设置基础速度比
    client.set_speed_ratio(30);

    // 不指定 speed_ratio，使用当前基础值 (30)
    client.walk_forward(2.0);

    // 显式指定 speed_ratio=100，临时覆盖，执行后恢复为 30
    client.walk_forward(2.0, 100);

    // 避障开关
    client.set_obstacle_avoidance(true);
    client.set_obstacle_avoidance("off");
    ```

### E11: 腿灯控制演示

=== "Python"

    ```python
    from dobot_quad import Leg, Color

    # 全部设为绿色
    robot.set_all_legs_color(Color.GREEN)

    # 前腿白色，后腿蓝色
    robot.set_legs_rgb([Leg.FL, Leg.FR], Color.WHITE)
    robot.set_legs_rgb([Leg.RL, Leg.RR], Color.BLUE)

    # 恢复默认灯光
    robot.reset_legs()
    ```

=== "C++"

    ```cpp
    // 全部设为绿色
    client.set_all_legs_color(Color::GREEN);

    // 前腿白色，后腿蓝色
    client.set_legs_rgb({Leg::FL, Leg::FR}, Color::WHITE);
    client.set_legs_rgb({Leg::RL, Leg::RR}, Color::BLUE);

    // 恢复默认灯光
    client.reset_legs();
    ```

### E12: 视频流获取

    ```bash
    # Python
    python examples/e12_video_stream.py 192.168.5.2:50051 --pull
    # C++
    ./e12_video_stream 192.168.5.2:50051 --camera front --pull
    ```

`--pull` 会用 ffmpeg 打开返回的地址，说明这个地址能被任意标准播放器使用。脚本
本身只是几行 API 调用（见 [15. 视频流获取](#15)）。

## 参数范围速查表

| 参数                            | 范围                                                 | 涉及函数                                                             |
| ------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------- |
| speed_ratio                     | [10, 100]                                            | set_speed_ratio；可选覆盖: line_walk, velocity_sequence, rotate_walk |
| distance                        | **[0, 3] m**                                         | walk_forward, walk_backward, move_left, move_right, rotate_walk      |
| angle (rotate)                  | [0, 3600]°                                            | rotate, rotate_left, rotate_right                                    |
| angle (rotate_walk)             | **[-180, 180]°**                                     | rotate_walk                                                          |
| turns                           | **[1, 10]**                                          | circle                                                               |
| balance value (rpy)             | roll: [-17.0, 17.0]°, pitch: [-11.5, 11.5]°, yaw: [-11.5, 11.5]° | balance_pitch/yaw/roll, balance_sequence                             |
| balance value (height)          | [-0.08, 0] m                                         | balance_height, balance_sequence                                     |
| balance duration                | [0.5, 5] s                                           | 所有 balance\_\* 函数                                                |
| dynamic_pose / static_pose 角度 | roll: [-17.0, 17.0]°, pitch: [-11.5, 11.5]°, yaw: [-11.5, 11.5]° | dynamic_pose, static_pose                                            |
| dynamic_pose / static_pose 高度 | [-0.08, 0] m                                         | dynamic_pose, static_pose                                            |
| dynamic_pose / static_pose 时长 | [1, 5] s                                             | dynamic_pose, static_pose                                            |
| obstacle_avoidance              | bool / "on" / "off"                                  | set_obstacle_avoidance                                               |
