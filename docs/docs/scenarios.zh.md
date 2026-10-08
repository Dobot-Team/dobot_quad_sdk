# 典型场景

下面用几个常见任务，把「拿到流地址 → 看到画面 → 交给自己的算法」走一遍。

!!! note "开始之前"
    1. **Python SDK 已安装**：`cd high_level/python && pip install .`（开发时用 `pip install -e .`），
       详见[安装指南](getting-started/installation.zh.md)，否则 `import dobot_quad` 会报
       `ModuleNotFoundError`。另外 Ubuntu 22.04 自带的 pip 22 太老，**先 `python3 -m pip install -U pip`**
       （否则会装出一个空包）。C++ 用户只需仓库源码和编译环境。
    2. **能访问到机器人**：先 `ping <机器人IP>` 确认，例子里出现的 `192.168.5.2` 都换成你的地址。
    3. **显示窗口需要 OpenCV**：`pip install opencv-python`（SDK 本身不依赖它）。

---

## 一、在电脑上实时看两路相机

最常见的需求是：坐在电脑前，实时看到机器狗上两个相机的画面。

这件事 SDK 可以帮你做前半段——它负责**把机器狗上的相机流打开**，并返回一个可以
直接播放的 RTSP 地址；后半段「把地址变成屏幕上的画面」交给 OpenCV，或者任何支持
RTSP 的工具，**你不需要自己解 H.264**。

整个流程只有三步：开流拿地址 → 用播放器 / OpenCV 打开地址 → 退出时释放。

### 1. 开流，拿到地址

```python
from dobot_quad import CameraId, RobotClient

robot = RobotClient("192.168.5.2:50051")
uri = robot.video.open(CameraId.FRONT_RGB)   # 开流，返回 rtsp://192.168.5.2:8554/camera1
print(uri)
```

`open()` 会等到相机真的在推数据才返回（通常一瞬间），所以拿到地址直接播放就行，
不用自己轮询、也不用自己判断流有没有起来。用完记得 `robot.video.close(camera)`
释放这一路。

!!! note "C++ 要多 include 一个头文件"
    C++ 在 `#include "robot_client.h"` 之外再加 `#include "video/video_client.h"`，
    链接时多带 `Threads::Threads`（视频模块是纯头文件，不需要别的库）。
    Python 不需要额外 include；下面显示窗口才需要 OpenCV（`pip install opencv-python`）。

### 2. 用什么把画面显示出来

返回的地址就是一个普通 RTSP 地址，手边的工具都能直接打开：

| 工具 | 怎么用 |
| ---- | ------ |
| ffplay（最快验证） | `ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay rtsp://192.168.5.2:8554/camera1` |
| ffmpeg（存成文件 / 转推） | `ffmpeg -rtsp_transport tcp -i <uri> -c copy -t 10 front.mp4` |
| OpenCV（写进自己的程序） | `cv2.VideoCapture(uri, cv2.CAP_FFMPEG)`，**先设低延迟参数**（见下面的提示） |
| VLC / GStreamer | 打开网络流，粘贴地址即可 |

!!! tip "OpenCV 一定要设低延迟参数，否则画面延迟明显偏大"
    OpenCV 只能通过环境变量传解码参数，而且要在创建 `VideoCapture` **之前**设置：

    ```python
    import os

    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
        "|reorder_queue_size;0|probesize;32|analyzeduration;0")
    ```

    C++ 用同一个环境变量：`setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "<上面的字符串>", 1);`
    用播放器时等价写法是
    `ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay <uri>`。

### 3. 完整代码：两个窗口一起看

=== "Python"

    ```python
    """两个窗口同时显示前/后相机；ESC 或 q 提前退出。

    已带低延迟参数：不设的话画面延迟会明显偏大。
    """
    import os
    import sys
    import time

    import cv2

    from dobot_quad import CameraId, RobotClient

    # 必须在创建 VideoCapture 之前设置：OpenCV 只能通过这个环境变量传解码参数
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
        "|reorder_queue_size;0|probesize;32|analyzeduration;0")

    ADDRESS = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"
    SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

    robot = RobotClient(ADDRESS)
    captures = {}
    for camera, title in ((CameraId.FRONT_RGB, "Front RGB"), (CameraId.REAR_RGB, "Rear RGB")):
        uri = robot.video.open(camera)      # 阻塞到「流在推且有数据」为止
        print(f"{title}: {uri}")
        cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            print(f"{title}: OpenCV 打不开这个地址")
            robot.video.close(camera)
            continue
        captures[camera] = (title, cap)

    deadline = time.monotonic() + SECONDS
    while captures and time.monotonic() < deadline:
        for camera in list(captures):
            title, cap = captures[camera]
            ok, frame = cap.read()
            if not ok:
                print(f"{title}: 没有画面数据了")
                cap.release()
                robot.video.close(camera)
                del captures[camera]
                continue
            cv2.imshow(title, frame)
        if cv2.waitKey(1) & 0xFF in (27, ord("q")):
            break

    cv2.destroyAllWindows()
    robot.video.close_all()
    robot.close()
    ```

=== "C++"

    ```cpp
    // two_cameras.cpp - 两个窗口同时显示前/后相机
    // 编译：robot_client.h + video/video_client.h，链接 proto_lib、
    //      Threads::Threads 与 OpenCV（CMake 片段见下）
    #include "robot_client.h"
    #include "video/video_client.h"   // 给 robot::Client 加上 video()

    #include <opencv2/opencv.hpp>

    #include <cstdlib>
    #include <iostream>
    #include <map>
    #include <string>

    int main(int argc, char** argv)
    {
        // 低延迟：OpenCV 只认这个环境变量，且要在创建 VideoCapture 之前设置
        setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS",
               "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
               "|reorder_queue_size;0|probesize;32|analyzeduration;0", 1);

        const std::string address = argc > 1 ? argv[1] : "192.168.5.2:50051";
        const double seconds = argc > 2 ? std::atof(argv[2]) : 30.0;

        robot::Client client(address);

        std::map<robot::video::CameraId, cv::VideoCapture> captures;
        for (auto camera : {robot::video::CameraId::FrontRgb, robot::video::CameraId::RearRgb}) {
            const std::string uri = client.video().open(camera);   // 阻塞到有数据在流
            std::cout << robot::video::camera_name(camera) << ": " << uri << std::endl;

            if (!captures[camera].open(uri, cv::CAP_FFMPEG)) {
                std::cerr << robot::video::camera_name(camera) << ": OpenCV 打不开" << std::endl;
                client.video().close(camera);
                captures.erase(camera);
            }
        }

        const double deadline = robot::video::monotonic_s() + seconds;
        while (!captures.empty() && robot::video::monotonic_s() < deadline) {
            for (auto it = captures.begin(); it != captures.end();) {
                cv::Mat frame;
                if (!it->second.read(frame) || frame.empty()) {
                    std::cerr << robot::video::camera_name(it->first) << ": 没有画面" << std::endl;
                    it->second.release();
                    client.video().close(it->first);
                    it = captures.erase(it);
                    continue;
                }
                cv::imshow(robot::video::camera_name(it->first), frame);
                ++it;
            }
            const int key = cv::waitKey(1) & 0xFF;
            if (key == 27 || key == 'q') {
                break;
            }
        }

        cv::destroyAllWindows();
        client.video().close_all();
        return 0;
    }
    ```

    ```cmake
    find_package(OpenCV REQUIRED)
    find_package(Threads REQUIRED)

    add_executable(two_cameras two_cameras.cpp)
    target_link_libraries(two_cameras PRIVATE proto_lib Threads::Threads ${OpenCV_LIBS})
    ```

    !!! tip "不用 CMake 时"
        `g++ -std=c++14 -O2 -I<仓库>/high_level/cpp -I<生成 .pb.h 的 build 目录> \
        two_cameras.cpp libproto_lib.a -lgrpc++ -lgpr -lprotobuf -lpthread \
        $(pkg-config --cflags --libs opencv4) -o two_cameras`

### 4. 运行

```bash
# Python（假定 SDK 已按安装指南装好）
python3 two_cameras.py 192.168.5.2:50051 30      # 参数：地址、显示秒数

# C++
./two_cameras 192.168.5.2:50051 30
```

两路相机各自出现在一个窗口里；到时间会自动退出，按 `q` / `ESC` 可立刻退出。

### 5. 预期表现（有线连接）

| 步骤 | 预期 |
| ---- | ---- |
| `open(CameraId.FRONT_RGB)`（冷启动，SDK 自己开流） | 约 0.5 s，返回 `rtsp://<ip>:8554/camera1` |
| `open(CameraId.REAR_RGB)` | 约 0.1~0.5 s，返回 `rtsp://<ip>:8554/camera2` |
| `open()`（流已在推且有数据，例如 App 正在看 → 直接采用） | 约 0.3 s：要看到 `bytes_recv` 在采样间隔内**增长**才算「在流」 |
| `open()`（刚 `stop_stream()`，残留的流不再增长） | 约 0.5 s：**不采用**残留流，自己 `start` 接管后再返回地址 |
| 同一相机重复 `open()` | 毫秒级（只增加引用计数，记得 `close()` 同次数） |
| 你自己的解码器解出第一帧 | 1~2 s（取决于解码器与主机性能） |
| 分辨率 / 帧率 / 码率 | 1280 × 720、单路约 30 fps、约 2.8 Mbps；两路同时显示没有问题 |

SDK 本身不解码，CPU 开销来自你自己的 OpenCV 解码器：桌面机上单路通常只占几个
百分点的 CPU。

### 6. 没有画面？

| 现象 | 检查什么 |
| ---- | -------- |
| `open()` 报 "not ready within 8 s" | 主机与机器人是否在同一网络（先 `ping <ip>`）；如果手机 App 正在切流，稍等再试。 |
| `open()` 报 "Cannot reach the streaming service" | 机器人的 22000 端口不可达——检查网络 / IP。 |
| OpenCV 说打不开 | 你的 OpenCV 没带 FFmpeg，或 RTSP 被挡了。先用播放器验证：`ffplay -rtsp_transport tcp <uri>`。 |
| 画面延迟大 | OpenCV 默认缓冲偏多。在创建 `VideoCapture` 之前设置 `OPENCV_FFMPEG_CAPTURE_OPTIONS`（见第一节的提示）。 |

---

## 二、不开窗口，把画面交给自己的算法

不要窗口、不依赖桌面环境，适合无头主机 / 容器 / 常驻服务：拿到的地址同样
交给 OpenCV，只是把每帧送进你自己的流程，而不是画到屏幕上。

=== "Python"

    ```python
    """从一路相机取帧，交给自己的处理流程。"""
    import time

    import cv2

    from dobot_quad import CameraId, RobotClient

    robot = RobotClient("192.168.5.2:50051")
    uri = robot.video.open(CameraId.FRONT_RGB)   # rtsp://192.168.5.2:8554/camera1
    print("playing:", uri)

    cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
    frames = 0
    started = time.monotonic()
    while time.monotonic() - started < 10.0:
        ok, frame = cap.read()
        if not ok:
            break
        frames += 1
        # >>> 你的算法写在这里，例如 detect(frame) <<<

    cap.release()
    robot.video.close(CameraId.FRONT_RGB)
    robot.close()
    print(f"{frames} frames in {time.monotonic() - started:.1f}s")
    ```

=== "C++"

    ```cpp
    #include "robot_client.h"
    #include "video/video_client.h"

    #include <opencv2/opencv.hpp>

    #include <iostream>

    int main()
    {
        robot::Client client("192.168.5.2:50051");
        const std::string uri = client.video().open(robot::video::CameraId::FrontRgb);
        std::cout << "playing: " << uri << std::endl;

        cv::VideoCapture cap(uri, cv::CAP_FFMPEG);
        const double deadline = robot::video::monotonic_s() + 10.0;
        int frames = 0;
        while (robot::video::monotonic_s() < deadline) {
            cv::Mat frame;
            if (!cap.read(frame) || frame.empty()) {
                break;
            }
            ++frames;
            // >>> 你的算法写在这里，例如 detect(frame) <<<
        }
        cap.release();
        client.video().close(robot::video::CameraId::FrontRgb);
        std::cout << frames << " frames in 10 s" << std::endl;
        return 0;
    }
    ```

!!! tip "只想录下来，不做处理？"
    不用写代码：用第一节第 2 步里的 ffmpeg 一行命令即可（`-c copy` 直接复制码流，
    不重新编码）。
