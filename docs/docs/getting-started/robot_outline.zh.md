# 本体图

本页给出机器人本体的**编号对照**：相机编号、电机编号及其物理位置。

<!-- 注意：i18n 插件不会把 assets/ 复制到各语言目录，所以中文页里的图片要按
     「当前页在站点里的层级」退回到站点根：本页在 /zh/getting-started/robot_outline/，
     所以要退三级（../../../assets/…）；首页那种一级页面写 ../assets/… 即可。
     改错层级图片就会挂掉。 -->
<img src="../../../assets/robot_front_cameras.png" alt="正面 / 背面：相机位置与编号" />

!!! note "关于这些图"
    图中标注用于说明**编号与位置的对应关系**；实际安装位置以产品实物为准。

---

## 一、相机编号

机身共有 **4 个相机模组**：**2 个纯 RGB 相机** + **2 个深度相机**（深度相机同时输出 RGB 图）。

机身印有 `X1` 字样的一侧是**前面**；两端模组完全相同，只是编号不同。

| 物理位置 | 模组类型 | DDS 话题编号 | RTSP 推流名 |
| -------- | -------- | ------------ | ----------- |
| 前置 | 纯 RGB（主） | `camera0` | `camera1` |
| 后置 | 纯 RGB（主） | `camera1` | `camera2` |
| 前置 | 深度相机（含 RGB） | `camera2` | 无推流 |
| 后置 | 深度相机（含 RGB） | `camera3` | 无推流 |

!!! warning "两套编号彼此独立"
    **DDS 话题编号**与 **RTSP 推流名**是两套独立编号，请勿跨层推断
    （本机型恰好整体偏移 1：RTSP `camera1` ↔ DDS `camera0`）。

### 话题一览

| 话题 | 消息类型 | 说明 |
| ---- | -------- | ---- |
| `rt/camera/camera0/image_compressed` | `CompressedImage` | 压缩的 RGB 图像（前置相机） |
| `rt/camera/camera1/image_compressed` | `CompressedImage` | 压缩的 RGB 图像（后置相机） |
| `rt/camera/camera2/image_compressed` | `CompressedImage` | 压缩的 RGB 图像（前置深度相机的 RGB 图） |
| `rt/camera/camera3/image_compressed` | `CompressedImage` | 压缩的 RGB 图像（后置深度相机的 RGB 图） |
| `rt/camera/camera2/image_depth` | `Image` | 原始深度图像（前置深度相机，16UC1） |
| `rt/camera/camera3/image_depth` | `Image` | 原始深度图像（后置深度相机，16UC1） |

---

## 二、电机编号

<img src="../../../assets/wheel_back.jpg" alt="俯视：电机编号（轮足）" style="max-width: 680px;" />

机器人共有 16 个关节电机，编号 `0`–`15`，分布在四条腿上；每条腿内部按「由身到足」的顺序编号：
**髋 → 大腿 → 膝 → 足端**。

点足与轮足**编号完全一致**——点足只是没有 `3`、`7`、`11`、`15` 这四个电机
（轮足上驱轮的那四个足端电机），所以点足是 12 个电机、轮足是 16 个：

| 腿部   | 轮足           | 点足        |
| ------ | -------------- | ----------- |
| 前左腿 | 0, 1, 2, 3     | 0, 1, 2     |
| 前右腿 | 4, 5, 6, 7     | 4, 5, 6     |
| 后左腿 | 8, 9, 10, 11   | 8, 9, 10    |
| 后右腿 | 12, 13, 14, 15 | 12, 13, 14  |

---

## 三、腿灯标识

高层腿灯接口使用**枚举**标识腿部，而非编号：

| 枚举 | 位置 | 说明 |
| ---- | ---- | ---- |
| `Leg.FL` | 前左 | 腿灯 |
| `Leg.FR` | 前右 | 腿灯 |
| `Leg.RL` | 后左 | 腿灯 |
| `Leg.RR` | 后右 | 腿灯 |
| `Leg.FILL_FRONT` | 前 | 补光灯（点足机型） |
| `Leg.FILL_BACK` | 后 | 补光灯（点足机型） |
