# 更新日志

## v1.1.0 — 文档迁移 & DDS中间件更新

- 迁移doc相关文档到docs目录，新增静态网页功能
- dist目录包更新到v0.22.10
- low_level文档中新增后置相机的数据获取话题

## v1.0.9 — 平衡参数重构 & 复合姿势 & 安全处理器

- `dynamic_pose(duration, roll_deg, pitch_deg, yaw_deg, height_m)` — 复合正弦姿势
- `static_pose(duration, roll_deg, pitch_deg, yaw_deg, height_m)` — 复合保持姿势
- `ready()` — 缓慢趴下（安全停止）状态
- `emergency()` — `passive()` 的别名
- `change_mode()` — 行走⇄奔跑平滑切换
- `enable_safety_ready()` — Ctrl+C 时自动 `ready()`
- 平衡动作参数：`amplitude/beats` → `value（度/米）, duration（秒）, mode（"dynamic"/"static"）`
- `set_bpm()` / `bpm()` — BPM 不再使用，计时基于秒
- 构造函数和 `execute()` 中的 `bpm` 参数

## v1.0.8 — 速度比本地跟踪 & 可选覆盖

- `speed_ratio` 参数默认值从 `80` 改为 `None` (Python) / `-1` (C++)，省略时使用当前基础值
- `get_speed_ratio()` 和 `get_obstacle_avoidance()` 现在返回本地跟踪值，不再查询服务端
- 构造函数通过 `get_state()` 获取初始速度比，本地存储

## v1.0.6 — 需求端接口规范对齐

- `walk_left()` → `move_left()`
- `walk_right()` → `move_right()`
- 行走距离上限 10m → **3m**
- circle 圈数上限 5 → **10**
- rotate_walk 距离上限 10m → **3m**
- `x_leg("std"/"x")` 腿部构型切换
- 可复用参数校验工具函数（`clamp_distance`, `clamp_angle` 等）
- C++ `set_` 前缀（`set_balance_stand()` → `balance_stand()`）
- `rl` 步态
- C++ 构造函数中 `set_speed_ratio(0)` 改为 `get_speed_ratio()`

## v1.0.0 — 初始版本

- Python `set_` 前缀移除、`rl` 步态移除
- 参数范围校验、方向字符串支持
- ARM 字段移除
- 完整测试套件（230 tests）
