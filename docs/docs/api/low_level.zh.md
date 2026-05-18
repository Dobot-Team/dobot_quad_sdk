# 底层 API 文档

本文档详细介绍 Dobot Quad SDK 的底层控制层（DDS）API，包括各示例程序的功能、QoS 配置、原理和使用方法。底层控制层基于 CycloneDDS 实现，提供直接访问机器人硬件的能力：

- **传感器订阅**：IMU、电机状态、电池状态、图像等
- **执行器控制**：LED 灯光、电机指令、语音播放
- **低延迟通信**：毫秒级实时数据传输

## 一、初始化

```python
import dds_middleware_python as dds

# 使用配置文件初始化
middleware = dds.PyDDSMiddleware("config/dds_config.yaml")

# 或使用 Domain ID 初始化
middleware = dds.PyDDSMiddleware(0)
```

## 二、QoS 配置说明

DDS 的 QoS (Quality of Service) 配置决定了数据传输的可靠性和性能特性。

### 2.1 默认配置文件

配置文件位于 `low_level/python/config/dds_config.yaml`：

| 配置项          | Writer 默认值 | Reader 默认值 | 说明         |
| --------------- | ------------- | ------------- | ------------ |
| `domain_id`     | 0             | 0             | DDS 域 ID    |
| `reliability`   | `reliable`    | `best_effort` | 可靠性策略   |
| `history_kind`  | `keep_last`   | `keep_last`   | 历史记录类型 |
| `history_depth` | 10            | 10            | 历史记录深度 |
| `durability`    | `volatile`    | `volatile`    | 持久性策略   |
| `liveliness`    | `automatic`   | `automatic`   | 存活性策略   |
| `deadline`      | `infinite`    | `infinite`    | 截止时间     |

### 2.2 QoS 参数说明

| 参数            | 可选值                         | 说明                                                    |
| --------------- | ------------------------------ | ------------------------------------------------------- |
| `reliability`   | `reliable` / `best_effort`     | reliable 保证数据到达，best_effort 允许丢包             |
| `history_kind`  | `keep_last` / `keep_all`       | keep_last 只保留最新 N 条，keep_all 保留所有            |
| `history_depth` | 整数                           | 保留的历史消息数量                                      |
| `durability`    | `volatile` / `transient_local` | volatile 不保存历史，transient_local 保存给后来的订阅者 |

### 2.3 推荐配置

| 场景           | Reliability | History Depth | 说明                 |
| -------------- | ----------- | ------------- | -------------------- |
| 实时传感器数据 | best_effort | 1-5           | 低延迟，允许丢包     |
| 控制指令       | reliable    | 1-5           | 保证到达             |
| 图像数据       | best_effort | 1-5           | 大数据量，优先低延迟 |

## 三、示例程序详解

### E1: RGB 图像订阅

**文件**: `low_level/python/e1_rgb_image_sub.py`

#### 功能说明

从机器人相机订阅压缩的 RGB 彩色图像数据。

#### QoS 配置

```python
# 使用配置文件中的默认 reader QoS
# reliability: best_effort
# history_kind: keep_last
# history_depth: 10
# durability: volatile
```

#### 订阅话题

| 话题名称                             | 消息类型          | 说明                    |
| ------------------------------------ | ----------------- | ----------------------- |
| `rt/camera/camera2/image_compressed` | `CompressedImage` | 压缩的 RGB 图像（前置） |
| `rt/camera/camera3/image_compressed` | `CompressedImage` | 压缩的 RGB 图像（后置） |

#### 图像保存功能

示例程序会自动将接收到的图像保存到 `rgb_images/` 目录：

**Python 版本：**

- 使用 OpenCV (`cv2.imdecode`) 将压缩的 JPEG 数据解码为原始图像格式
- 保存为无损的 PNG 格式以获得更好的质量
- 文件名格式：`rgb_{时间戳秒}_{时间戳纳秒}.png`

**C++ 版本：**

- 使用 `cv::imdecode` 将压缩数据解码为 `cv::Mat`
- 使用 `cv::imwrite` 保存为 PNG 格式
- 与 Python 版本相同的文件名格式

#### 示例代码

```python
import dds_middleware_python as dds
import cv2
import numpy as np
import os

def image_callback(data):
    print(f"Received RGB CompressedImage:")
    print(f"  Timestamp: {data.header().stamp().sec()}.{data.header().stamp().nanosec():09d} (sec.nanosec)")
    print(f"  Frame ID: {data.header().frame_id()}")
    print(f"  Format: {data.format()}")
    print(f"  Data size: {len(data.data())} bytes")

    # 解码压缩图像
    np_arr = np.array(data.data(), dtype=np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image is not None:
        filename = f"rgb_images/rgb_{data.header().stamp().sec()}_{data.header().stamp().nanosec()}.png"
        cv2.imwrite(filename, image)
        print(f"Saved raw image to {filename}")

# 创建保存目录
os.makedirs("rgb_images", exist_ok=True)

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeCompressedImage("rt/camera/camera2/image_compressed", image_callback)
```

#### 输出示例

```
Subscribed to RGB image topic. Waiting for messages...
Received RGB CompressedImage:
  Timestamp: 1706000000.123456789 (sec.nanosec)
  Frame ID: camera2_optical_frame
  Format: jpeg
  Data size: 45678 bytesSaved raw image to rgb_images/rgb_1706000000_123456789.png---
  ...
```

#### 运行方式

```bash
cd low_level/python
python3 e1_rgb_image_sub.py
```

### E2: 深度图像订阅

**文件**: `low_level/python/e2_depth_image_sub.py`

#### 功能说明

从机器人深度相机订阅原始深度图像数据。

#### QoS 配置

```python
qos_config = {
    "reliability": "best_effort",
    "history_kind": "keep_last",
    "history_depth": 5,
    "durability": "volatile"
}
```

#### 订阅话题

| 话题名称                        | 消息类型 | 说明                 |
| ------------------------------- | -------- | -------------------- |
| `rt/camera/camera2/image_depth` | `Image`  | 原始深度图像（前置） |
| `rt/camera/camera3/image_depth` | `Image`  | 原始深度图像（后置） |

#### 深度图像可视化

示例程序会处理深度图像并保存到 `depth_images/` 目录：

**可视化处理：**

1. **归一化**：使用 `cv2.normalize` 将深度值拉伸到 0-255 范围
2. **伪彩色**：应用 Jet 色图（红色/暖色 = 近处，蓝色/冷色 = 远处）
3. **保存**：将处理后的可视化图像保存为 PNG 文件

**Python 版本：**

- 使用 `view(np.uint16)` 将原始字节转换为 numpy 数组
- 使用 OpenCV 应用归一化和色图
- 文件名格式：`depth_{时间戳秒}_{时间戳纳秒}.png`

**C++ 版本：**

- 直接从原始数据指针创建 `cv::Mat`
- 使用 `cv::normalize` 和 `cv::applyColorMap` 进行可视化
- 与 Python 版本相同的文件名格式

#### 示例代码

```python
import dds_middleware_python as dds
import cv2
import numpy as np
import os

def depth_image_callback(depth_msg):
    print(f"Received Image message:")
    print(f"  Timestamp: {depth_msg.header().stamp().sec()}.{depth_msg.header().stamp().nanosec():09d}")
    print(f"  Frame ID: {depth_msg.header().frame_id()}")
    print(f"  Encoding: {depth_msg.encoding()}")
    print(f"  Data size: {len(depth_msg.data())} bytes")

    if "16UC1" in depth_msg.encoding():
        # 转换为 16 位深度图
        raw_data = np.array(depth_msg.data(), dtype=np.uint8)
        depth_img = raw_data.view(np.uint16).reshape((depth_msg.height(), depth_msg.width()))

        # 归一化并应用色图
        depth_vis = cv2.normalize(depth_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

        filename = f"depth_images/depth_{depth_msg.header().stamp().sec()}_{depth_msg.header().stamp().nanosec()}.png"
        cv2.imwrite(filename, depth_color)
        print(f"Saved visibility depth map to {filename}")

# 创建保存目录
os.makedirs("depth_images", exist_ok=True)

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeImage("rt/camera/camera2/image_depth", depth_image_callback, qos_config)
```

#### 输出示例

```
Starting DDS Python Image subscriber...
Subscribing to topic: rt/camera/camera2/image_depth
Using QoS config: {'reliability': 'best_effort', 'history_kind': 'keep_last', 'history_depth': 5, 'durability': 'volatile'}
Image subscriber started, waiting for messages...
Received Image message:
  Timestamp: 1706000000.123456789
  Image size: 640x480
  Encoding: 16UC1
  Data size: 614400 bytes
  Step: 1280
  Big endian: False
...
```

#### 运行方式

```bash
cd low_level/python
python3 e2_depth_image_sub.py
```

### E3: LED 灯光控制

**文件**: `low_level/python/e3_led_control_pub.py`

#### 功能说明

控制机器人上的 6 个 LED 灯，支持 RGB 颜色设置和呼吸灯效果。

#### ⚠️ 重要警告

**在运行此程序之前，必须先停止机器人的主控程序！** 否则 LED 控制在当前版本中可能不生效。

停止主控程序的方法（推荐使用 SDK 提供的工具）：

```bash
# 推荐方法：使用 kill_robot 工具
cd high_level/python
python3 kill_robot.py 192.168.5.2:50051

# 或使用 C++ 版本
cd high_level/cpp/build
./kill_robot 192.168.5.2:50051
```

`kill_robot` 工具会安全地将机器人切换到 PASSIVE 状态并终止控制器进程。详见 [安全关闭章节](../../getting-started/quickstart/#_6)。

#### QoS 配置

```python
qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}
```

#### 发布话题

| 话题名称      | 消息类型  | 说明         |
| ------------- | --------- | ------------ |
| `rt/leds/cmd` | `LedsCmd` | LED 控制指令 |

#### LED 名称

| LED 名称      | 位置     | 说明               |
| ------------- | -------- | ------------------ |
| `leg_light1`  | 腿部灯 1 | -                  |
| `leg_light2`  | 腿部灯 2 | -                  |
| `leg_light3`  | 腿部灯 3 | -                  |
| `leg_light4`  | 腿部灯 4 | -                  |
| `fill_light1` | 前照灯   | 机器人前方的照明灯 |
| `fill_light2` | 补光灯 2 | 暂未开放功能       |
| `fill_light3` | 后照灯   | 机器人后方的照明灯 |

#### 示例代码

```python
import dds_middleware_python as dds
import math
import time

middleware = dds.PyDDSMiddleware(0)

qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}

middleware.createLedsCmdWriter("rt/leds/cmd", qos_config)

# 创建 LED 控制命令
led_cmd = dds.LedsCmd()
leds = []

# LED1 - 红色
led1 = dds.LEDControl()
led1.name("leg_light1")
led1.mode(0)  # RGB 模式
led1.brightness(255)
led1.r(255)
led1.g(0)
led1.b(0)
led1.priority(0)
leds.append(led1)

led_cmd.leds(leds)
middleware.publishLedsCmd(led_cmd)
```

#### 输出示例

```
LED control publisher started, press Ctrl+C to exit...
Published LED control command: Intensity: 50% LED1 (R:127 G:0 B:0) LED2 (R:0 G:127 B:0) ...
Published LED control command: Intensity: 100% LED1 (R:255 G:0 B:0) LED2 (R:0 G:255 B:0) ...
Program finished after 15000ms
```

#### 运行方式

```bash
cd low_level/python
python3 e3_led_control_pub.py
```

---

### E4: IMU 数据订阅

**文件**: `low_level/python/e4_imu_state_sub.py`

#### 功能说明

从底层直接获取 IMU（惯性测量单元）的原始数据，包括四元数、陀螺仪和加速度计数据。

#### QoS 配置

```python
# 使用配置文件中的默认 reader QoS
# reliability: best_effort
# history_kind: keep_last
# history_depth: 10
# durability: volatile
```

#### 订阅话题

| 话题名称         | 消息类型     | 说明                      |
| ---------------- | ------------ | ------------------------- |
| `rt/lower/state` | `LowerState` | 底层状态（包含 IMU 数据） |

#### 数据字段说明

| 字段            | 类型     | 单位  | 说明                      |
| --------------- | -------- | ----- | ------------------------- |
| `quaternion`    | float[4] | -     | 姿态四元数 [w, x, y, z]   |
| `gyroscope`     | float[3] | rad/s | 陀螺仪角速度 [x, y, z]    |
| `accelerometer` | float[3] | m/s²  | 加速度计 [x, y, z]        |
| `rpy`           | float[3] | rad   | 欧拉角 [roll, pitch, yaw] |

#### 示例代码

```python
import dds_middleware_python as dds
import time

def lower_state_callback(state):
    imu_state = state.imu_state()
    print(f"IMU State:")
    print(f"  Quaternion: {list(imu_state.quaternion())}")
    print(f"  Gyroscope (rad/s): {list(imu_state.gyroscope())}")
    print(f"  Accelerometer (m/s²): {list(imu_state.accelerometer())}")
    print(f"  RPY (roll, pitch, yaw in rad): {list(imu_state.rpy())}")

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeLowerState("rt/lower/state", lower_state_callback)
```

#### 输出示例

```
Received LowerState #100
IMU State:
  Quaternion: [0.9998, 0.0012, -0.0156, 0.0023]
  Gyroscope (rad/s): [0.0021, -0.0034, 0.0012]
  Accelerometer (m/s²): [0.12, -0.08, 9.78]
  RPY (roll, pitch, yaw in rad): [0.0024, -0.0312, 0.0046]
```

#### 运行方式

```bash
cd low_level/python
python3 e4_imu_state_sub.py
```

### E5: 电机状态订阅

**文件**: `low_level/python/e5_motor_state_sub.py`

#### 功能说明

从底层直接获取 16 个电机（对于点足式四足机器狗来说有四个足端电机为无效数据）的状态数据，包括位置、速度、力矩和温度等信息。

#### QoS 配置

```python
# 使用配置文件中的默认 reader QoS
# reliability: best_effort
# history_kind: keep_last
# history_depth: 10
# durability: volatile
```

#### 订阅话题

| 话题名称         | 消息类型     | 说明                     |
| ---------------- | ------------ | ------------------------ |
| `rt/lower/state` | `LowerState` | 底层状态（包含电机数据） |

#### 电机数据字段说明

| 字段         | 类型  | 单位   | 说明                                                 |
| ------------ | ----- | ------ | ---------------------------------------------------- |
| `mode`       | uint8 | -      | 模式：0-失能, 1-报错, 2-掉线, 3-使能, 4-受控, 5-回零 |
| `q`          | float | rad    | 角位置                                               |
| `dq`         | float | rad/s  | 角速度                                               |
| `ddq`        | float | rad/s² | 角加速度                                             |
| `tau_est`    | float | Nm     | 估计力矩                                             |
| `q_raw`      | float | rad    | 原始角位置                                           |
| `dq_raw`     | float | rad/s  | 原始角速度                                           |
| `ddq_raw`    | float | rad/s² | 原始角加速度                                         |
| `motor_temp` | uint8 | °C     | 电机温度                                             |

#### 电机编号

机器人有 16 个电机，编号 0-15，分布在四条腿上（点足式四足机器狗只有12个电机）：

| 腿部   | 电机编号       |
| ------ | -------------- |
| 前左腿 | 0, 1, 2, 3     |
| 前右腿 | 4, 5, 6, 7     |
| 后左腿 | 8, 9, 10, 11   |
| 后右腿 | 12, 13, 14, 15 |

#### 示例代码

```python
import dds_middleware_python as dds

def lower_state_callback(state):
    motor_states = state.motor_state()
    print(f"Received Motor States")
    for i in range(16):
        motor = motor_states[i]
        print(f"Motor[{i}]: mode={motor.mode()}, q={motor.q():.4f} rad, "
              f"dq={motor.dq():.4f} rad/s, tau_est={motor.tau_est():.4f} Nm, "
              f"temp={motor.motor_temp()}°C")

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeLowerState("rt/lower/state", lower_state_callback)
```

#### 输出示例

```
Received Motor States #50
Motor[0]: mode=4, q(rad)=-0.0523, dq(rad/s)=0.0012, ddq(rad/s²)=0.0001, tau_est(N·m)=0.12345, q_raw(rad)=-0.0523, dq_raw(rad/s)=0.0012, ddq_raw(rad/s²)=0.0001, motor_temp(°C)=35
Motor[1]: mode=4, q(rad)=0.8542, dq(rad/s)=-0.0034, ...
...
```

#### 运行方式

```bash
cd low_level/python
python3 e5_motor_state_sub.py
```

### E6: 电池状态订阅

**文件**: `low_level/python/e6_bms_state_sub.py`

#### 功能说明

获取电池管理系统（BMS）的状态信息。

#### ⚠️ 注意

**Python 版本的 E6 示例目前只输出电池电量（battery_level）一项信息。** 如需更多的 BMS 数据，请参考 C++ 版本。

#### QoS 配置

```python
# 使用配置文件中的默认 reader QoS
# reliability: best_effort
# history_kind: keep_last
# history_depth: 10
# durability: volatile
```

#### 订阅话题

| 话题名称         | 消息类型     | 说明                      |
| ---------------- | ------------ | ------------------------- |
| `rt/lower/state` | `LowerState` | 底层状态（包含 BMS 数据） |

#### 示例代码

```python
import dds_middleware_python as dds

def lower_state_callback(state):
    bms = state.bms_state()
    print(f"Received BMS State")
    print(f"Battery Level: {bms.battery_level()}")

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeLowerState("rt/lower/state", lower_state_callback)
```

#### 输出示例

```
Received BMS State #100
Battery Level: 85
```

#### 运行方式

```bash
cd low_level/python
python3 e6_bms_state_sub.py
```

### E7: 语音播放

**文件**: `low_level/python/e7_voice_pub.py`

#### 功能说明

向机器人发送语音播放命令，支持两种模式：

1. **File 模式**：播放机器人主机上的音频文件
2. **Streaming 模式**：实时发送音频流数据

#### QoS 配置

```python
qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 5,
    "durability": "volatile"
}
```

#### 发布话题

| 话题名称       | 消息类型   | 说明     |
| -------------- | ---------- | -------- |
| `rt/voice/cmd` | `VoiceCmd` | 语音命令 |

#### File 模式

播放机器人主机端的音频文件。

**重要**：音频文件必须存在于机器人主机上，而不是开发机上！

```python
import dds_middleware_python as dds

middleware = dds.PyDDSMiddleware(0)

qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 5,
    "durability": "volatile"
}

middleware.createVoiceCmdWriter("rt/voice/cmd", qos_config)

# ⚠️ 重要：发布前需要 sleep 约 1 秒
# 原因：DDS 是一个分布式通信中间件，Writer 创建后需要时间发现对应的 Reader。
# 这个发现过程（Entity Discovery）需要通过网络协议的握手完成，通常需要 100-1000ms。
# 如果立即发布，对方可能还未完全发现该 Writer，导致消息丢失。
import time
time.sleep(1)

# File 模式
voice_cmd = dds.VoiceCmd()
voice_cmd.type("file")
voice_cmd.path("/root/test.wav")  # 机器人主机上的文件路径
voice_cmd.data([])

middleware.publishVoiceCmd(voice_cmd)
```

支持的音频格式：

- WAV
- FLAC
- MP3

#### Streaming 模式

实时发送音频流数据，适用于 TTS 或实时音频传输场景。

音频参数要求：

- 采样率：24kHz
- 位深：16bit
- 声道：单声道

```python
# Streaming 模式
voice_cmd = dds.VoiceCmd()
voice_cmd.type("streaming")
voice_cmd.path("")
voice_cmd.data(audio_bytes)  # PCM 音频数据

middleware.publishVoiceCmd(voice_cmd)
```

#### 运行方式

```bash
cd low_level/python

# File 模式
python3 e7_voice_pub.py file

# Streaming 模式（从麦克风捕获）
python3 e7_voice_pub.py streaming
```

### E8: 语音采集

**文件**: `low_level/python/e8_voice_sub.py`

#### 功能说明

从机器人麦克风订阅音频流数据。

音频参数：

- 采样率：24kHz
- 位深：16bit
- 声道：单声道

#### QoS 配置

```python
qos_config = {
    "reliability": "best_effort",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}
```

#### 订阅话题

| 话题名称         | 消息类型     | 说明            |
| ---------------- | ------------ | --------------- |
| `rt/voice/state` | `VoiceState` | 语音状态/音频流 |

#### 示例代码

```python
import dds_middleware_python as dds

def voice_state_callback(voice_state_msg):
    print(f"Received VoiceState message:")
    print(f"  Data size: {len(voice_state_msg.data_())} bytes")

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")
middleware.subscribeVoiceState("rt/voice/state", voice_state_callback, qos_config)
```

#### 输出示例

```
Starting DDS Python VoiceState subscriber...
Subscribing to topic: rt/voice/state
VoiceState subscriber started, waiting for voice state messages...
Received VoiceState message:
  Data size: 4800 bytes
---
```

#### 运行方式

```bash
cd low_level/python
python3 e8_voice_sub.py
```

### E9: 电机指令发布

**文件**: `low_level/python/e9_motor_cmd_pub.py`

#### 功能说明

直接向电机发送控制指令。此示例演示了正弦波位置控制测试。

#### 🚨 重要安全警告

**在运行此程序之前，必须先停止机器人的主控程序！**

直接控制电机而不停止主程序**会造成严重安全事故**，可能导致：

- ⚠️ **控制冲突**：主程序和你的代码同时发送指令，电机行为不可预测
- 🤖 **机器人失控**：不可预期的危险动作
- 🔥 **硬件损坏**：电机过载、过热、机械碰撞
- 👥 **人员伤害**：机器人意外移动造成伤害

#### ✅ 正确的停止方法（必须执行！）

**推荐使用 SDK 提供的 `kill_robot` 工具**：

```bash
# Python 版本（推荐）
cd high_level/python
python3 kill_robot.py 192.168.5.2:50051

# C++ 版本
cd high_level/cpp/build
./kill_robot 192.168.5.2:50051
```

`kill_robot` 工具会安全地：

1. ✅ 将机器人切换到 **PASSIVE** 状态（电机失能）
2. ⏱️ 等待 **5 秒**确保机器人安全停止
3. 🚫 终止所有控制器进程

详细信息请参考：[安全关闭章节](../../getting-started/quickstart/#_6)

#### 🛡️ 使用前检查清单

在运行电机控制程序前，请确认：

- [ ] 已使用 `kill_robot` 工具停止主控程序
- [ ] 机器人处于安全位置（平坦地面，远离障碍物）
- [ ] 周围无人员和贵重物品
- [ ] 理解你的代码将会发送的指令
- [ ] 准备好紧急停止按钮（Ctrl+C）

#### QoS 配置

```python
qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}
```

#### 发布/订阅话题

| 话题名称         | 类型 | 消息类型     | 说明         |
| ---------------- | ---- | ------------ | ------------ |
| `rt/lower/cmd`   | 发布 | `LowerCmd`   | 电机控制指令 |
| `rt/lower/state` | 订阅 | `LowerState` | 电机状态反馈 |

#### 电机指令参数

| 参数   | 类型  | 单位  | 说明     |
| ------ | ----- | ----- | -------- |
| `mode` | uint8 | -     | 控制模式 |
| `q`    | float | rad   | 目标位置 |
| `dq`   | float | rad/s | 目标速度 |
| `tau`  | float | Nm    | 前馈力矩 |
| `kp`   | float | -     | 位置增益 |
| `kd`   | float | -     | 速度增益 |

#### 控制公式

```
τ = kp × (q_des - q) + kd × (dq_des - dq) + τ_ff
```

其中：

- `τ` - 最终输出力矩
- `q_des`, `dq_des` - 期望位置和速度
- `q`, `dq` - 实际位置和速度
- `τ_ff` - 前馈力矩
- `kp`, `kd` - 增益参数

#### 电机 Offset（来自 E9 电机控制示例）

E9 示例使用固定的电机零位 offset 表，用于在硬件角度与逻辑关节角之间转换。

- 12 个有效电机使用的硬件索引映射：

```python
ABS2HW = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14]
```

- Offset 表（长度 16，按硬件电机 ID 索引）：

```python
MOTOR_OFFSET = [
    -0.05, -0.5, 1.17, 0.0,
    0.05, -0.5, 1.17, 0.0,
    -0.05, 0.5, -1.17, 0.0,
    0.05, 0.5, -1.17, 0.0,
]
```

控制环中的使用方式：

- 读取侧（硬件 -> 逻辑）：`q_real = q_hw - MOTOR_OFFSET[hw]`
- 下发侧（逻辑 -> 硬件）：`q_cmd = q_target + MOTOR_OFFSET[hw]`

#### 示例代码

```python
import dds_middleware_python as dds
import math

# 电机索引映射
NUM_MOTORS = 12
ABS2HW = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14]
MOTOR_OFFSET = [
    -0.05, -0.5, 1.17, 0.0, 0.05, -0.5, 1.17, 0.0,
    -0.05, 0.5, -1.17, 0.0, 0.05, 0.5, -1.17, 0.0
]

middleware = dds.PyDDSMiddleware("config/dds_config.yaml")

qos_config = {
    "reliability": "reliable",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile"
}

middleware.createLowerCmdWriter("rt/lower/cmd", qos_config)

# 创建正弦波控制指令
def create_swing_cmd(s, q_init):
    cmd = dds.LowerCmd()
    for i in range(NUM_MOTORS):
        hw = ABS2HW[i]
        qdes = q_init[hw] + math.sin(2 * math.pi * s) * 0.2 + MOTOR_OFFSET[hw]
        cmd[hw].mode(0)
        cmd[hw].q(qdes)
        cmd[hw].dq(0.0)
        cmd[hw].tau(0.0)
        cmd[hw].kp(30.0)
        cmd[hw].kd(1.2)
    return cmd
```

#### 运行方式

```bash
cd low_level/python
python3 e9_motor_cmd_pub.py
```

#### 输出示例

```
Waiting for initial position collection...
Initial position collection completed: -0.0500 0.8500 -1.7000 ...
Starting control loop
[0] Initialization phase
[10] Starting swing
[5000] Swing completed, entering damping mode
```

## 常见问题

### Q: 订阅不到数据

1. 检查 `CYCLONEDDS_URI` 环境变量是否设置
2. 检查网络接口配置是否正确
3. 使用 `cyclonedds ps` 查看可用话题

### Q: LED 控制没有效果

必须先停止主控程序，参见 E3 部分的警告说明。

### Q: 电机控制剧烈震荡

1. 必须先停止主控程序
2. 确认电机初始位置采集完成

