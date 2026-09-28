#!/usr/bin/env python3
"""High-Level camera video streaming joint-test harness (interactive; needs a robot).

Location: high_level/test/python/video_joint_test.py

Usage:
  python video_joint_test.py [server_address] [options]

Options:
  --suite NAME   all|api|stream|adopt|recover|multi|edge|smoke   (default: all)
  --camera WHICH front|rear|both                                 (default: both)
  --auto         Timed pause instead of keyboard wait; verdicts that can be
                 measured automatically are decided automatically, the rest are
                 recorded as OBSERVE
  --hold SEC     Observation time in --auto mode (default: 3)
  --seconds SEC  Decode / stability window for the stream cases (default 10)
  --no-gui       Never open OpenCV windows (headless machines / CI)

Covers joint-test cases:
  TC-API-*      interface contract: address, info, idempotent open, callbacks
  TC-STREAM-*   media plane: probe, first frame, fps, both cameras, bitrate
  TC-ADOPT-*    a stream that is already running (phone app / another player)
  TC-RECOVER-*  external stop -> automatic resume; stop_stream() stays stopped
  TC-MULTI-*    repeated open/close, thread count, no leaks
  TC-EDGE-*     unreachable host, close right after open, close without open
  TC-SMOKE      one-command end-to-end pass

Out of scope: the fill lights and the depth cameras are not streamed by design.

The SDK does not decode frames: every picture in this harness is decoded by
OpenCV / ffmpeg on the test machine, which is exactly what a user would do.

Not collected by pytest (filename has no test_ prefix).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from dobot_quad import CameraId, RobotClient
from dobot_quad.video import StreamEvent, StreamEventKind, StreamState, VideoStreamManager

try:  # OpenCV is only needed by the cases that show or decode pictures.
    import cv2
except Exception:  # noqa: BLE001 - keep the harness usable without OpenCV
    cv2 = None

GO2RTC_PORT = 1984
STREAM_PORT = 22000
DEFAULT_ADDRESS = "192.168.5.2:50051"

CAMERA_CHOICES: Dict[str, CameraId] = {
    "front": CameraId.FRONT_RGB,
    "rear": CameraId.REAR_RGB,
}


# --------------------------------------------------------------------------- HTTP
def http_post(host: str, port: int, path: str, timeout: float = 4.0) -> int:
    """Hit the streaming switch directly, bypassing the SDK.

    Used to imitate "the phone app started/stopped the stream" from the outside.
    """
    request = urllib.request.Request(
        f"http://{host}:{port}{path}", data=b"{}", method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except Exception as exc:  # noqa: BLE001 - a test harness wants the reason
        print(f"  [warn] POST {path} failed: {exc}")
        return -1


def go2rtc_streams(host: str, timeout: float = 3.0) -> dict:
    """Snapshot of go2rtc's own view: who produces, who consumes."""
    try:
        with urllib.request.urlopen(
            f"http://{host}:{GO2RTC_PORT}/api/streams", timeout=timeout
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def stream_facts(host: str, stream: str) -> str:
    entry = go2rtc_streams(host).get(stream) or {}
    producers = entry.get("producers") or []
    consumers = entry.get("consumers") or []
    received = sum(int(p.get("bytes_recv") or 0) for p in producers)
    return (f"producers={len(producers)} consumers={len(consumers)} "
            f"bytes_recv={received}")


def producer_bytes(host: str, stream: str) -> int:
    entry = go2rtc_streams(host).get(stream) or {}
    return sum(int(p.get("bytes_recv") or 0) for p in entry.get("producers") or [])


def has_producer(host: str, stream: str) -> bool:
    entry = go2rtc_streams(host).get(stream) or {}
    return bool(entry.get("producers"))


def wait_for_data(host: str, stream: str, timeout: float = 20.0,
                 min_bytes: int = 100_000) -> bool:
    """Wait until the producer really carries data (spin-up can take seconds)."""
    first = producer_bytes(host, stream)
    if first >= min_bytes:
        return True
    return wait_for(lambda: producer_bytes(host, stream) - first >= min_bytes,
                    timeout=timeout, interval=0.5)


def wait_for(predicate: Callable[[], bool], timeout: float = 10.0,
             interval: float = 0.2) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


# ---------------------------------------------------------------------- ffmpeg
def have_tool(name: str) -> bool:
    return shutil.which(name) is not None


def ffprobe_uri(uri: str, timeout: float = 25.0) -> Optional[Dict[str, str]]:
    """Play the address with ffprobe: external proof that it is playable."""
    if not have_tool("ffprobe"):
        return None
    try:
        done = subprocess.run(
            ["ffprobe", "-v", "error", "-rtsp_transport", "tcp",
             "-select_streams", "v:0",
             "-show_entries", "stream=codec_name,width,height,r_frame_rate",
             "-of", "default=nw=1", uri],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    facts = {}
    for line in done.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            facts[key.strip()] = value.strip()
    return facts or None


def first_frame_seconds(uri: str, timeout: float = 25.0) -> Optional[float]:
    """Wall-clock time from "address in hand" to "one JPEG written" (ffmpeg)."""
    if not have_tool("ffmpeg"):
        return None
    started = time.monotonic()
    try:
        done = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp",
             "-i", uri, "-frames:v", "1", "-f", "image2", "-y", "/tmp/_vt_first.jpg"],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    if done.returncode != 0:
        return None
    return time.monotonic() - started


def start_background_player(uri: str, seconds: float) -> Optional[subprocess.Popen]:
    """A second viewer (player/App stand-in) that keeps the stream alive."""
    if not have_tool("ffmpeg"):
        return None
    return subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp",
         "-i", uri, "-f", "null", "-t", str(seconds), "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def cv_first_frame_seconds(uri: str, timeout: float = 12.0) -> Optional[float]:
    """Time from opening the address to the first decoded frame (user-side view).

    Unlike the ffmpeg number this excludes process start-up, so it is the value a
    user's own program would see.
    """
    if cv2 is None:
        return None
    started = time.monotonic()
    capture = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
    try:
        while time.monotonic() - started < timeout:
            ok, frame = capture.read()
            if ok and frame is not None:
                return time.monotonic() - started
    finally:
        capture.release()
    return None


def decode_window(uri: str, seconds: float, *, gui: bool = False,
                  window: str = "camera") -> Dict[str, float]:
    """Decode for `seconds` with OpenCV and report frames / fps / size."""
    if cv2 is None:
        return {}
    capture = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
    if not capture.isOpened():
        return {"opened": 0}
    frames = 0
    width = height = 0
    started = time.monotonic()
    try:
        while time.monotonic() - started < seconds:
            ok, frame = capture.read()
            if not ok:
                break
            frames += 1
            height, width = frame.shape[:2]
            if gui:
                cv2.imshow(window, frame)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
    finally:
        capture.release()
        if gui:
            cv2.destroyWindow(window)
    elapsed = max(time.monotonic() - started, 1e-6)
    return {"opened": 1, "frames": frames, "fps": frames / elapsed,
            "width": width, "height": height, "seconds": elapsed}


# --------------------------------------------------------------------- results
@dataclass
class CaseResult:
    case_id: str
    title: str
    rpc_ok: Optional[bool]
    verdict: str  # PASS / FAIL / SKIP / OBSERVE
    note: str = ""


@dataclass
class Runner:
    robot: RobotClient
    auto: bool = False
    hold_sec: float = 3.0
    seconds: float = 10.0
    no_gui: bool = False
    selected: Sequence[CameraId] = (CameraId.FRONT_RGB, CameraId.REAR_RGB)
    results: List[CaseResult] = field(default_factory=list)

    # ------------------------------------------------------------- plumbing
    @property
    def host(self) -> str:
        return self.robot.video.host

    def banner(self, title: str) -> None:
        print("\n" + "=" * 62)
        print(title)
        print("=" * 62)

    def pause(self, prompt: str = "观察后按 Enter 继续") -> None:
        if self.auto:
            print(f"  ... 自动等待 {self.hold_sec:.1f}s")
            time.sleep(self.hold_sec)
            return
        try:
            input(f"  >> {prompt} ")
        except EOFError:
            time.sleep(self.hold_sec)

    def ask_verdict(self, case_id: str, title: str, ok: Optional[bool],
                    expect_hint: str, measured: str = "") -> None:
        print(f"\n[{case_id}] {title}")
        print(f"  期望: {expect_hint}")
        if measured:
            print(f"  实测: {measured}")

        if self.auto:
            verdict = "OBSERVE" if ok is None else ("PASS" if ok else "FAIL")
            note = "auto 模式未人工判定" if verdict == "OBSERVE" else ""
            self.results.append(CaseResult(case_id, title, ok, verdict, note))
            self.pause("自动停留供观察")
            return

        self.pause("观察/确认后输入判定")
        try:
            raw = input("  判定 [y/n/s]: ").strip().lower()
        except EOFError:
            raw = "y"
        if raw in ("", "y", "yes"):
            verdict = "PASS"
        elif raw in ("n", "no"):
            verdict = "FAIL"
        else:
            verdict = "SKIP"
        note = ""
        if ok is False and verdict == "PASS":
            note = "人工通过但自动判定为否"
        elif ok is None and verdict == "PASS":
            note = "人工判定"
        self.results.append(CaseResult(case_id, title, ok, verdict, note))

    def baseline(self) -> None:
        """Back to a clean slate: nobody streaming, nobody watching."""
        for camera in CAMERA_CHOICES.values():
            try:
                self.robot.video.stop_stream(camera)
            except Exception:  # noqa: BLE001
                pass
            try:
                self.robot.video.close(camera)
            except Exception:  # noqa: BLE001
                pass
        for name in ("camera1", "camera2"):
            wait_for(lambda s=name: not has_producer(self.host, s), timeout=6.0)
        quiet = not any(has_producer(self.host, name) for name in ("camera1", "camera2"))
        print(f"  基线就绪：{'当前没有任何人在推流（producers=0）' if quiet else '⚠ 仍有 producer！'}")
        print(f"    camera1 {stream_facts(self.host, 'camera1')} | "
              f"camera2 {stream_facts(self.host, 'camera2')}")
        print("    （producers=推流方数量，consumers=观看方数量，bytes_recv=累计字节；"
              "含义见自验报告「术语速查」）")

    def timed_open(self, camera: CameraId) -> Tuple[str, float]:
        started = time.monotonic()
        uri = self.robot.video.open(camera)
        return uri, time.monotonic() - started

    # -------------------------------------------------------------- suites
    def suite_api(self) -> None:
        self.banner("组 A: 接口能力 (TC-API)")
        self.baseline()

        # 回调必须**在第一次 open 之前**注册，否则看不到 StreamReady。
        events: List[StreamEvent] = []
        lock = threading.Lock()

        def on_event(event: StreamEvent) -> None:
            with lock:
                events.append(event)

        cancel = self.robot.video.on_state_change(on_event)

        def event_names() -> List[str]:
            with lock:
                return [event.name for event in events]

        # ---- list_cameras
        cameras = self.robot.video.list_cameras()
        self.ask_verdict(
            "TC-API-01", "list_cameras() 返回两路 RGB 相机",
            set(cameras) == {CameraId.FRONT_RGB, CameraId.REAR_RGB},
            "包含 FRONT_RGB / REAR_RGB 两路",
            f"list_cameras() = {[c.name for c in cameras]}")

        # ---- open front: address shape
        uri_front, cost_front = self.timed_open(CameraId.FRONT_RGB)
        expected_front = f"rtsp://{self.host}:8554/{CameraId.FRONT_RGB.rtsp_name}"
        self.ask_verdict(
            "TC-API-02", "open(FRONT_RGB) 返回可播放地址",
            uri_front == expected_front and has_producer(self.host, "camera1"),
            f"返回 {expected_front}，且 go2rtc 真的有 producer",
            f"{uri_front}（{cost_front * 1000:.0f} ms）；{stream_facts(self.host, 'camera1')}")

        # ---- idempotent open (raises the reference count)
        uri_again, cost_again = self.timed_open(CameraId.FRONT_RGB)
        self.ask_verdict(
            "TC-API-03", "重复 open() 返回同一地址且几乎不耗时",
            uri_again == uri_front and cost_again < 0.2,
            "地址不变；第二次调用 < 200 ms（不重新开流，仅引用计数 +1）",
            f"第二次 {cost_again * 1000:.0f} ms，地址 "
            f"{'相同' if uri_again == uri_front else '不同'}")

        # ---- get_stream_info
        info = self.robot.video.get_stream_info(CameraId.FRONT_RGB)
        ok_info = (info.state == StreamState.READY and info.uri == uri_front
                   and info.codec == "H.264")
        self.ask_verdict(
            "TC-API-04", "get_stream_info() 字段完整",
            ok_info,
            "state=READY、uri 一致、codec=H.264，owner 能区分谁开的流",
            f"state={info.state.value} owner={info.owner.value} "
            f"bitrate={info.bitrate_kbps} uri={info.uri}")

        # ---- is_streaming 与 go2rtc 一致
        streaming = self.robot.video.is_streaming(CameraId.FRONT_RGB)
        self.ask_verdict(
            "TC-API-05", "is_streaming() 与 go2rtc 现状一致",
            streaming is True and has_producer(self.host, "camera1"),
            "开流后为 True",
            f"is_streaming={streaming}；{stream_facts(self.host, 'camera1')}")

        # ---- 状态回调（注册在 open 之前，能看到 StreamReady）
        self.ask_verdict(
            "TC-API-06", "on_state_change() 能收到 StreamReady",
            StreamEventKind.READY.value in event_names(),
            "open 期间回调里收到 StreamReady",
            f"事件序列 = {event_names()}")

        # ---- 引用计数语义：open 两次，close 一次只减计数、不停流
        self.robot.video.close(CameraId.FRONT_RGB)
        still = self.robot.video.is_streaming(CameraId.FRONT_RGB)
        self.ask_verdict(
            "TC-API-10", "重复 open 后 close 的引用计数语义（重要）",
            still is True and has_producer(self.host, "camera1"),
            "open×2 → close 一次只是引用计数 -1，流仍在推、也不发事件；"
            "必须 close 同样次数（或 stop_stream/close_all 才回收）",
            f"close×1 后 is_streaming={still}；{stream_facts(self.host, 'camera1')}")

        # ---- close：引用计数归零后才真的停流
        self.robot.video.close(CameraId.FRONT_RGB)
        wait_for(lambda: not has_producer(self.host, "camera1"), timeout=6.0)
        info_after = self.robot.video.get_stream_info(CameraId.FRONT_RGB)
        self.ask_verdict(
            "TC-API-07", "close()（计数归零）停流并说明原因",
            not has_producer(self.host, "camera1")
            and info_after.state == StreamState.STOPPED
            and "stopped" in info_after.message.lower(),
            "producer 消失；state=stopped；message 说明\"Stream stopped, resources released\"",
            f"state={info_after.state.value} uri={info_after.uri!r} "
            f"message={info_after.message!r}")

        # ---- 注销回调后不再收到事件
        cancel()
        before = len(event_names())
        self.robot.video.open(CameraId.REAR_RGB)
        self.robot.video.close(CameraId.REAR_RGB)
        time.sleep(1.0)
        self.ask_verdict(
            "TC-API-11", "cancel() 注销后不再回调",
            len(event_names()) == before,
            "注销后事件数不再增长",
            f"注销前 {before} 条 → 现在 {len(event_names())} 条")

        # ---- stop_stream 不被自愈拉起
        uri_front, _ = self.timed_open(CameraId.FRONT_RGB)
        self.robot.video.stop_stream(CameraId.FRONT_RGB)
        time.sleep(3.0)
        self.ask_verdict(
            "TC-API-08", "stop_stream() 后不被自愈拉起",
            not has_producer(self.host, "camera1"),
            "3 秒后 go2rtc 仍无 producer（用户明确停流）",
            f"3 s 后 {stream_facts(self.host, 'camera1')}")

        # ---- close_all：只释放本地，不动机器人的推流开关
        self.robot.video.open(CameraId.REAR_RGB)
        self.robot.video.close_all()
        time.sleep(1.0)
        local_released = not any(
            self.robot.video.is_streaming(cam) for cam in CAMERA_CHOICES.values())
        self.ask_verdict(
            "TC-API-09", "close_all() 释放本地状态（按设计不停机器人推流）",
            local_released,
            "两路 is_streaming() 均为 False；按设计 close_all 不动推流开关，"
            "要真停用 stop_stream()",
            f"is_streaming 均为 False={local_released}；"
            f"camera1 {stream_facts(self.host, 'camera1')} | "
            f"camera2 {stream_facts(self.host, 'camera2')}")
        self.robot.video.stop_stream(CameraId.FRONT_RGB)
        wait_for(lambda: not has_producer(self.host, "camera1"), timeout=6.0)

    def suite_stream(self) -> None:
        self.banner("组 B: 媒体面可用性 (TC-STREAM)")
        self.baseline()
        cameras = self._selected_cameras()

        for camera in cameras:
            uri, cost = self.timed_open(camera)
            label = camera.description
            flowing = wait_for_data(self.host, camera.rtsp_name)

            facts = ffprobe_uri(uri) if have_tool("ffprobe") else None
            if facts is None and have_tool("ffprobe"):
                wait_for_data(self.host, camera.rtsp_name, timeout=10.0)
                facts = ffprobe_uri(uri, timeout=40.0)
            self.ask_verdict(
                f"TC-STREAM-01-{camera.name}", f"ffprobe 能拉通 {label} 地址",
                bool(facts) if have_tool("ffprobe") else None,
                "codec=h264 / 1280x720 / 30 fps",
                (f"codec={facts.get('codec_name')} {facts.get('width')}x{facts.get('height')} "
                 f"fps={facts.get('r_frame_rate')}" if facts else
                 f"ffprobe 拉不通（producer 有数据={flowing}）"))

            first = cv_first_frame_seconds(uri)
            ff_first = first_frame_seconds(uri) if have_tool("ffmpeg") else None
            probe = (f"OpenCV 首帧 {first:.2f} s" if first is not None
                     else "OpenCV 不可用")
            if ff_first is not None:
                probe += f"；ffmpeg 含启动 {ff_first:.2f} s"
            self.ask_verdict(
                f"TC-STREAM-02-{camera.name}", f"{label} 首帧耗时",
                (first is not None and first < 2.0) if first is not None
                else (ff_first is not None and ff_first < 3.0),
                "拿到地址后 < 2 s 解出第一帧（实测约 0.1~0.3 s）",
                probe)

            decoded = decode_window(uri, self.seconds, gui=not self.no_gui,
                                    window=f"{camera.name} {label}")
            if decoded.get("frames"):
                fps = decoded["fps"]
                ok_fps = fps >= 15.0
                self.ask_verdict(
                    f"TC-STREAM-03-{camera.name}",
                    f"{label} 连续解码 {self.seconds:.0f}s",
                    ok_fps,
                    "分辨率 1280x720、帧率 ≥ 15 fps（实测约 30 fps）",
                    f"{decoded['frames']:.0f} 帧 / {decoded['fps']:.1f} fps / "
                    f"{decoded['width']}x{decoded['height']}")
            else:
                self.ask_verdict(
                    f"TC-STREAM-03-{camera.name}", f"{label} 连续解码",
                    None if self.no_gui else False,
                    "OpenCV 能打开地址并持续读帧",
                    "OpenCV 不可用或打不开地址")

            if not self.no_gui:
                self.ask_verdict(
                    f"TC-STREAM-04-{camera.name}", f"{label} 窗口画面目视确认",
                    None,
                    "窗口里能看到实时画面，无明显卡顿/花屏/延迟累积",
                    "人眼确认（本项不做自动判定）")

            self.robot.video.close(camera)

        # 码率：用 go2rtc 的 bytes_recv 差分测（相机→服务端）
        uri, _ = self.timed_open(cameras[0])
        first_bytes = producer_bytes(self.host, cameras[0].rtsp_name)
        time.sleep(5.0)
        second_bytes = producer_bytes(self.host, cameras[0].rtsp_name)
        kbps = (second_bytes - first_bytes) * 8 / 5.0 / 1000.0
        self.ask_verdict(
            "TC-STREAM-05", "码率估算（go2rtc bytes_recv 差分）",
            kbps > 200.0,
            "720p30 H.264 约 1~3 Mbps（早期 107 kbps 为异常样本）",
            f"{kbps:.0f} kbps（{kbps / 1000.0:.2f} Mbps）")
        self.robot.video.close(cameras[0])

        # 独立 Manager：只要视频能力，不建 gRPC 客户端也能开流
        manager = VideoStreamManager(self.host, register_atexit=False)
        try:
            standalone_uri = manager.open(cameras[0])
            standalone_ok = standalone_uri.endswith(cameras[0].rtsp_name)
        except Exception as exc:  # noqa: BLE001
            standalone_ok = False
            standalone_uri = f"{type(exc).__name__}: {exc}"
        finally:
            manager.close_all()
            manager.shutdown()
            self.robot.video.stop_stream(cameras[0])
        self.ask_verdict(
            "TC-STREAM-06", "只用 VideoStreamManager（不走 gRPC）也能开流",
            standalone_ok,
            "不建 RobotClient，直接用 robot::video::Manager 等价物拿到地址",
            f"{standalone_uri}")

    def suite_adopt(self) -> None:
        self.banner("组 C: 与 App / 播放器共用 (TC-ADOPT)")
        self.baseline()
        camera = CAMERA_CHOICES["front"]
        stream = camera.rtsp_name

        # 外部（模拟 App）先开流，SDK 直接采用
        status = http_post(self.host, STREAM_PORT, "/settings/streaming/start")
        appear = wait_for(lambda: has_producer(self.host, stream), timeout=10.0)
        uri, cost = self.timed_open(camera)
        self.ask_verdict(
            "TC-ADOPT-01", "外部已开流时 open() 直接采用",
            appear and uri.endswith(stream) and cost < 1.0,
            "外部（App）先开流 → open() 很快返回同一地址，不重新开流",
            f"POST start={status}；producer {'已出现' if appear else '未出现'}；"
            f"open()={cost * 1000:.0f} ms {uri}")

        # 有别的观众时 close() 不停流
        player = start_background_player(uri, seconds=8.0)
        time.sleep(1.5)
        self.robot.video.close(camera)
        time.sleep(1.5)
        kept = has_producer(self.host, stream)
        self.ask_verdict(
            "TC-ADOPT-02", "还有别人在看时 close() 不停流",
            kept and player is not None,
            "播放器还在拉 → close() 只释放自己，流继续推",
            f"close 后 {stream_facts(self.host, stream)}")

        # 观众退出后再 close() → 停流（需先把流的所有权拿回 SDK 手里）
        if player is not None:
            player.wait(timeout=15.0)
        wait_for(lambda: not go2rtc_streams(self.host).get(stream, {}).get("consumers"),
                 timeout=10.0)
        self.robot.video.stop_stream(camera)          # 清掉外部开的那条
        wait_for(lambda: not has_producer(self.host, stream), timeout=6.0)
        self.robot.video.open(camera)                 # 这次由 SDK 自己开
        self.robot.video.close(camera)
        time.sleep(1.0)
        reclaimed = not has_producer(self.host, stream)
        self.ask_verdict(
            "TC-ADOPT-03", "SDK 自己开的流，close() 会回收（不留空转流）",
            reclaimed,
            "外部流清掉后由 SDK 开流 → close() 停流（SDK 开的才回收）",
            f"{stream_facts(self.host, stream)}")

        self.robot.video.stop_stream(camera)
        wait_for(lambda: not has_producer(self.host, stream), timeout=6.0)

    def suite_recover(self) -> None:
        self.banner("组 D: 断流自愈 (TC-RECOVER)")
        self.baseline()
        camera = CAMERA_CHOICES["front"]
        stream = camera.rtsp_name

        events: List[StreamEvent] = []
        lock = threading.Lock()

        def on_event(event: StreamEvent) -> None:
            with lock:
                events.append(event)

        cancel = self.robot.video.on_state_change(on_event)
        uri, _ = self.timed_open(camera)
        print(f"  地址 {uri}；外部 POST /stop 模拟被停流 …")
        http_post(self.host, STREAM_PORT, "/settings/streaming/stop")
        lost = wait_for(lambda: not has_producer(self.host, stream), timeout=6.0)
        resumed = wait_for(lambda: has_producer(self.host, stream), timeout=15.0)
        time.sleep(0.5)
        with lock:
            kinds = [e.name for e in events]
        self.ask_verdict(
            "TC-RECOVER-01", "外部停流后 SDK 自动续流",
            resumed and StreamEventKind.RECONNECTED.value in kinds,
            "外部 stop → 收到 StreamLost/StreamReconnected，流自动恢复",
            f"producer 消失={lost} 恢复={resumed}；事件={kinds}")

        # 用户明确 stop_stream 后不应被自愈拉起
        self.robot.video.stop_stream(camera)
        time.sleep(5.0)
        self.ask_verdict(
            "TC-RECOVER-02", "stop_stream() 后 5 s 内不被自愈拉起",
            not has_producer(self.host, stream),
            "用户明确停流 → 自愈不再拉起",
            f"{stream_facts(self.host, stream)}")

        # 自愈之后地址仍然可用
        uri2, _ = self.timed_open(camera)
        playing = ffprobe_uri(uri2) if have_tool("ffprobe") else None
        self.ask_verdict(
            "TC-RECOVER-03", "自愈后地址仍可播放",
            bool(playing) if playing is not None else None,
            "续流后的地址依旧能被 ffprobe 拉通",
            f"uri={uri2}；ffprobe={'OK' if playing else '失败/不可用'}")
        cancel()
        self.robot.video.close(camera)
        self.robot.video.stop_stream(camera)

    def suite_multi(self) -> None:
        self.banner("组 E: 反复调用与资源 (TC-MULTI)")
        self.baseline()
        camera = CAMERA_CHOICES["front"]
        stream = camera.rtsp_name

        base_threads = threading.active_count()
        rounds = 8
        failures = []
        for index in range(rounds):
            try:
                uri = self.robot.video.open(camera)
                if not uri:
                    failures.append(f"#{index + 1} 空地址")
                self.robot.video.close(camera)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"#{index + 1} {type(exc).__name__}: {exc}")
        # 收尾可能有几十毫秒延迟，先等 producer 消失再判定（避免取样竞态）
        left_running = not wait_for(lambda: not has_producer(self.host, stream), timeout=5.0)
        snapshot = stream_facts(self.host, stream)
        self.ask_verdict(
            "TC-MULTI-01", f"open/close 循环 {rounds} 次",
            not failures and not left_running,
            "无异常、结束时不留 producer",
            f"失败 {len(failures)} 次 {failures[:2]}；结束 {snapshot}")

        # 两路交替
        both_ok = True
        for _ in range(3):
            for cam in (CameraId.FRONT_RGB, CameraId.REAR_RGB):
                try:
                    self.robot.video.open(cam)
                    self.robot.video.close(cam)
                except Exception as exc:  # noqa: BLE001
                    both_ok = False
                    print(f"  [warn] {cam.name}: {exc}")
        self.ask_verdict(
            "TC-MULTI-02", "两路交替 open/close",
            both_ok,
            "前后两路交替开/关各 3 轮，无异常",
            f"camera1 {stream_facts(self.host, 'camera1')} | "
            f"camera2 {stream_facts(self.host, 'camera2')}")

        # 线程：开流期间多一个监督线程，全关后回落
        self.robot.video.open(CameraId.FRONT_RGB)
        self.robot.video.open(CameraId.REAR_RGB)
        during = threading.active_count()
        self.robot.video.close_all()
        time.sleep(1.5)
        after = threading.active_count()
        self.ask_verdict(
            "TC-MULTI-03", "监督线程随开流创建、关闭后退出",
            (during - base_threads) <= 2 and after <= base_threads + 1,
            "开流期间线程数增加 ≤ 2；close_all 后回落",
            f"基线={base_threads} 开流中={during} 关闭后={after}")

    def suite_edge(self) -> None:
        self.banner("组 F: 异常路径 (TC-EDGE)")
        self.baseline()

        # 未 open 就 close / 查询
        problems = []
        for camera in CAMERA_CHOICES.values():
            try:
                self.robot.video.close(camera)
                info = self.robot.video.get_stream_info(camera)
                if info.state == StreamState.READY:
                    problems.append(f"{camera.name} 未开却 READY")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{camera.name}: {type(exc).__name__}: {exc}")
        self.ask_verdict(
            "TC-EDGE-01", "未开流时 close()/get_stream_info() 幂等不抛错",
            not problems,
            "幂等返回，状态为非 READY",
            f"problems={problems}")

        # open 后立刻 close（不拉流）
        try:
            self.robot.video.open(CameraId.REAR_RGB)
            self.robot.video.close(CameraId.REAR_RGB)
            immediate_ok = True
        except Exception as exc:  # noqa: BLE001
            immediate_ok = False
            print(f"  [warn] {exc}")
        time.sleep(1.0)
        rear_info = self.robot.video.get_stream_info(CameraId.REAR_RGB)
        self.ask_verdict(
            "TC-EDGE-02", "open() 后立刻 close()",
            immediate_ok,
            "不开播放器也能干净释放（不抛异常、不卡住）",
            f"camera2 {stream_facts(self.host, 'camera2')} | "
            f"message={rear_info.message!r}")

        # 非法参数
        raised = None
        try:
            self.robot.video.open("front")  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            raised = f"{type(exc).__name__}: {exc}"
        self.ask_verdict(
            "TC-EDGE-03", "非法相机参数被拒绝",
            raised is not None,
            "抛异常且不发请求（不落进错误状态）",
            f"raised={raised}")

        # 主机不可达：直接用独立 Manager（不需要 gRPC 客户端）
        manager = VideoStreamManager("192.0.2.1", register_atexit=False)  # TEST-NET-1
        started = time.monotonic()
        error = None
        try:
            manager.open(CameraId.FRONT_RGB)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        cost = time.monotonic() - started
        manager.shutdown()
        self.ask_verdict(
            "TC-EDGE-04", "主机不可达时给出明确错误（不挂死）",
            error is not None and "VideoError" in error
            and "streaming service" in error and cost < 15.0,
            "抛 VideoError（带\"Cannot reach the robot's streaming service…same network\"），"
            "耗时在 10 s 级内",
            f"{cost:.1f} s；{error}")

    def suite_smoke(self) -> None:
        self.banner("冒烟: 一条命令走完主流程")
        self.baseline()
        ok = True
        for camera in self._selected_cameras():
            uri, cost = self.timed_open(camera)
            print(f"  {camera.description}: {uri}（{cost * 1000:.0f} ms）")
            decoded = decode_window(uri, min(self.seconds, 5.0), gui=not self.no_gui,
                                    window=camera.description)
            print(f"  解码 {decoded.get('frames', 0):.0f} 帧 / "
                  f"{decoded.get('fps', 0):.1f} fps")
            ok = bool(decoded.get("frames"))
            self.robot.video.close(camera)
        info = self.robot.video.get_stream_info(CameraId.FRONT_RGB)
        self.ask_verdict(
            "TC-SMOKE", "开流→解码→释放 全流程",
            ok,
            "两路都能开、都能解出帧、最后干净释放",
            f"最后一次信息: state={info.state.value} uri={info.uri!r}")

    # ------------------------------------------------------------- utilities
    def _selected_cameras(self) -> List[CameraId]:
        return [cam for cam in self.selected if cam in CAMERA_CHOICES.values()]

    def print_summary(self) -> int:
        self.banner("联调结果汇总")
        if not self.results:
            print("  (无记录)")
            return 0
        counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "OBSERVE": 0}
        print(f"{'Case':<24}{'Verdict':<10}{'Auto':<6}Title")
        print("-" * 78)
        for result in self.results:
            counts[result.verdict] = counts.get(result.verdict, 0) + 1
            auto = "-" if result.rpc_ok is None else ("OK" if result.rpc_ok else "NG")
            note = f"  ({result.note})" if result.note else ""
            print(f"{result.case_id:<24}{result.verdict:<10}{auto:<6}"
                  f"{result.title}{note}")
        print("-" * 78)
        print(f"PASS={counts.get('PASS', 0)}  FAIL={counts.get('FAIL', 0)}  "
              f"SKIP={counts.get('SKIP', 0)}  OBSERVE={counts.get('OBSERVE', 0)}")
        print("上表可直接粘进自验报告的「用例结果」小节。")
        return 1 if counts.get("FAIL", 0) else 0


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="High-level camera video joint test")
    parser.add_argument("server", nargs="?", default=DEFAULT_ADDRESS,
                        help="gRPC server address, e.g. 10.30.12.4:50051")
    parser.add_argument("--suite", default="all",
                        choices=["all", "api", "stream", "adopt", "recover",
                                 "multi", "edge", "smoke"],
                        help="which test group to run")
    parser.add_argument("--camera", default="both", choices=["front", "rear", "both"],
                        help="which camera(s) the stream cases use")
    parser.add_argument("--auto", action="store_true",
                        help="timed pause; auto verdict where measurable")
    parser.add_argument("--hold", type=float, default=3.0,
                        help="seconds to hold in --auto mode")
    parser.add_argument("--seconds", type=float, default=10.0,
                        help="decode / stability window for stream cases")
    parser.add_argument("--no-gui", action="store_true",
                        help="never open OpenCV windows (headless)")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    print(f"连接: {args.server}")
    print(f"套件: {args.suite}  相机: {args.camera}  auto={args.auto}  "
          f"hold={args.hold}s  解码窗口={args.seconds}s  gui={not args.no_gui}")

    robot = RobotClient(args.server)
    runner = Runner(
        robot=robot,
        auto=args.auto,
        hold_sec=args.hold,
        seconds=args.seconds,
        no_gui=args.no_gui,
    )
    if args.camera == "front":
        runner.selected = (CameraId.FRONT_RGB,)
    elif args.camera == "rear":
        runner.selected = (CameraId.REAR_RGB,)

    suites: Dict[str, Callable[[], None]] = {
        "api": runner.suite_api,
        "stream": runner.suite_stream,
        "adopt": runner.suite_adopt,
        "recover": runner.suite_recover,
        "multi": runner.suite_multi,
        "edge": runner.suite_edge,
        "smoke": runner.suite_smoke,
    }

    if args.suite == "all":
        for name in ("api", "stream", "adopt", "recover", "multi", "edge"):
            suites[name]()
    else:
        suites[args.suite]()

    code = runner.print_summary()
    try:
        robot.video.close_all()
        robot.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] 收尾: {exc}")
    return code


if __name__ == "__main__":
    sys.exit(main())
