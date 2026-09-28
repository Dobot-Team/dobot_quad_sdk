# Typical Scenarios

A few common tasks, walked through end to end: get the address, see the picture,
hand the frames to your own algorithm.

!!! note "Before you start"
    1. **The Python SDK is installed**: `cd high_level/python && pip install .` (use
       `pip install -e .` while developing). See the
       [Installation guide](getting-started/installation.md); without it `import dobot_quad`
       raises `ModuleNotFoundError`. On Ubuntu 22.04 run `python3 -m pip install -U pip`
       first, otherwise pip installs an empty package. For C++ you only need the
       repository and a compiler.
    2. **The robot is reachable**: check with `ping <robot-ip>` and replace the
       `192.168.5.2` used in the examples with your own address.
    3. **OpenCV for the windows**: `pip install opencv-python` (the SDK itself does not
       depend on it).

---

## 1. Watch Both Cameras on Your PC

The usual starting point: you want to see both robot cameras live on the PC in front of
you.

The SDK does the first half for you - it **starts the camera stream on the robot** and
returns an RTSP address you can play directly. The second half, turning that address
into a window, is left to OpenCV or to any tool that speaks RTSP. **You never have to
decode H.264 yourself.**

Three steps in total: open the stream, point a player (or OpenCV) at the address,
release the camera when you are done.

### 1. Open the stream and get the address

```python
from dobot_quad import CameraId, RobotClient

robot = RobotClient("192.168.5.2:50051")
uri = robot.video.open(CameraId.FRONT_RGB)   # returns rtsp://192.168.5.2:8554/camera1
print(uri)
```

`open()` returns only once the camera is really sending data (usually instantly), so the
address is ready to play right away and there is nothing to poll. Release the camera
with `robot.video.close(camera)` when you are done.

!!! note "One extra header for C++"
    Besides `#include "robot_client.h"`, add `#include "video/video_client.h"` and link
    `Threads::Threads` (the module is header-only, so there is no other library).
    Python needs no extra header; only the display code below needs OpenCV
    (`pip install opencv-python`).

### 2. What to display it with

The address is a plain RTSP URL, so anything you already have can open it:

| Tool | How |
| ---- | --- |
| ffplay (quickest check) | `ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay rtsp://192.168.5.2:8554/camera1` |
| ffmpeg (save to a file / re-stream) | `ffmpeg -rtsp_transport tcp -i <uri> -c copy -t 10 front.mp4` |
| OpenCV (inside your program) | `cv2.VideoCapture(uri, cv2.CAP_FFMPEG)`, **set the low-latency options first** (see the tip below) |
| VLC / GStreamer | Open a network stream and paste the address |

!!! tip "OpenCV: set the low-latency options, otherwise the picture lags"
    OpenCV only takes decoder options through an environment variable, and it has to be set
    **before** the `VideoCapture` is created:

    ```python
    import os

    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
        "|reorder_queue_size;0|probesize;32|analyzeduration;0")
    ```

    In C++ the same variable: `setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "<the string above>", 1);`
    With a player instead, the equivalent is
    `ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay <uri>`.

### 3. Complete code: both cameras in two windows

=== "Python"

    ```python
    """Show both robot cameras in two windows. ESC or q quits early.

    The low-latency options are already set: without them the picture lags noticeably.
    """
    import os
    import sys
    import time

    import cv2

    from dobot_quad import CameraId, RobotClient

    # Must be set before VideoCapture is created: OpenCV only takes decoder
    # options through this environment variable.
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
        "|reorder_queue_size;0|probesize;32|analyzeduration;0")

    ADDRESS = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"
    SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

    robot = RobotClient(ADDRESS)
    captures = {}
    for camera, title in ((CameraId.FRONT_RGB, "Front RGB"), (CameraId.REAR_RGB, "Rear RGB")):
        uri = robot.video.open(camera)      # blocks until the stream carries data
        print(f"{title}: {uri}")
        cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            print(f"{title}: OpenCV cannot open the stream")
            robot.video.close(camera)
            continue
        captures[camera] = (title, cap)

    deadline = time.monotonic() + SECONDS
    while captures and time.monotonic() < deadline:
        for camera in list(captures):
            title, cap = captures[camera]
            ok, frame = cap.read()
            if not ok:
                print(f"{title}: stream stopped")
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
    // two_cameras.cpp - show both robot cameras in two windows
    // build: robot_client.h + video/video_client.h, link proto_lib,
    //        Threads::Threads and OpenCV (see CMake snippet below)
    #include "robot_client.h"
    #include "video/video_client.h"   // adds client.video()

    #include <opencv2/opencv.hpp>

    #include <cstdlib>
    #include <iostream>
    #include <map>
    #include <string>

    int main(int argc, char** argv)
    {
        // Low latency: OpenCV reads this environment variable only, and it has to be
        // set before the VideoCapture is created.
        setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS",
               "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
               "|reorder_queue_size;0|probesize;32|analyzeduration;0", 1);

        const std::string address = argc > 1 ? argv[1] : "192.168.5.2:50051";
        const double seconds = argc > 2 ? std::atof(argv[2]) : 30.0;

        robot::Client client(address);

        std::map<robot::video::CameraId, cv::VideoCapture> captures;
        for (auto camera : {robot::video::CameraId::FrontRgb, robot::video::CameraId::RearRgb}) {
            const std::string uri = client.video().open(camera);   // blocks until data flows
            std::cout << robot::video::camera_name(camera) << ": " << uri << std::endl;

            if (!captures[camera].open(uri, cv::CAP_FFMPEG)) {
                std::cerr << robot::video::camera_name(camera) << ": OpenCV cannot open it"
                          << std::endl;
                client.video().close(camera);
                captures.erase(camera);
            }
        }

        const double deadline = robot::video::monotonic_s() + seconds;
        while (!captures.empty() && robot::video::monotonic_s() < deadline) {
            for (auto it = captures.begin(); it != captures.end();) {
                cv::Mat frame;
                if (!it->second.read(frame) || frame.empty()) {
                    std::cerr << robot::video::camera_name(it->first) << ": no frame" << std::endl;
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

    !!! tip "Without CMake"
        `g++ -std=c++14 -O2 -I<repo>/high_level/cpp -I<build dir with the generated .pb.h> \
        two_cameras.cpp libproto_lib.a -lgrpc++ -lgpr -lprotobuf -lpthread \
        $(pkg-config --cflags --libs opencv4) -o two_cameras`

### 4. Run it

```bash
# Python (the SDK is assumed to be installed, see the Installation guide)
python3 two_cameras.py 192.168.5.2:50051 30      # address, seconds

# C++
./two_cameras 192.168.5.2:50051 30
```

Both cameras appear in two windows; the program exits by itself after the given
number of seconds, or immediately when you press `q` / `ESC`.

### 5. What to expect (measured, wired connection)

| Step | Measured |
| ---- | -------- |
| `open(CameraId.FRONT_RGB)` (cold start, the SDK opens the stream) | ~0.5 s (521 ms measured), returns `rtsp://<ip>:8554/camera1` |
| `open(CameraId.REAR_RGB)` | 0.1-0.5 s, returns `rtsp://<ip>:8554/camera2` |
| `open()` on a stream that is already running *and carrying data* (e.g. the app is watching) | ~0.3 s (295 ms measured): `bytes_recv` has to **grow** between two samples before a stream counts as running |
| `open()` right after `stop_stream()` (leftover stream that no longer grows) | ~0.5 s (519 ms measured): the leftover stream is **not** adopted, the SDK issues its own `start` first |
| Opening the same camera again | < 1 ms (reference count only - call `close()` as many times) |
| First frame in your own decoder | 1-2 s (OpenCV 1.1-1.3 s; ffmpeg 2.0 s including process start-up) |
| Resolution / rate / bitrate | 1280 × 720, ~30-32 fps per camera (30.9 fps measured over 6 s, no slow-down in the second half), ~2.8 Mbps; both windows at once are fine |

The SDK does not decode anything itself, so CPU cost here is your OpenCV
decoder: on a desktop this is a few percent per camera.

### 6. No picture?

| Symptom | What to check |
| -------- | ------------- |
| `open()` raises "not ready within 8 s" | Host and robot on the same network (`ping <ip>`); if the phone app is switching streams, wait a moment and try again. |
| `open()` raises "Cannot reach the streaming service" | The robot's port 22000 is unreachable - check the network / IP. |
| OpenCV says it cannot open the stream | Your OpenCV has no FFmpeg support, or RTSP is blocked. Verify with a player first: `ffplay -rtsp_transport tcp <uri>`. |
| Picture is very late | OpenCV buffers too much by default. Set `OPENCV_FFMPEG_CAPTURE_OPTIONS` before creating the `VideoCapture` (see the tip in section 1). |

---

## 2. Grab Frames for Your Own Algorithm

No window and no display - suitable for a headless PC, a container or a long-running
service. The address works the same way, you just push every frame into your own
pipeline instead of onto the screen.

=== "Python"

    ```python
    """Grab frames from one camera and hand them to your own pipeline."""
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
        # >>> your algorithm goes here, e.g. detect(frame) <<<

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
            // >>> your algorithm goes here, e.g. detect(frame) <<<
        }
        cap.release();
        client.video().close(robot::video::CameraId::FrontRgb);
        std::cout << frames << " frames in 10 s" << std::endl;
        return 0;
    }
    ```

!!! tip "Only want to record, not process?"
    No code needed: use the ffmpeg line from step 2 above (`-c copy` copies the codec
    stream as-is, without re-encoding).
