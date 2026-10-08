"""离线测试用的最小 RTSP 服务端（也被 C++ 测试脚本复用）。

用真实 H.264 码流（ffmpeg 现场生成）伺候 SDK：完成

    OPTIONS → DESCRIBE(带 sprop-parameter-sets) → SETUP(interleaved) → PLAY
    → 交织 RTP（单包 / FU-A）→ TEARDOWN

这样「协议层 + 拉流后端」可以在没有机器人、没有网络的情况下完整回归。
"""

from __future__ import annotations

import base64
import json
import os
import select
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

from typing import List, Optional

_PY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "python"))
if _PY_ROOT not in sys.path:
    sys.path.insert(0, _PY_ROOT)


def split_nals(data: bytes) -> List[bytes]:
    """按 Annex-B 起始码切分 H.264 字节流（去掉起始码）。

    原先复用 ``dobot_quad.video.rtsp.split_nals``；媒体层已从 SDK 中删除
    （设计文档 §5.2），所以这里自带一份，仅供本测试服务端打包使用。
    """
    starts: List[tuple] = []
    i, n = 0, len(data)
    while i < n - 3:
        if data[i : i + 4] == b"\x00\x00\x00\x01":
            starts.append((i, 4))
            i += 4
        elif data[i : i + 3] == b"\x00\x00\x01":
            starts.append((i, 3))
            i += 3
        else:
            i += 1
    nals: List[bytes] = []
    for idx, (start, sc_len) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else n
        nal = data[start + sc_len : end].rstrip(b"\x00")
        if nal:
            nals.append(nal)
    return nals


FFMPEG = shutil.which("ffmpeg")
MTU = 1400
START_CODE = b"\x00\x00\x00\x01"


def _make_h264(path: str, profile: str = "main", width: int = 1280, height: int = 720) -> bytes:
    """用 ffmpeg 生成一小段真实 H.264（Annex-B）。"""
    import subprocess

    subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=30:duration=1",
            "-c:v", "libx264", "-profile:v", profile, "-pix_fmt", "yuv420p",
            "-f", "h264", path,
        ],
        check=True,
    )
    with open(path, "rb") as fp:
        return fp.read()


# =====================================================================
# 最小 RTSP 服务端（只服务本测试）
# =====================================================================


def _group_access_units(nals: List[bytes]) -> List[List[bytes]]:
    """按「VCL NAL 之后又出现 VCL NAL」切分访问单元。"""
    units: List[List[bytes]] = []
    current: List[bytes] = []
    has_vcl = False
    for nal in nals:
        nal_type = nal[0] & 0x1F
        if 1 <= nal_type <= 5:
            if has_vcl:
                units.append(current)
                current, has_vcl = [], False
            current.append(nal)
            has_vcl = True
        else:
            current.append(nal)
    if current:
        units.append(current)
    return units


def _rtp_packet(nal: bytes, seq: int, timestamp: int, marker: bool, ssrc: int) -> bytes:
    header = struct.pack(
        ">BBHII", 0x80, (0x80 if marker else 0x00) | 96, seq & 0xFFFF, timestamp, ssrc
    )
    return header + nal


def _packetize(nal: bytes, seq: int, timestamp: int, marker: bool, ssrc: int) -> List[bytes]:
    """单个 NAL → 一个或多个 RTP 包（单包模式 / FU-A）。"""
    if len(nal) <= MTU:
        return [_rtp_packet(nal, seq, timestamp, marker, ssrc)]

    packets: List[bytes] = []
    header = nal[0]
    body = nal[1:]
    offset = 0
    while offset < len(body):
        chunk = body[offset : offset + MTU - 2]
        offset += len(chunk)
        first = offset == len(chunk)
        last = offset >= len(body)
        fu_indicator = (header & 0xE0) | 28
        fu_header = (0x80 if first else 0) | (0x40 if last else 0) | (header & 0x1F)
        packets.append(
            _rtp_packet(
                bytes([fu_indicator, fu_header]) + chunk,
                seq,
                timestamp,
                marker and last,
                ssrc,
            )
        )
        seq += 1
    return packets


class MockRtspServer:
    """最小可用的 RTSP 服务端：Docker-free 地喂真实 H.264 给 SDK。"""

    def __init__(self, h264: bytes, *, fps: float = 200.0, limit_aus: int = 0) -> None:
        self._nals = split_nals(h264)
        self._units = _group_access_units(self._nals)
        self._sps = next((n for n in self._nals if n[0] & 0x1F == 7), b"")
        self._pps = next((n for n in self._nals if n[0] & 0x1F == 8), b"")
        self._fps = fps
        self._limit = limit_aus
        self._stop = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._sender: Optional[threading.Thread] = None
        self._sender_stop = threading.Event()
        self._write_lock = threading.Lock()
        self.port = 0
        self.requests: List[str] = []
        self.teardown_seen = threading.Event()
        self.clients_served = 0
        self.access_units_sent = 0

    # -- lifecycle ---------------------------------------------------

    def start(self) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(2)
        self._sock.settimeout(0.2)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._sock is not None:
            self._sock.close()

    # -- server ------------------------------------------------------

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except (OSError, AttributeError):
                continue
            self.clients_served += 1
            try:
                self._serve(conn)
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _serve(self, conn: socket.socket) -> None:
        buffer = bytearray()
        conn.settimeout(2.0)
        try:
            while not self._stop.is_set():
                request = self._read_request(conn, buffer)
                if request is None:
                    return
                method, headers = request
                self.requests.append(method)
                cseq = headers.get("cseq", "1")
                if method == "OPTIONS":
                    self._respond(
                        conn,
                        200,
                        "OK",
                        cseq,
                        {"Public": "OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN"},
                    )
                elif method == "DESCRIBE":
                    body = self._sdp().encode()
                    self._respond(
                        conn,
                        200,
                        "OK",
                        cseq,
                        {
                            "Content-Type": "application/sdp",
                            "Content-Base": f"rtsp://127.0.0.1:{self.port}/camera1/",
                            "Content-Length": str(len(body)),
                        },
                        body,
                    )
                elif method == "SETUP":
                    self._respond(
                        conn,
                        200,
                        "OK",
                        cseq,
                        {
                            "Transport": "RTP/AVP/TCP;unicast;interleaved=0-1",
                            "Session": "ABCDEF123456",
                        },
                    )
                elif method == "PLAY":
                    self._respond(conn, 200, "OK", cseq, {"Session": "ABCDEF123456"})
                    self._start_sender(conn)
                elif method == "TEARDOWN":
                    self._respond(conn, 200, "OK", cseq, {"Session": "ABCDEF123456"})
                    self.teardown_seen.set()
                    return
                else:
                    self._respond(conn, 501, "Not Implemented", cseq, {})
        finally:
            self._stop_sender()

    def _start_sender(self, conn: socket.socket) -> None:
        """PLAY 之后用独立线程持续下发 RTP，服务主循环只负责处理请求。"""
        self._stop_sender()
        self._sender_stop.clear()
        self._sender = threading.Thread(
            target=self._sender_loop, args=(conn,), daemon=True
        )
        self._sender.start()

    def _stop_sender(self) -> None:
        self._sender_stop.set()
        sender, self._sender = self._sender, None
        if sender is not None and sender.is_alive():
            sender.join(timeout=1.5)

    def _sender_loop(self, conn: socket.socket) -> None:
        seq = 1
        timestamp = 0
        ssrc = 0x12345678
        index = 0
        while not self._stop.is_set() and not self._sender_stop.is_set():
            if self._limit and index >= self._limit:
                return
            try:
                self._send_access_unit(conn, index, seq, timestamp, ssrc)
            except OSError:
                return
            self.access_units_sent += 1
            index += 1
            seq += 50
            timestamp += 3000
            time.sleep(1.0 / self._fps)

    def _send_access_unit(
        self, conn: socket.socket, index: int, seq: int, timestamp: int, ssrc: int
    ) -> None:
        unit = self._units[index % len(self._units)]
        packets: List[bytes] = []
        for position, nal in enumerate(unit):
            marker = position == len(unit) - 1
            packets.extend(_packetize(nal, seq, timestamp, marker, ssrc))
            seq = (seq + 1) & 0xFFFF
        payload = b"".join(b"$" + bytes([0]) + struct.pack(">H", len(p)) + p for p in packets)
        with self._write_lock:
            conn.sendall(payload)

    def _sdp(self) -> str:
        sprop = ",".join(
            base64.b64encode(nal).decode() for nal in (self._sps, self._pps) if nal
        )
        return (
            "v=0\r\n"
            "o=- 0 0 IN IP4 127.0.0.1\r\n"
            "s=Mock\r\n"
            "c=IN IP4 0.0.0.0\r\n"
            "t=0 0\r\n"
            "a=control:*\r\n"
            "m=video 0 RTP/AVP 96\r\n"
            "a=rtpmap:96 H264/90000\r\n"
            f"a=fmtp:96 packetization-mode=1;sprop-parameter-sets={sprop}\r\n"
            "a=framesize:96 1280-720\r\n"
            "a=control:trackID=0\r\n"
        )

    def _respond(
        self,
        conn: socket.socket,
        status: int,
        reason: str,
        cseq: str,
        headers: dict,
        body: bytes = b"",
    ) -> None:
        lines = [f"RTSP/1.0 {status} {reason}", f"CSeq: {cseq}"]
        lines.extend(f"{key}: {value}" for key, value in headers.items())
        payload = ("\r\n".join(lines) + "\r\n\r\n").encode() + body
        with self._write_lock:
            conn.sendall(payload)

    def _read_request(self, conn: socket.socket, buffer: bytearray):
        while b"\r\n\r\n" not in buffer:
            try:
                chunk = conn.recv(4096)
            except (socket.timeout, OSError):
                return None
            if not chunk:
                return None
            buffer.extend(chunk)
        index = buffer.find(b"\r\n\r\n")
        head = bytes(buffer[:index]).decode("latin-1")
        del buffer[: index + 4]
        lines = head.split("\r\n")
        method = lines[0].split(" ", 1)[0]
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
        return method, headers




def make_sample_h264(path: str, profile: str = "main", width: int = 1280, height: int = 720) -> bytes:
    """用 ffmpeg 生成一小段真实 H.264（Annex-B）。"""
    return _make_h264(path, profile, width, height)
