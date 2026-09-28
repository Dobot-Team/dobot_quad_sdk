# 更新日志

## v1.3.0 — 腿灯控制、原子编舞动作及文档修复

### 新功能

#### 高层腿灯控制
用户现可通过高层 API 独立控制机器狗四条腿上的 RGB 灯。设置任一腿灯即覆盖机器狗内置灯光逻辑；调用 `reset_legs()` 后恢复默认灯光。

- `set_legs_rgb(legs, color)` — 批量设置腿灯颜色（OFF、RED、ORANGE、YELLOW、GREEN、CYAN、BLUE、PURPLE、WHITE）
- `set_leg_rgb(leg, r, g, b)` — 设置单腿原始 RGB 值
- `set_leg_color(leg, color)` — 设置单腿为指定颜色
- `set_leg_brightness(leg, brightness)` — 调整单腿亮度（0–255）
- `set_all_legs_rgb(r, g, b)` / `set_all_legs_color(color)` — 一键设置全部腿灯
- `reset_legs()` — 恢复默认灯光

腿灯标识：`Leg.FL`、`Leg.FR`、`Leg.RL`、`Leg.RR`。示例见 `high_level/python/examples/e11_led_control.py` / `high_level/cpp/e11_led_control.cpp`。

#### 原子编舞动作（仅点足构型）
新增八个编舞动作：`twirl_jump()`、`diag_step()`、`hop_step()`、`groove()`、`bounce()`、`body_wave()`、`hip_circle()`、`head_circle()`。各动作自动处理状态切换，完成后返回 `WALK` 模式。也可通过 `atomic_action("name")` 调用。

#### 视频流获取（`robot.video`）

前 / 后两路 RGB 相机都可以拿地址，交给自己的播放器或算法看画面。SDK 负责把流
开起来、盯住它、返回 RTSP 地址，不做解码，因此没有引入任何媒体依赖。

- `video.open(camera)` —— 阻塞到相机确实在推数据，返回
  `rtsp://<ip>:8554/camera1`（前置）/ `.../camera2`（后置）；已在推的相机直接采用，
  重复调用很轻且返回同一个地址。
- `video.is_streaming(camera)` / `video.get_stream_info(camera)` —— 状态、地址、
  流是谁开的、当前码率。
- `video.on_state_change(cb)` —— 流事件（断流 / 被外部停掉 / 已恢复）。
- `video.close(camera)` / `close_all()` —— 只有确认没人看时才停流，不会打断手机 App。
- `video.stop_stream(camera)` —— 强制让本体停止推流。
- 断流自动续流、卡住自动重启，无需任何配置。
- C++ 侧**纯头文件**（`robot_client.h` 再加 `video/video_client.h`），没有库要链接、
  也不依赖 gRPC；Python 侧就在现有客户端的 `robot.video` 上，零额外依赖。
- 示例：`high_level/python/examples/e12_video_stream.py`、
  `high_level/cpp/e12_video_stream.cpp`。

### 变更

- **`choreo()` 更名为 `gongxi()`**：原 `choreo` 状态统一更名为 `gongxi`（恭喜），更准确反映动作语义；增加了 11.5 秒触发后等待。**旧名称保留可用**：Python `RobotClient.choreo()`、C++ `Client::choreo()` / `Client::set_choreo()` 均转发到 `gongxi()` 并发出废弃告警；`set_target_state("choreo")` 也会自动映射到 `gongxi`。
- **URDF 模型文件**：更新了点足和轮足构型的机器人模型定义。

### 文档修复

- 新增**典型场景**页：可直接复制的示例（在电脑上实时看两路相机、把每帧交给自己的
  算法）
- 高层 API 文档补充视频功能的头文件与链接说明（2.15 节）

- 修复 README 中指向不存在 `doc/` 目录的损坏链接
- 更新 README 项目结构以反映实际目录
- 修正 API 文档中 balance 值范围和 rotate angle 范围以对齐代码实际限制
- 修正 `clamp_angle_signed` 代码注释中方向符号错误
- 删除底层文档 LED 表中不存在的 `fill_light2` 条目
- 修复中文底层文档示例输出格式错误
- 修正 v1.0.9 更新日志中不完整句子

### 示例修复

- E7 语音发布（Python/C++）：移除硬编码音频路径 `/root/test2.flac`，改为接受命令行参数指定文件路径
- E8 语音订阅（Python）：补全 WAV 文件录制功能（此前仅有声明未实现）
- E8 语音订阅（Python/C++）：修正注释中的示例编号从 `e9` 为 `E8`；移除未使用的导入

## v1.2.0 — 机器人作揖 / 编舞动作 & DDS 中间件更新

- 新增四足机器人 `choreo` 状态支持。
- 新增 Python `RobotClient.choreo()` 和 C++ `RobotClient::choreo()` / `RobotClient::set_choreo()` 接口。
- 在自动状态切换示例和状态切换测试中加入 `choreo` 状态。
- 将内置 DDS 中间件包从 `0.22.10` 更新到 `0.23.3`，支持 `amd64` 和 `arm64`。
- 更新 C++ 和 Python `e7_voice_pub` 示例，适配 `dds-middleware >= 0.23.x` 使用的 `VoiceCmd` 消息结构。
- 重新生成英文、中文 API 文档和静态网页。

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
