"""离线测试用：go2rtc 状态服务 + GControll 推流开关（真实 HTTP 服务）。

设计文档 §5.4 的四条决策（开流判据 R1/R2、卡住重启、关闭让路、强制停流）全部
依赖「对端可观测」，所以这里用两个**真实 HTTP 服务**复现对端行为：

* :class:`MockGo2Rtc` —— ``GET /api/streams``：``producers`` / ``consumers``
  / ``producers[].bytes_recv``（按真实时间增长，可「冻结」模拟推流卡住）；
* :class:`MockGControll` —— ``POST /settings/streaming/{start,stop}``：记录调用；
  并且复现真机的两个关键特性：**全局开关**（一次 ``start`` 让两路相机都有
  producer）与 **`start` 后延迟出现 producer**。
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

__all__ = ["MockGo2Rtc", "MockGControll", "MockRobotServices"]

DEFAULT_CAMERAS = ("camera1", "camera2")

#: 脚本槽里的「本请求走正常逻辑」哨兵（与「返回空响应」区分开）
NORMAL = object()


# =====================================================================
# go2rtc 状态服务
# =====================================================================
class _Stream:
    __slots__ = ("producer", "base_bytes", "since", "bps", "growing", "consumers", "producer_present")

    def __init__(self, bps: float) -> None:
        self.producer = False
        self.producer_present = False
        self.base_bytes = 0
        self.since = time.monotonic()
        self.bps = bps
        self.growing = True
        self.consumers: List[dict] = []

    def bytes_now(self) -> int:
        if not self.producer or not self.growing:
            return self.base_bytes
        return self.base_bytes + int(self.bps * (time.monotonic() - self.since))

    def start_pushing(self, bps: Optional[float] = None) -> None:
        """producer 出现，且 ``bytes_recv`` 从 0 重新开始增长（真机行为）。"""
        self.producer = True
        self.producer_present = True
        self.base_bytes = 0
        self.since = time.monotonic()
        self.growing = True
        if bps is not None:
            self.bps = bps

    def freeze(self) -> None:
        """推流卡住：``bytes_recv`` 停在当前值不再增长。"""
        self.base_bytes = self.bytes_now()
        self.growing = False

    def freeze_at_zero(self) -> None:
        """卡住且一个字节都没流过（严格 0，确定性）。

        直接 ``freeze()`` 会取「base + bps × 几微秒」作冻结值，可能算出 1~20 字节，
        于是下一次采样看起来像「增长」，测试会偶发不稳。
        """
        self.base_bytes = 0
        self.growing = False

    def drop_producer(self) -> None:
        self.producer = False
        self.producer_present = False
        self.base_bytes = 0
        self.growing = True


class _Go2RtcHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        mock: MockGo2Rtc = self.server.mock  # type: ignore[attr-defined]
        if self.path.split("?")[0] != "/api/streams":
            self.send_error(404)
            return
        with mock._lock:
            mock.request_count += 1
            now = time.monotonic()
            offline = mock._offline
            fixed_body = mock._body
            scripted = mock._take_script()
            body = None
            if fixed_body is not None:
                body = fixed_body.encode("utf-8")
            elif scripted is not NORMAL:
                body = None if scripted is None else str(scripted).encode("utf-8")
            else:
                payload: Dict[str, dict] = {}
                for name, stream in mock._streams.items():
                    if name in mock._hidden:
                        continue  # 响应里没有这一路流（≠ 没人看，≠ 没在推）
                    if not stream.producer_present:
                        payload[name] = {"producers": [], "consumers": list(stream.consumers)}
                    else:
                        payload[name] = {
                            "producers": [
                                {
                                    "format_name": "rtsp",
                                    "protocol": "rtsp+tcp",
                                    "remote_addr": "[::1]:59374",
                                    "bytes_recv": stream.bytes_now(),
                                }
                            ],
                            "consumers": list(stream.consumers),
                        }
                body = json.dumps(payload).encode("utf-8")
        if offline:
            # 模拟 go2rtc 不可达：直接断开连接
            try:
                self.connection.close()
            except OSError:
                pass
            return
        if mock.force_chunked or len(body) > 2048:
            # 真机（Go net/http）在响应体变大时改用 chunked —— 拉流时响应里会带上
            # 很长的 SDP，正好触发这条路径，因此这里也要能复现。
            mock.chunked_responses += 1
            if mock.chunked_split:
                mock.chunked_splits += 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for start in range(0, len(body), 512):
                piece = body[start:start + 512]
                self.wfile.write(f"{len(piece):x}\r\n".encode("ascii"))
                self.wfile.write(piece)
                if mock.chunked_split:
                    # 把「尾随 CRLF」推到下一个 TCP 段再发：网络上本来就会这样，
                    # 客户端必须把这种「还没读全」和「报文坏了」区分开。
                    self.wfile.flush()
                    time.sleep(0.05)
                self.wfile.write(b"\r\n")
            if mock.chunked_split:
                self.wfile.flush()
                time.sleep(0.05)
            self.wfile.write(b"0\r\n\r\n")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D102 - 静音
        pass


class MockGo2Rtc:
    """``GET /api/streams`` 的可控实现。"""

    def __init__(self, cameras=DEFAULT_CAMERAS, *, bps: float = 350_000.0) -> None:
        self._lock = threading.RLock()
        self._bps = float(bps)
        self._streams: Dict[str, _Stream] = {
            name: _Stream(self._bps) for name in cameras
        }
        self._hidden: set = set()
        self._offline = False
        self._body: Optional[str] = None
        #: 按请求顺序返回的响应体（最后一个重复）；``None`` = 该次仍走正常逻辑
        self._script: List[object] = []
        #: 模拟「重启推流也救不回来」：``start`` 后 producer 出现但立即卡住
        self.stuck = False
        #: 强制用 ``Transfer-Encoding: chunked`` 回响应（真机在响应体变大时就是这样）
        self.force_chunked = False
        self.chunked_responses = 0
        #: 把 chunk 的「尾随 CRLF」单独放在下一个 TCP 段发（覆盖客户端分帧解码）
        self.chunked_split = False
        self.chunked_splits = 0
        self.request_count = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Go2RtcHandler)
        self._server.daemon_threads = True
        self._server.mock = self  # type: ignore[attr-defined]
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, name="mock-go2rtc", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------ 生命周期
    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/streams"

    def close(self) -> None:
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:  # pragma: no cover
            pass

    def __enter__(self) -> "MockGo2Rtc":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ------------------------------------------------------------ 状态操纵
    def start_pushing(self, name: Optional[str] = None, *, bps: Optional[float] = None) -> None:
        """让某路（默认全部）出现 producer 并开始增长。"""
        with self._lock:
            for key in ([name] if name else list(self._streams)):
                stream = self._streams[key]
                stream.start_pushing(bps)
                self._hidden.discard(key)
                if self.stuck:
                    stream.freeze_at_zero()

    def drop_producer(self, name: Optional[str] = None) -> None:
        """让某路（默认全部）的 producer 消失。"""
        with self._lock:
            for key in ([name] if name else list(self._streams)):
                self._streams[key].drop_producer()

    def freeze(self, name: Optional[str] = None) -> None:
        """推流卡住：``bytes_recv`` 不再增长。"""
        with self._lock:
            for key in ([name] if name else list(self._streams)):
                self._streams[key].freeze()

    def add_consumer(self, name: str, *, ua: str = "Lavf/60.16.100", addr: str = "10.0.0.5:41000") -> None:
        """模拟「有别人在看」（App / 用户自己的播放器）。"""
        with self._lock:
            self._streams[name].consumers.append(
                {"remote_addr": addr, "user_agent": ua, "id": f"{name}-{addr}"}
            )

    def clear_consumers(self, name: Optional[str] = None) -> None:
        with self._lock:
            for key in ([name] if name else list(self._streams)):
                self._streams[key].consumers.clear()

    def has_producer(self, name: str) -> bool:
        with self._lock:
            return self._streams[name].producer_present

    def bytes_recv(self, name: str) -> int:
        with self._lock:
            return self._streams[name].bytes_now()

    def hide(self, name: str, hidden: bool = True) -> None:
        """让响应里**没有**这一路流（用于「看不到」与「没人看」的区分）。"""
        with self._lock:
            self._hidden.add(name) if hidden else self._hidden.discard(name)

    def set_offline(self, offline: bool = True) -> None:
        """go2rtc 不可达。"""
        with self._lock:
            self._offline = offline

    def set_body(self, body: Optional[str]) -> None:
        """直接指定响应体（``None`` 表示恢复默认；``""`` 表示空响应）。"""
        with self._lock:
            self._body = body

    def set_body_script(self, bodies) -> None:
        """按**请求顺序**逐个返回响应体（最后一个会一直重复）。

        ``NORMAL`` 表示该次仍走正常逻辑（便于「先正常、再异常」的序列）。
        用来确定性地覆盖 probe 的异常分支：非法 JSON / 非对象 / 缺流 /
        流项不是对象 / ``bytes_recv`` 不是数字 / 两次采样结果不一致。
        """
        with self._lock:
            self._script = list(bodies)

    def _take_script(self):
        """取下一个脚本项（调用方必须已持有锁）。"""
        if not self._script:
            return NORMAL
        if len(self._script) > 1:
            return self._script.pop(0)
        return self._script[0]


# =====================================================================
# GControll 推流开关
# =====================================================================
class _GControllHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        mock: MockGControll = self.server.mock  # type: ignore[attr-defined]
        path = self.path.split("?")[0]
        if path not in ("/settings/streaming/start", "/settings/streaming/stop"):
            self.send_error(404)
            return
        action = path.rsplit("/", 1)[-1]
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        fail = mock._record(action)
        body = json.dumps({"success": not fail}).encode("utf-8")
        self.send_response(500 if fail else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D102 - 静音
        pass


class MockGControll:
    """``POST /settings/streaming/{start,stop}`` 的可控实现（**全局开关**）。"""

    def __init__(
        self,
        go2rtc: Optional[MockGo2Rtc] = None,
        *,
        start_delay: float = 0.15,
        stop_delay: float = 0.0,
    ) -> None:
        self._lock = threading.RLock()
        self.go2rtc = go2rtc
        self.start_delay = float(start_delay)
        self.stop_delay = float(stop_delay)
        self.calls: List[str] = []
        self.fail_next_start = 0
        self._timers: List[threading.Timer] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _GControllHandler)
        self._server.daemon_threads = True
        self._server.mock = self  # type: ignore[attr-defined]
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, name="mock-gcontroll", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------ 生命周期
    def close(self) -> None:
        for timer in self._timers:
            timer.cancel()
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:  # pragma: no cover
            pass

    def __enter__(self) -> "MockGControll":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def set_unreachable(self) -> None:
        """模拟 ``:22000`` 不可达（监听 socket 关闭）。"""
        try:
            self._server.server_close()
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------ 断言辅助
    @property
    def start_calls(self) -> int:
        return self.calls.count("start")

    @property
    def stop_calls(self) -> int:
        return self.calls.count("stop")

    def reset_calls(self) -> None:
        with self._lock:
            self.calls.clear()

    def wait_for_start(self, count: int = 1, timeout: float = 2.0) -> bool:
        return self._wait_for(lambda: self.start_calls >= count, timeout)

    def wait_for_stop(self, count: int = 1, timeout: float = 2.0) -> bool:
        return self._wait_for(lambda: self.stop_calls >= count, timeout)

    @staticmethod
    def _wait_for(predicate, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    # ------------------------------------------------------------ 内部
    def _record(self, action: str) -> bool:
        """记录调用并触发副作用（复现真机行为）。返回是否应返回 500。"""
        with self._lock:
            self.calls.append(action)
            if action == "start":
                if self.fail_next_start > 0:
                    self.fail_next_start -= 1
                    return True
                delay = self.start_delay
            else:
                delay = self.stop_delay
        if self.go2rtc is not None:
            if action == "start":
                self._schedule(delay, self.go2rtc.start_pushing)
            else:
                self._schedule(delay, self.go2rtc.drop_producer)
        return False

    def _schedule(self, delay: float, func) -> None:
        if delay <= 0:
            func()
            return
        timer = threading.Timer(delay, func)
        timer.daemon = True
        with self._lock:
            self._timers.append(timer)
        timer.start()


# =====================================================================
# 组合：一个「机器人」
# =====================================================================
class MockRobotServices:
    """go2rtc + GControll，行为对齐真机（全局开关、start 后延迟出 producer）。"""

    def __init__(self, cameras=DEFAULT_CAMERAS, *, bps: float = 350_000.0, start_delay: float = 0.15) -> None:
        self.go2rtc = MockGo2Rtc(cameras, bps=bps)
        self.gcontroll = MockGControll(self.go2rtc, start_delay=start_delay)
        self.cameras = tuple(cameras)

    def close(self) -> None:
        self.gcontroll.close()
        self.go2rtc.close()

    def __enter__(self) -> "MockRobotServices":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def port_open(self, port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False
