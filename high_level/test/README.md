# Robot Client Test Suite

单元测试覆盖 `dobot_quad/robot_client.py` 和 `robot_client.h` 的全部公开 API。  
## 运行方式

### Python 单元测试
```bash
cd high_level/test/python
pip install pytest grpcio grpcio-tools
pytest -v
```


### C++ 单元测试 (需要 gRPC 和 GTest)
```bash
cd high_level/test/cpp
mkdir build && cd build
cmake .. -DCMAKE_PREFIX_PATH=<your_grpc_install>
make -j
ctest --output-on-failure
```

## 测试策略

| 分类 | 测试重点 | 是否需要真实服务端 |
|---|---|---|
| 参数校验 / 钳位 | `set_speed_ratio`, `rotate`, `circle`, `rotate_walk`, `dynamic_pose` 的范围钳位 | ❌ Mock |
| 异常输入 | `set_obstacle_avoidance("bad")`, `rotate("up")` 的错误抛出 | ❌ Mock |
| RPC 参数构造 | `execute`, `line_walk`, `velocity_sequence`, `balance_sequence` 的 proto 构造正确性 | ❌ Mock |
| 查询接口 | `get_state`, `get_motions`, `get_speed_ratio`, `get_obstacle_avoidance` 的返回值 | ❌ Mock |
| 状态切换 | `passive`/`emergency`/`ready` 等状态方法 + `change_mode` | ❌ Mock |
| LED 单元测试 | `test_led.py` 对 SetLeds/ResetLeds 的 mock 断言 | ❌ Mock |
| 腿灯联调 | `led_joint_test` 连续控灯 / 颜色 / 亮度 / reset 人眼判定 | ✅ 真机或 mock |

## 文件清单

### Python (`test/python/`)
| 文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `conftest.py` | — | Mock fixtures (stub, responses) |
| `test_constructor.py` | 3 | 构造器、缓存初始化、上下文管理器 |
| `test_query.py` | 13 | `get_state`, `get_motions`, `get_current_state_name`, `get_speed_ratio`, `get_obstacle_avoidance` + 缓存行为 |
| `test_config.py` | 14+ | `set_speed_ratio` 钳位 (8 组参数)、`set_obstacle_avoidance` 字符串/bool/非法输入 (9 组) |
| `test_execution.py` | 11 | `execute` 单/多动作、元组参数、`make_velocity_string`、`velocity_sequence` (gait, stand_down_after) |
| `test_state_switching.py` | 18+ | `set_target_state`、预定义状态（含 emergency/ready）、积木别名、`change_mode`、已移除方法检查 |
| `test_locomotion.py` | 8 | `line_walk`、4 个方向快捷方法、speed_ratio 保存/恢复 |
| `test_rotation.py` | 20+ | `rotate` 方向/角度钳位、`circle` 圈数钳位、`rotate_walk` 角度+距离双钳位、左右快捷 |
| `test_balance.py` | 12 | `balance_pitch/yaw/roll/height/neutral`（value/duration/mode）、`balance_sequence` 批量、`dynamic_pose`、`dance` |
| `test_led.py` | 25+ | `set_legs_rgb`/`set_leg_rgb`/`set_leg_color`/`set_leg_brightness`/`set_all_legs_*`/`turn_off_leg`/`reset_legs`、RGB 校验、缓存行为、RPC 错误 |
| `led_joint_test.py` | 交互联调 | TC-CONT/CTRL/COLOR/BRI/RST 等；不跑 pytest |

### C++ (`test/cpp/`)
| 文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `CMakeLists.txt` | — | CMake 配置 (FetchContent GoogleTest) + `led_joint_test` 目标 |
| `test_robot_client.cpp` | 50+ | `make_request` 默认值、`set_param` 三类型、`VelocityStep`/`BalanceMotion` 结构体（value/duration/mode）、`make_velocity_string` 序列化、5 组参数钳位 (speed_ratio, angle, turns, distance, duration)、方向校验、balance value 钳位、`LegLedConfig`/`Leg`/`Color`/`color_to_rgb`/`leg_to_proto`/`scale_rgb_by_brightness` |
| `led_joint_test.cpp` | 交互联调 | 与 Python `led_joint_test.py` 对称；不进 ctest |
