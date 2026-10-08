#!/usr/bin/env python3
"""C++ robot.video（控制面）离线自检驱动。

不需要机器人、不需要网络：

    # 先编译被测程序（不依赖 grpc / protobuf）
    cd high_level/cpp && g++ -std=c++14 -O2 -I. -I../test/cpp \\
        ../test/cpp/video_mock_check.cpp -o /tmp/video_mock_check -lpthread

    python3 high_level/test/cpp/run_video_mock_check.py --binary /tmp/video_mock_check

启动的 mock（都在 127.0.0.1，见 test/python/mock_go2rtc.py）：
  * **mock go2rtc**  —— ``/api/streams``：``producers`` / ``consumers`` /
    ``bytes_recv``（按真实时间增长，可冻结、可摘掉、可整机离线）；
  * **mock GControll** —— ``/settings/streaming/{start,stop}``：记录调用，并复现
    真机行为（**全局开关**：一次 start 让两路都出 producer；start 后延迟出现）。

验证 C++ 侧与 Python 侧行为一致：开流等「有数据在流」、卡住重启、断流续流、
关闭时给别人让路。
"""

from __future__ import annotations

import argparse
import os
import queue
import subprocess
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY_TEST = os.path.abspath(os.path.join(_HERE, "..", "python"))
if _PY_TEST not in sys.path:
    sys.path.insert(0, _PY_TEST)

from mock_go2rtc import NORMAL, MockRobotServices # noqa: E402

RTSP_PORT = 18554


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list = []

    def ok(self, name: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.passed += 1
            print(f" [ok]  {name}")
        else:
            self.failures.append(f"{name}: {detail}")
            print(f" [FAIL] {name} -> {detail}")
        return bool(condition)


class Harness:
    """把 C++ 被测程序当成一个「命令行客户端」来驱动。"""

    def __init__(self, binary: str, services: MockRobotServices, extra_args=()) -> None:
        self.services = services
        self.events: list = []
        self.protocol_errors: list = []
        self.lines: list = []
        self._lines_lock = threading.Lock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._proc = subprocess.Popen(
            [
                binary,
                "--gcontroll-port", str(services.gcontroll.port),
                "--go2rtc-port", str(services.go2rtc.port),
                "--rtsp-port", str(RTSP_PORT),
                *extra_args,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # ------------------------------------------------------------------ 内部
    def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            line = raw.rstrip("\n")
            if line.startswith("# event "):
                self.events.append(tuple(line.split()[2:]))
            with self._lines_lock:
                self.lines.append(line)
            self._queue.put(line)

    # ------------------------------------------------------------------ API
    def send(self, line: str) -> None:
        """只下发命令、不等结果（用于「命令执行期间还要改 mock 状态」的场景）。"""
        assert self._proc.stdin is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def collect(self, timeout: float = 8.0) -> list:
        out: list = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                out.append("# TIMEOUT")
                break
            try:
                item = self._queue.get(timeout=remaining)
            except queue.Empty:
                out.append("# TIMEOUT")
                break
            if item == "# done":
                break
            out.append(item)
        for item in out:
            if item.startswith("# err") or item.startswith("# TIMEOUT"):
                self.protocol_errors.append(f"命令 -> {item}")
        return out

    def cmd(self, line: str, timeout: float = 8.0) -> list:
        """下发一条命令，返回它产生的输出行（不含 ``# done``）。

        任何 ``# err`` / 超时都会被记入 ``protocol_errors``：命令没被执行到是最
        危险的情况（断言会「假通过」），所以这里零容忍。
        """
        self.send(line)
        return self.collect(timeout)

    def wait_for_line(self, predicate, timeout: float = 3.0) -> bool:
        """等输出里出现满足条件的行（命令执行中也能用）。"""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lines_lock:
                if any(predicate(line) for line in self.lines):
                    return True
            time.sleep(0.01)
        return False

    def event_names(self) -> list:
        return [event[0] for event in self.events]

    def clear_events(self) -> None:
        self.events.clear()
        self.cmd("clear_events")

    def close(self) -> None:
        scan_protocol(self)
        try:
            self.cmd("quit", timeout=3.0)
        except Exception: # pragma: no cover
            pass
        try:
            assert self._proc.stdin is not None
            self._proc.stdin.close()
        except Exception: # pragma: no cover
            pass
        try:
            self._proc.wait(timeout=5)
        except Exception: # pragma: no cover
            self._proc.kill()


def wait_for(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


PROTOCOL_ERRORS: list = []


def scan_protocol(harness: "Harness") -> None:
    """把被测程序的协议错误（# err / 超时）汇总进全局，最后统一报错。"""
    for item in harness.protocol_errors:
        if item not in PROTOCOL_ERRORS:
            PROTOCOL_ERRORS.append(item)


# =====================================================================
# 场景
# =====================================================================
def scenario_open_and_adopt(check: Checker, binary: str) -> None:
    print("== 场景 1：开流 / 采用已在推的流 / 编号映射 ==")
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            # 1a 流已在推（App 在看）→ 采用，且**不碰开关**
            services.go2rtc.start_pushing()
            time.sleep(0.05)
            out = harness.cmd("open front")
            check.ok("采用已在推的流时 open() 成功", any(l.startswith("# uri ") for l in out), out)
            check.ok(
                "uri 用 RTSP 流名 camera1",
                any(l.strip().endswith(f"rtsp://127.0.0.1:{RTSP_PORT}/camera1") for l in out),
                out,
            )
            check.ok("采用路径不产生任何开关调用", services.gcontroll.calls == [], services.gcontroll.calls)
            out = harness.cmd("state front")
            check.ok("采用路径 owner=external", any("external" in l for l in out), out)
            check.ok("采用路径 state=ready", any("ready" in l for l in out), out)
            check.ok("is_streaming() == 1", harness.cmd("streaming front")[0].endswith("1"))

            # 1b 重复 open 不重复开流
            services.gcontroll.reset_calls()
            harness.cmd("open front")
            check.ok("重复 open 不重复下发 start", services.gcontroll.start_calls == 0)

            # 1c close 时有人在看 → 不停流；无人看且不是自己开的 → 也不停流
            harness.cmd("close front")
            check.ok("还有使用者时 close 不停流", services.gcontroll.calls == [], services.gcontroll.calls)
            harness.cmd("close front")
            check.ok(
                "外部流（不是 SDK 开的）close 不发 stop",
                services.gcontroll.calls == [],
                services.gcontroll.calls,
            )
            out = harness.cmd("state front")
            check.ok("外部流关闭后说明「不是本 SDK 开启」", any("not started by this SDK" in l for l in out), out)
            harness.cmd("close_all")
            check.ok("close_all 不发 HTTP", services.gcontroll.calls == [], services.gcontroll.calls)

            # 1d 冷启动：流不存在 → start → ready（判据 R1+R2）
            services.go2rtc.drop_producer()
            services.gcontroll.reset_calls()
            harness.clear_events()
            out = harness.cmd("open rear")
            check.ok("冷启动 open() 返回地址", any("/camera2" in l for l in out), out)
            check.ok("冷启动下发了一次 start", services.gcontroll.start_calls == 1, services.gcontroll.calls)
            out = harness.cmd("state rear")
            check.ok("冷启动 owner=sdk", any("sdk" in l for l in out), out)
            check.ok("冷启动发过 StreamReady", "StreamReady" in harness.event_names(), harness.event_names())

            # 1e 引用计数：两次 open + 一次 close → 不停流
            services.gcontroll.reset_calls()
            harness.cmd("open rear")
            harness.cmd("close rear")
            check.ok("还有使用者时 close 不停流", services.gcontroll.calls == [], services.gcontroll.calls)
            harness.cmd("close rear")
            check.ok("最后一个使用者 close 时停流", services.gcontroll.stop_calls == 1, services.gcontroll.calls)
            harness.cmd("close_all")

            # 1f 「在推但不动」的外部流不能被采用：bytes_recv 非零只是历史值
            #    （stop_stream() 之后就是这样），采用它会拿到一个 404 的地址。
            #    正确动作是幂等 start 接管，再由正常逻辑自愈成 ready。
            harness.cmd("close_all")
            services.gcontroll.reset_calls()
            services.go2rtc.start_pushing()
            time.sleep(0.12)  # 攒出非零的历史字节数
            services.go2rtc.freeze()  # 之后不再增长
            out = harness.cmd("open front", timeout=20.0)
            check.ok("接管后返回地址（自愈成功）", any(l.startswith("# uri ") for l in out), out)
            check.ok("接管时下发了一次 start（不是白拿别人的流）", services.gcontroll.start_calls == 1,
                     services.gcontroll.calls)
            out = harness.cmd("state front")
            check.ok("接管后 owner=sdk", "sdk" in " ".join(out) and "external" not in " ".join(out), out)
            harness.cmd("close_all")
        finally:
            harness.close()


def scenario_recovery(check: Checker, binary: str) -> None:
    print("== 场景 2：断流续流（L1）/ 卡住重启（L2）/ 上限（L3）==")
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            harness.cmd("open front")
            services.gcontroll.reset_calls()
            harness.clear_events()

            # 2a 外部关流 → L1 续流（只 start，不 stop）
            services.go2rtc.drop_producer()
            out = harness.cmd("wait_event 2 3.0")
            check.ok("外部关流后发出事件", "event-ok" in " ".join(out), out)
            names = harness.event_names()
            check.ok("报出 StreamLost(external)", "StreamLost" in names, names)
            check.ok("报出 StreamReconnected", "StreamReconnected" in names, names)
            check.ok(
                "L1 续流只 start，不 stop",
                services.gcontroll.start_calls >= 1 and services.gcontroll.stop_calls == 0,
                services.gcontroll.calls,
            )
            check.ok("恢复后 state=ready", "ready" in harness.cmd("state front")[0])

            # 2b 推流卡住 → L2 重启（stop + start）
            services.gcontroll.reset_calls()
            harness.clear_events()
            services.go2rtc.freeze()
            out = harness.cmd("wait_event 2 3.0")
            check.ok("卡住被检出并恢复", "event-ok" in " ".join(out), out)
            check.ok(
                "卡住时执行了 stop + start",
                services.gcontroll.stop_calls >= 1 and services.gcontroll.start_calls >= 1,
                services.gcontroll.calls,
            )
            check.ok(
                "恢复事件标明 L2_restart",
                any(len(e) > 5 and e[5] == "L2_restart" for e in harness.events),
                harness.events,
            )
            check.ok("卡住自愈后回到 ready", "ready" in harness.cmd("state front")[0])

            # 2c 反复卡住救不回来 → ERROR（自愈不能变风暴）
            services.go2rtc.stuck = True
            harness.clear_events()
            services.go2rtc.freeze()
            services.gcontroll.reset_calls()
            out = harness.cmd("wait_state front error 6.0")
            check.ok("反复卡住最终进入 error", "state-ok" in " ".join(out), out)
            check.ok(
                "重启次数受上限约束",
                services.gcontroll.stop_calls <= 2,
                services.gcontroll.calls,
            )
            calls_at_error = list(services.gcontroll.calls)
            time.sleep(0.4)
            check.ok("error 之后不再自动动作", services.gcontroll.calls == calls_at_error, services.gcontroll.calls)
            check.ok("error 时 is_streaming()==0", harness.cmd("streaming front")[0].endswith("0"))

            # 2d 新 open() 能重试
            services.go2rtc.stuck = False
            services.go2rtc.drop_producer()
            out = harness.cmd("open front")
            check.ok("error 后重新 open() 可恢复", any(l.startswith("# uri ") for l in out), out)
            harness.cmd("close_all")
        finally:
            harness.close()


def scenario_close_decision(check: Checker, binary: str) -> None:
    print("== 场景 3：关闭决策（consumers 驱动）与强制停流 ==")
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            # 3a go2rtc 看不到 → 安全侧：不发 stop
            harness.cmd("open front")
            services.gcontroll.reset_calls()
            services.go2rtc.set_offline(True)
            harness.cmd("close front")
            check.ok("看不到 consumers 时不停流（安全侧）", services.gcontroll.calls == [], services.gcontroll.calls)
            services.go2rtc.set_offline(False)
            out = harness.cmd("state front")
            check.ok("close 后仍能读到「最后一次已知状态」", any("stopped" in l for l in out), out)

            # 3b 没人看 → 停流（包括「本进程早先自己开过、这次只是采纳」的情形）
            services.gcontroll.reset_calls()
            harness.cmd("open front")
            services.gcontroll.reset_calls()
            harness.cmd("close front")
            check.ok("无人观看时停流（含采纳自己早先开的流）", services.gcontroll.stop_calls == 1, services.gcontroll.calls)

            # 3c 有人在看（App）→ 让路
            services.go2rtc.add_consumer("camera1", ua="Mozilla/5.0 (uni-app)")
            harness.cmd("open front")
            services.gcontroll.reset_calls()
            harness.cmd("close front")
            check.ok("App 在看时 close() 让路", services.gcontroll.calls == [], services.gcontroll.calls)
            services.go2rtc.clear_consumers()

            # 3d stop_stream：强停且不被自愈拉起来
            services.gcontroll.reset_calls()
            harness.cmd("open front")
            harness.cmd("stop_stream front")
            check.ok("stop_stream 直接下发 stop", services.gcontroll.stop_calls == 1, services.gcontroll.calls)
            check.ok("stop_stream 后 is_streaming()==0", harness.cmd("streaming front")[0].endswith("0"))
            time.sleep(0.4)
            check.ok("强停后各相机都不再自愈", services.gcontroll.start_calls == 0, services.gcontroll.calls)
            check.ok("强停后 producer 确实没了", services.go2rtc.has_producer("camera1") is False)
            check.ok("stop 是全局开关：另一路也归零", harness.cmd("streaming rear")[0].endswith("0"))
            harness.cmd("close_all")
        finally:
            harness.close()


# =====================================================================
# 场景 4：异常响应 / 单元自检 / Manager 边界
# =====================================================================
def scenario_internals(check: Checker, binary: str) -> None:
    print("== 场景 4：异常响应 / 单元自检 / Manager 边界 ==")
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            # 4a 单元自检（枚举 / JSON / HTTP / Manager / Arbiter 构造）
            out = harness.cmd("selfcheck", timeout=60.0)
            failed = [l for l in out if l.startswith("# check") and not l.endswith(" ok")]
            check.ok("单元自检无失败项", not failed, failed[:4])
            check.ok("单元自检整体通过", any(l.strip() == "# selfcheck ok" for l in out), out[-2:])

            # 4a-2 非法 CameraId：立刻拒绝，而且**一个请求都不发**。
            #     用 mock 的请求计数证明「没发请求」：先把本地状态收干净、等监督线程
            #     退掉（它闲置时不会轮询），再取前后差值。
            harness.cmd("close_all")
            time.sleep(0.6)
            requests_before = services.go2rtc.request_count
            out = harness.cmd("bad_camera", timeout=10.0)
            requests_after = services.go2rtc.request_count
            ran = any(l.strip() == "# bad-camera rejected=6" for l in out)
            check.ok(
                "非法 CameraId 在 6 个入口都被拒绝",
                ran,
                out,
            )
            check.ok(
                "非法 CameraId 不发任何请求",
                ran and requests_after == requests_before,
                f"go2rtc 请求数 {requests_before} -> {requests_after}",
            )

            # 4b 未开流 / 重复关闭等边界
            out = harness.cmd("state rear")
            check.ok("未开流的相机返回默认信息", any("stopped" in l for l in out), out)
            harness.cmd("close rear")
            harness.cmd("close_all")
            harness.cmd("close_all")
            check.ok("重复 close / close_all 幂等", True)

            # 4c go2rtc 响应体异常：不能崩、不能误判为断流
            harness.cmd("open front")
            harness.clear_events()
            for body in ("{ not json", "[1, 2, 3]", '{"camera1": 42}'):
                services.go2rtc.set_body_script([body])
                time.sleep(0.2)
                state = harness.cmd("state front")[0]
                check.ok(f"异常响应体不影响状态（{body[:14]}…）", "ready" in state, state)
            check.ok(
                "「看不到」不产生断流事件（安全侧）",
                not any("StreamLost" in event[0] for event in harness.events),
                harness.event_names(),
            )

            # 4c-2 bytes_recv 非法 → 被读成 0 ＝「在推但没数据」→ 必须由 R2 检出并自愈
            services.go2rtc.set_body_script(
                ['{"camera1": {"producers": [{"bytes_recv": "oops"}], "consumers": []}}']
            )
            check.ok(
                "非法 bytes_recv 被当成「没数据」并由 R2 检出",
                harness.wait_for_line(lambda line: line.startswith("# event StreamLost"), 3.0),
                harness.event_names(),
            )
            services.go2rtc.set_body_script([NORMAL])
            check.ok(
                "恢复正常响应体后能回到 ready",
                wait_for(lambda: "ready" in harness.cmd("state front", timeout=3.0)[0], 6.0),
                harness.cmd("state front")[0],
            )

            # 4d 开关首次返回 500 → 自动重试
            services.go2rtc.drop_producer()
            services.gcontroll.reset_calls()
            services.gcontroll.fail_next_start = 1
            out = harness.cmd("open rear", timeout=15.0)
            check.ok("start 首次 500 会自动重试并成功", any("/camera2" in l for l in out), out)
            check.ok("确实重试了 start", services.gcontroll.start_calls >= 2, services.gcontroll.calls)
            harness.cmd("close_all") # 收摊：后面的自检里 close() 才不会再发事件

            # 4e 缺流 / 非对象项 / 非对象 producer、consumer（探针解析的防御分支）
            # 注意：响应里故意不放 camera1 —— 既覆盖「缺流」分支，又不会打扰已就绪的前路
            crafted = (
                '{"camera2": {"producers": [1, {"bytes_recv": 5}],'
                ' "consumers": [1, {"addr": "10.0.0.9:1"}]}}'
            )
            services.go2rtc.set_body_script([crafted])
            out = harness.cmd("selfcheck", timeout=60.0)
            check.ok(
                "自定义响应体下自检仍通过",
                any(l.strip() == "# selfcheck ok" for l in out),
                [l for l in out if "FAIL" in l][:3],
            )
            services.go2rtc.set_body_script([NORMAL])

            # 4f 真机在响应体变大时会改用 chunked（拉流时响应带 SDP 就会触发）：
            #    自检与开流都必须照常工作。这里连「尾随 CRLF 落到下一个 TCP
            #    段」一起覆盖 —— 分帧解码最容易在这里写错（把「还没读全」当成
            #    「报文坏了」）。
            services.go2rtc.force_chunked = True
            services.go2rtc.chunked_split = True
            out = harness.cmd("selfcheck", timeout=60.0)
            check.ok(
                "chunked + 分片到达（CRLF 在下一段）下自检通过",
                any(l.strip() == "# selfcheck ok" for l in out),
                [l for l in out if "FAIL" in l or l.startswith("# diag")][:4],
            )
            check.ok(
                "mock 确实用了 chunked",
                services.go2rtc.chunked_responses > 0,
                services.go2rtc.chunked_responses,
            )
            check.ok(
                "mock 确实把 CRLF 拆到了下一段",
                services.go2rtc.chunked_splits > 0,
                services.go2rtc.chunked_splits,
            )
            services.go2rtc.chunked_split = False
            out = harness.cmd("open front", timeout=20.0)
            check.ok("chunked 响应体下 open() 正常", any(l.startswith("# uri ") for l in out), out)
            harness.cmd("close_all")
            services.go2rtc.force_chunked = False

            harness.cmd("open front", timeout=15.0) # 先建立会话（正常响应体）
            harness.clear_events()
            services.go2rtc.set_body_script([crafted]) # 再制造「缺流 / 非法项」
            time.sleep(0.3)
            check.ok(
                "缺流/非法项不产生断流事件（看不到≠断流）",
                not any("StreamLost" in event[0] for event in harness.events),
                harness.event_names(),
            )
            state = harness.cmd("state front", timeout=5.0)[0]
            check.ok("缺流不改变已就绪状态", "ready" in state, state)
            services.go2rtc.set_body_script([NORMAL])
            state = harness.cmd("state front", timeout=5.0)[0]
            check.ok("恢复响应后仍为 ready", "ready" in state, state)

            # 4f 关闭判定：两次采样不一致 → 安全侧（不停流）
            with_consumer = (
                '{"camera1": {"producers": [], "consumers": [{"remote_addr": "10.0.0.9:1"}]},'
                ' "camera2": {"producers": [], "consumers": []}}'
            )
            without = '{"camera1": {"producers": [], "consumers": []}, "camera2": {"producers": [], "consumers": []}}'
            services.go2rtc.set_body_script([with_consumer, with_consumer, without, without])
            services.gcontroll.reset_calls()
            harness.cmd("close front", timeout=10.0)
            check.ok(
                "采样不一致时 close 让路（安全侧，不发 stop）",
                services.gcontroll.stop_calls == 0,
                services.gcontroll.calls,
            )
            services.go2rtc.set_body_script([NORMAL])

            # 4g 准备阶段超时（两种前置状态，各自覆盖一条 fail 分支）
            # 「流不存在」：用 hide 让响应里根本没这一路（与「有人看」区分开）
            harness.cmd("close_all")
            services.go2rtc.drop_producer()
            services.go2rtc.hide("camera2")
            out = harness.cmd("selfcheck_deadline_no_producer", timeout=20.0)
            check.ok(
                "准备阶段：流不存在且超时 → 判失败",
                any(l.strip() == "# selfcheck ok" for l in out),
                out[-3:],
            )
            services.go2rtc.hide("camera2", False)
            services.go2rtc.stuck = True
            services.go2rtc.start_pushing() # producer 在，但 bytes_recv 冻结在 0
            out = harness.cmd("selfcheck_deadline_no_growth", timeout=20.0)
            check.ok(
                "准备阶段：在推但无数据且超时 → 判失败",
                any(l.strip() == "# selfcheck ok" for l in out),
                out[-3:],
            )
            harness.cmd("close_all")
        finally:
            harness.close()


# =====================================================================
# 场景 5：失败与放弃路径
# =====================================================================
def scenario_failure_paths(check: Checker, binary: str) -> None:
    print("== 场景 5：失败与放弃路径 ==")

    # 5a 开关不可达 → port_unreachable（不计重试风暴）
    with MockRobotServices(start_delay=0.05) as services:
        services.gcontroll.set_unreachable()
        harness = Harness(binary, services)
        try:
            out = harness.cmd("open front", timeout=15.0)
            check.ok("开关不可达 → port_unreachable", any("port_unreachable" in l for l in out), out)
            check.ok(
                "不能到达机器人 → 抛 VideoConnectionError（可按子类 catch）",
                any("# open-error VideoConnectionError port_unreachable" in l for l in out),
                out,
            )
            check.ok("错误文案给出下一步动作", any("same network" in l for l in out), out)
        finally:
            harness.close()

    # 5b start 返回 200 但永远没数据 → no_data（不返回假地址）
    with MockRobotServices(start_delay=0.05) as services:
        services.gcontroll.go2rtc = None # start 成功，但 producer 永不会出现
        harness = Harness(binary, services)
        try:
            out = harness.cmd("open front", timeout=15.0)
            check.ok("start 200 但无数据 → no_data", any("no_data" in l for l in out), out)
            check.ok(
                "开始后一直没有数据 → 抛 VideoTimeoutError（可按子类 catch）",
                any("# open-error VideoTimeoutError no_data" in l for l in out),
                out,
            )
            check.ok("开流失败不发 stop（保守）", services.gcontroll.stop_calls == 0, services.gcontroll.calls)
        finally:
            harness.close()

    # 5c 准备阶段就卡住（producers 在、bytes 不动）→ stall，且受重启上限约束
    with MockRobotServices(start_delay=0.05) as services:
        services.go2rtc.stuck = True
        harness = Harness(binary, services)
        try:
            out = harness.cmd("open front", timeout=20.0)
            check.ok("准备阶段卡住 → 最终 stall", any("stall" in l for l in out), out)
            check.ok(
                "准备阶段也受重启上限约束",
                services.gcontroll.stop_calls <= 2,
                services.gcontroll.calls,
            )
        finally:
            harness.close()

    # 5d 恢复反复失败 → error（尝试次数用尽）
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            harness.cmd("open front")
            services.gcontroll.go2rtc = None
            services.go2rtc.drop_producer()
            out = harness.cmd("wait_state front error 12.0", timeout=15.0)
            text = " ".join(out)
            check.ok("恢复反复失败 → error", "state-ok" in text, out)
            check.ok("放弃原因说明已尝试次数", "attempts" in text, out)
        finally:
            harness.close()

    # 5e 恢复窗口耗尽 → 自动恢复超时（把上限调大、退避调小，逼出超时分支）
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(
            binary,
            services,
            extra_args=("--ready-timeout", "0.5", "--max-attempts", "4", "--backoff", "2.0"),
        )
        try:
            harness.cmd("open front")
            services.gcontroll.go2rtc = None
            services.go2rtc.drop_producer()
            out = harness.cmd("wait_state front error 12.0", timeout=15.0)
            check.ok("恢复窗口耗尽 → 自动恢复超时", "timed out" in " ".join(out), out)
        finally:
            harness.close()


    # 5f go2rtc 不可达（但开关可用）→ 不能拿假地址，判 no_data
    with MockRobotServices(start_delay=0.05) as services:
        services.go2rtc.set_offline(True)
        harness = Harness(binary, services)
        try:
            out = harness.cmd("open front", timeout=15.0)
            check.ok("go2rtc 不可达 → no_data（不返回地址）", any("no_data" in l for l in out), out)
        finally:
            harness.close()

    # 5g 断流 + 开关不可达 → do_action 直接判 port_unreachable
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            harness.cmd("open front")
            services.gcontroll.set_unreachable()
            services.go2rtc.drop_producer() # 外部关流（此时开关已挂）
            out = harness.cmd("wait_state front error 8.0", timeout=12.0)
            text = " ".join(out)
            check.ok("断流 + 开关不可达 → error", "state-ok" in text, out)
            check.ok("错误文案指向网络（同一网络）", "same network" in text, out)
        finally:
            harness.close()

    # 5h 推流卡住 + 开关不可达 → try_restart 直接判 port_unreachable
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            harness.cmd("open front")
            services.gcontroll.set_unreachable()
            services.go2rtc.freeze() # 卡住（此时开关已挂）
            out = harness.cmd("wait_state front error 8.0", timeout=12.0)
            text = " ".join(out)
            check.ok("卡住 + 开关不可达 → error", "state-ok" in text, out)
            check.ok("错误文案指向网络（同一网络）", "same network" in text, out)
        finally:
            harness.close()

    # 5i 动作做完之后开关掉线 → 等证据窗口结束时判 port_unreachable
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            harness.cmd("open front")
            services.gcontroll.go2rtc = None # L1 续流不会真的把流拉回来
            services.gcontroll.reset_calls()
            services.go2rtc.drop_producer()
            # 先等到「续流动作已经发出」，再把开关弄挂：这样才会走「动作后掉线」分支
            check.ok(
                "续流动作已发出",
                services.gcontroll.wait_for_start(1, 5.0),
                services.gcontroll.calls,
            )
            services.gcontroll.set_unreachable()
            out = harness.cmd("wait_state front error 10.0", timeout=15.0)
            text = " ".join(out)
            check.ok("动作后开关掉线 → error", "state-ok" in text, out)
            check.ok("错误文案指向网络（同一网络）", "same network" in text, out)
        finally:
            harness.close()

    # 5j 已经 error 之后再次 open（引用计数不为 0）→ 失败也要把记账回滚
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            harness.cmd("open front")
            services.gcontroll.go2rtc = None
            services.go2rtc.drop_producer()
            out = harness.cmd("wait_state front error 12.0", timeout=15.0)
            check.ok("恢复失败后进入 error", "state-ok" in " ".join(out), out)
            out = harness.cmd("open front", timeout=15.0)
            check.ok("error 后再次 open 会明确报错", any(l.startswith("# open-error") for l in out), out)
        finally:
            harness.close()


    # 5k L2 冷却期：两次重启之间必须等冷却（Cooling 分支），不能立刻再重启
    with MockRobotServices(start_delay=0.05) as services:
        services.go2rtc.stuck = True
        harness = Harness(
            binary,
            services,
            extra_args=("--prepare-stall", "0.05", "--restart-cooldown", "2.0"),
        )
        try:
            out = harness.cmd("open front", timeout=20.0)
            check.ok("冷却期内不会无限重启（最终超时收场）", any(l.startswith("# open-error") for l in out), out)
            check.ok(
                "冷却期内只重启了一次",
                services.gcontroll.stop_calls == 1,
                services.gcontroll.calls,
            )
        finally:
            harness.close()

    # 5l 「producer 在、字节数非零但不再增长」的外部流 → **不可采用**。
    #     这正是 stop_stream() 之后残留（或卡住）的流的样子：字节数是历史值，
    #     采用它等于把调用方送到一个 404 的地址上。接管之后仍然救不回来，
    #     所以要明确失败，而不是假成功。
    with MockRobotServices(start_delay=0.05) as services:
        services.go2rtc.start_pushing()
        time.sleep(0.12)  # 先攒出一点历史字节数（非零，但不是「在流」的证据）
        services.go2rtc.freeze()
        services.go2rtc.stuck = True  # 接管后也不会有新数据（重启也救不回来）
        harness = Harness(binary, services)
        try:
            out = harness.cmd("open front", timeout=20.0)
            check.ok(
                "在推但不增长的外部流不被采用（不返回地址）",
                not any(l.startswith("# uri ") for l in out),
                out,
            )
            check.ok("改为自己下发 start 接管", services.gcontroll.start_calls >= 1, services.gcontroll.calls)
            check.ok("始终无新数据 → 明确失败", any(l.startswith("# open-error") for l in out), out)
            check.ok(
                "失败原因指向数据（no_data / stall）",
                any(word in " ".join(out) for word in ("no_data", "stall")),
                out,
            )
        finally:
            harness.close()


# =====================================================================
# 场景 6：生命周期（shutdown / 在回调里关闭）
# =====================================================================
def scenario_lifecycle(check: Checker, binary: str) -> None:
    print("== 场景 6：生命周期（shutdown / 回调内关闭）==")
    with MockRobotServices(start_delay=0.05) as services:
        harness = Harness(binary, services)
        try:
            # 6a 在断流回调（跑在监督线程上）里关闭：不能死锁
            harness.cmd("open front")
            harness.cmd("close_on_lost front")
            services.go2rtc.drop_producer()
            check.ok(
                "断流回调里 close 生效",
                wait_for(lambda: "stopped" in harness.cmd("state front", timeout=3.0)[0], 6.0),
                harness.cmd("state front")[0],
            )
            # 6b 再次开流：监督线程需要被重新拉起
            out = harness.cmd("open front", timeout=15.0)
            check.ok("关闭后能重新开流", any(l.startswith("# uri ") for l in out), out)
            harness.cmd("close_all")

            # 6c shutdown 之后 open 必须被拒绝，且 close/close_all 仍幂等
            harness.cmd("shutdown")
            out = harness.cmd("open front", timeout=10.0)
            check.ok(
                "shutdown 后 open 被拒绝",
                any(l.startswith("# open-error") and "shut down" in l for l in out),
                out,
            )
            harness.cmd("close front")
            harness.cmd("close_all")
            check.ok("shutdown 后 close/close_all 幂等", True)
        finally:
            harness.close()


# =====================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="C++ robot.video 离线自检")
    parser.add_argument("--binary", default="/tmp/video_mock_check", help="被测程序路径")
    parser.add_argument("--only", default="", help="只跑指定场景（调试用）")
    args = parser.parse_args()

    if not os.path.exists(args.binary):
        print(f"找不到被测程序：{args.binary}", file=sys.stderr)
        return 2

    check = Checker()
    started = time.monotonic()
    scenarios = {
        "open": scenario_open_and_adopt,
        "recovery": scenario_recovery,
        "close": scenario_close_decision,
        "internals": scenario_internals,
        "failures": scenario_failure_paths,
        "lifecycle": scenario_lifecycle,
    }
    if args.only:
        wanted = [name.strip() for name in args.only.split(",") if name.strip()]
        unknown = [name for name in wanted if name not in scenarios]
        if unknown:
            print(f"未知场景：{unknown}（可用：{list(scenarios)}）", file=sys.stderr)
            return 2
        for name in wanted:
            scenarios[name](check, args.binary)
    else:
        for name in ("open", "recovery", "close", "internals", "failures", "lifecycle"):
            scenarios[name](check, args.binary)

    elapsed = time.monotonic() - started
    print()
    if check.failures:
        print(f"❌ C++ 离线自检失败：{len(check.failures)} 项")
        for item in check.failures:
            print(f"  - {item}")
        return 1
    if PROTOCOL_ERRORS:
        print(f"❌ 被测程序命令协议异常（断言可能假通过）：{len(PROTOCOL_ERRORS)} 项")
        for item in PROTOCOL_ERRORS:
            print(f"  - {item}")
        return 1
    print(f"✅ C++ 离线自检通过：{check.passed} 项检查（{elapsed:.1f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
