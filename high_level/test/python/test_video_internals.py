"""`robot.video` 的**内部与边界**测试（补齐行/分支覆盖）。

与 `test_video_stream.py` 的分工：

* `test_video_stream.py` —— 用户视角的端到端行为（用真实 HTTP mock 服务）；
* 本文件 —— ① 公共类型的琐碎成员；② 探针 / 开关的异常分支；
  ③ Manager 的边界（生命周期、幂等、参数校验）；
  ④ **状态机白盒**：对 `StreamArbiter` 直接下 tick 并注入可控的探针 / 开关，
      把「准备阶段超时」「恢复超时」「开关不可达」等时序分支跑成确定性的。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace

import pytest

from dobot_quad.video import (
    CameraId,
    CameraStreamInfo,
    LossReason,
    ObserveConfig,
    RecoveredBy,
    RecoveryPolicy,
    StatusProbe,
    StreamArbiter,
    StreamEvent,
    StreamEventKind,
    StreamOwner,
    StreamState,
    VideoError,
    VideoStreamManager,
)
from dobot_quad.video.arbiter import RestartOutcome
from dobot_quad.video.controller import StreamingController
from dobot_quad.video.probe import Consumer, StreamStatus
from dobot_quad.video.types import CAMERA_SPECS, VideoConnectionError
from dobot_quad.video import types as vtypes

from mock_go2rtc import NORMAL, MockRobotServices
from test_video_stream import (
    FAST_OBSERVE,
    FAST_RECOVERY,
    RTSP_PORT,
    make_manager,
    services,
    wait_for,
) # noqa: F401 - services 是夹具，必须导入到本模块命名空间

FRONT = CameraId.FRONT_RGB
URI = f"rtsp://127.0.0.1:{RTSP_PORT}/camera1"


# =====================================================================
# 测试替身：可控探针 / 开关（不联网，可精确驱动分支）
# =====================================================================
def make_status(
    *,
    producers: int = 0,
    bytes_recv: int = 0,
    consumers: int = 0,
    available: bool = True,
    fetched_at: float = 0.0,
    camera: CameraId = FRONT,
) -> StreamStatus:
    return StreamStatus(
        camera=camera,
        name=CAMERA_SPECS[camera].rtsp_name,
        producers=tuple({"bytes_recv": bytes_recv} for _ in range(producers)),
        consumers=tuple(Consumer(remote_addr=f"10.0.0.{i}:1") for i in range(consumers)),
        bytes_recv=bytes_recv,
        available=available,
        fetched_at=fetched_at,
    )


class FakeProbe:
    """按需返回指定快照的探针（`StreamArbiter` 只用到 `status()`）。"""

    def __init__(self, status: StreamStatus) -> None:
        self.current = status
        self.force_calls = 0

    def set(self, status: StreamStatus) -> None:
        self.current = status

    def status(self, camera: CameraId, force: bool = False) -> StreamStatus:
        if force:
            self.force_calls += 1
        return self.current


class FakeController:
    """鸭子类型的推流开关（不联网）。"""

    def __init__(self, reachable: bool = True) -> None:
        self.reachable_result = reachable
        self.calls: list = []
        self.start_error: Exception | None = None
        self.stop_error: Exception | None = None

    def start(self) -> None:
        self.calls.append("start")
        if self.start_error is not None:
            raise self.start_error

    def stop(self) -> None:
        self.calls.append("stop")
        if self.stop_error is not None:
            raise self.stop_error

    def reachable(self, timeout: float | None = None) -> bool:
        return self.reachable_result


class Ticker:
    """模拟 Manager 的监督线程：周期调用 ``arbiter.tick()``。

    白盒测试直接构造 arbiter 时没有监督线程，需要它才能跑出「随时间推进」的分支。
    """

    def __init__(self, arbiter: StreamArbiter, interval: float = 0.005) -> None:
        self._arbiter = arbiter
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Ticker":
        self._thread = threading.Thread(target=self._run, name="test-video-ticker", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._arbiter.tick()
            self._stop.wait(self._interval)


def make_arbiter(
    probe=None,
    controller=None,
    *,
    on_event=None,
    observe: ObserveConfig | None = None,
    policy: RecoveryPolicy | None = None,
) -> StreamArbiter:
    return StreamArbiter(
        FRONT,
        URI,
        probe or FakeProbe(make_status()),
        controller or FakeController(),
        on_event=on_event,
        observe=observe or FAST_OBSERVE,
        policy=policy or FAST_RECOVERY,
    )


# =====================================================================
# 1. 公共类型
# =====================================================================
def test_camera_id_helpers():
    assert FRONT.spec is CAMERA_SPECS[FRONT]
    assert FRONT.description == CAMERA_SPECS[FRONT].description
    assert str(FRONT) == "FRONT_RGB"
    assert FRONT.rtsp_name == "camera1" and FRONT.dds_index == 0


def test_enum_str_and_event_names():
    assert str(StreamState.READY) == "ready"
    assert str(StreamOwner.EXTERNAL) == "external"
    assert str(LossReason.STALL) == "stall"
    assert str(RecoveredBy.L2_RESTART) == "L2_restart"
    assert [k.value for k in StreamEventKind] == [
        "StreamReady",
        "StreamLost",
        "StreamReconnected",
        "StreamClosed",
        "StreamError",
    ]


def test_clock_helpers_are_monotonic():
    assert vtypes.monotonic_ns() > 0
    assert vtypes.monotonic_ns() >= vtypes.monotonic_ns() - 10**9


def test_camera_stream_info_members():
    info = CameraStreamInfo(camera=FRONT)
    assert info.available is False, "未 open() 时地址不可用"
    assert info.is_streaming is False
    assert info.to_dict()["camera"] == "FRONT_RGB"
    assert info.to_dict()["state"] == "stopped"
    assert "FRONT_RGB" in str(info)

    ready = CameraStreamInfo(
        camera=FRONT,
        state=StreamState.READY,
        owner=StreamOwner.SDK,
        uri=URI,
        bitrate_kbps=2800.0,
        message="就绪",
    )
    assert ready.available is True and ready.is_streaming is True
    text = str(ready)
    assert "ready" in text and "sdk" in text and URI in text and "2800" in text


def test_stream_event_members():
    event = StreamEvent(
        kind=StreamEventKind.LOST,
        camera=FRONT,
        old_state=StreamState.READY,
        new_state=StreamState.RECOVERING,
        reason=LossReason.STALL,
        uri=URI,
        message="卡住",
    )
    assert event.name == "StreamLost"
    assert event.to_dict()["reason"] == "stall"
    assert "ready -> recovering" in str(event) and "卡住" in str(event)

    recovered = replace(event, kind=StreamEventKind.RECONNECTED, recovered_by=RecoveredBy.L2_RESTART, message="")
    assert "recovered_by=L2_restart" in str(recovered)


def test_video_error_carries_reason_and_camera():
    error = VideoError("x", reason=LossReason.NO_DATA, camera=FRONT)
    assert error.reason is LossReason.NO_DATA and error.camera is FRONT
    assert isinstance(VideoConnectionError("y"), VideoError)


# =====================================================================
# 2. go2rtc 探针的异常分支
# =====================================================================
def make_probe(services) -> StatusProbe:
    return StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)


def test_probe_invalid_json_body(services):
    services.go2rtc.set_body_script(["{ not json"])
    status = make_probe(services).status(FRONT, force=True)
    assert status.available is False and "invalid json" in status.error


def test_probe_non_object_body(services):
    services.go2rtc.set_body_script(["[1, 2, 3]"])
    status = make_probe(services).status(FRONT, force=True)
    assert status.available is False and status.error == "unexpected body"


def test_probe_stream_entry_not_object(services):
    services.go2rtc.set_body_script(['{"camera1": 42}'])
    status = make_probe(services).status(FRONT, force=True)
    assert status.available is False and status.error == "invalid stream entry"


def test_probe_non_numeric_bytes_recv_is_ignored(services):
    body = json.dumps({"camera1": {"producers": [{"bytes_recv": "oops"}], "consumers": []}})
    services.go2rtc.set_body_script([body])
    status = make_probe(services).status(FRONT, force=True)
    assert status.available is True and status.has_producer is True
    assert status.bytes_recv == 0, "非数字 bytes_recv 必须被跳过而不是抛异常"


def test_probe_falls_back_to_last_good_snapshot_on_blip(services):
    """抖动容忍：一次请求失败时，短窗口内沿用上一次成功结果（不误判「流没了」）。"""
    probe = make_probe(services)
    services.go2rtc.start_pushing("camera1")
    time.sleep(0.05)
    assert probe.status(FRONT, force=True).has_producer is True

    services.go2rtc.set_offline(True)
    status = probe.status(FRONT, force=False)
    assert status.available is True and status.has_producer is True, "抖动不应立刻变成「没有流」"
    assert probe.status(FRONT, force=True).available is False, "强制刷新失败时不允许用旧数据兜底"


def test_probe_invalidate_clears_cache(services):
    probe = make_probe(services)
    services.go2rtc.start_pushing("camera1")
    probe.status(FRONT, force=True)
    before = services.go2rtc.request_count
    assert probe.status(FRONT, force=False).available is True
    assert services.go2rtc.request_count == before, "TTL 内应命中缓存"

    probe.invalidate()
    probe.status(FRONT, force=False)
    assert services.go2rtc.request_count == before + 1, "invalidate() 之后必须重新请求"


def test_probe_fetch_override_is_used(services):
    probe = make_probe(services)
    seen = []

    def override(url: str, timeout: float):
        seen.append((url, timeout))
        return json.dumps({"camera1": {"producers": [{"bytes_recv": 7}], "consumers": []}}), ""

    probe._fetch_override = override # noqa: SLF001 - 这是本类公开的测试注入点
    status = probe.status(FRONT, force=True)
    assert seen and seen[0][0].endswith("/api/streams")
    assert status.available is True and status.bytes_recv == 7


def test_probe_does_not_use_too_old_cached_snapshot(services):
    """超过抖动容忍窗口的旧快照不能再拿来充数。"""
    probe = make_probe(services)
    services.go2rtc.start_pushing("camera1")
    time.sleep(0.05)
    assert probe.status(FRONT, force=True).has_producer is True

    probe._cache[FRONT].fetched_at -= 10.0 # noqa: SLF001 - 把缓存时间拨到窗口之外
    services.go2rtc.set_offline(True)
    assert probe.status(FRONT, force=False).available is False, "过期缓存不能用来交差"


def test_all_watching_inconsistent_samples_take_safe_side(services):
    """两次采样结果不一致时按安全侧（视为有人在看）。"""
    probe = make_probe(services)

    def body(consumers_for_camera1: int) -> str:
        return json.dumps(
            {
                "camera1": {
                    "producers": [],
                    "consumers": [{"remote_addr": f"10.0.0.{i}:1"} for i in range(consumers_for_camera1)],
                },
                "camera2": {"producers": [], "consumers": []},
            }
        )

    # 一次 all_watching(2) 会发 4 次请求（两路 × 两次采样）：先有人看、再没人看
    services.go2rtc.set_body_script([body(1), body(1), body(0), body(0)])
    try:
        assert probe.all_watching(samples=2, interval=0.01) is True, "采样不一致时必须偏向安全侧"
    finally:
        services.go2rtc.set_body_script([NORMAL])


# =====================================================================
# 3. 推流开关的异常分支
# =====================================================================
class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


def test_controller_http_error_is_reported(services):
    services.gcontroll.fail_next_start = 1
    controller = StreamingController("127.0.0.1", services.gcontroll.port, timeout=0.5)
    with pytest.raises(VideoConnectionError) as exc:
        controller.start()
    assert "HTTP 500" in str(exc.value)


def test_controller_timeout_is_reported(services, monkeypatch):
    def boom(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    controller = StreamingController("127.0.0.1", services.gcontroll.port, timeout=0.1)
    with pytest.raises(VideoError) as exc:
        controller.stop()
    assert "Timed out" in str(exc.value)


def test_controller_unreachable_and_oserror(services, monkeypatch):
    refused = StreamingController("127.0.0.1", services.gcontroll.port + 1, timeout=0.2)
    assert refused.reachable() is False
    with pytest.raises(VideoConnectionError):
        refused.start()

    def oserror(*_args, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr("urllib.request.urlopen", oserror)
    with pytest.raises(VideoConnectionError) as exc:
        refused.stop()
    assert "boom" in str(exc.value)


def test_controller_ignores_non_json_body(services, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _FakeResponse(b"<html>ok</html>"))
    controller = StreamingController("127.0.0.1", services.gcontroll.port, timeout=0.5)
    controller.start() # 不抛异常即可（只有 2xx + 合法 JSON 才解析）


# =====================================================================
# 4. Manager 边界
# =====================================================================
def test_manager_properties_and_atexit_registration(services):
    import atexit

    manager = VideoStreamManager(
        "127.0.0.1",
        endpoints=services_endpoints(services),
        observe=FAST_OBSERVE,
        policy=FAST_RECOVERY,
    )
    try:
        assert manager.host == "127.0.0.1"
        assert manager.endpoints.rtsp_port == RTSP_PORT
        assert manager.uri(FRONT) == URI
        assert manager.list_cameras() == [FRONT, CameraId.REAR_RGB]
        manager.open(FRONT) # 让监督线程跑起来，以便覆盖「退出时收线程」的路径
    finally:
        manager._atexit_cleanup() # noqa: SLF001 - atexit 回调本体
        atexit.unregister(manager._atexit_cleanup) # noqa: SLF001
    assert "dobot-video-supervisor" not in {t.name for t in threading.enumerate()}


def test_manager_rejects_invalid_camera_ids(services):
    """非法相机参数：抛异常、不发请求、不落进错误状态。

    对应自测用例「非法相机参数」：`open("front")` 传的是字符串而不是 `CameraId`，
    以及越界的整数（模拟 C++ 侧 `static_cast<CameraId>(7)`）。
    """
    manager = VideoStreamManager(
        "127.0.0.1",
        endpoints=services_endpoints(services),
        observe=FAST_OBSERVE,
        policy=FAST_RECOVERY,
    )
    try:
        requests_before = services.go2rtc.request_count
        for call in (
            manager.open,
            manager.close,
            manager.stop_stream,
            manager.is_streaming,
            manager.get_stream_info,
            manager.uri,
        ):
            with pytest.raises(ValueError, match="is not a valid CameraId"):
                call("front")        # 字符串而不是 CameraId
            with pytest.raises(ValueError, match="is not a valid CameraId"):
                call(7)              # 越界的整数
        assert services.go2rtc.request_count == requests_before, "非法参数不该发任何请求"

        # 不落进错误状态：正常相机照常可用（开流、ready、再关掉）
        assert manager.open(FRONT) == URI
        assert manager.is_streaming(FRONT)
        manager.close(FRONT)
    finally:
        manager.shutdown()


def services_endpoints(services):
    from dobot_quad.video import Endpoints
    return Endpoints(
        http_port=services.gcontroll.port, go2rtc_port=services.go2rtc.port, rtsp_port=RTSP_PORT
    )


def test_open_after_shutdown_is_rejected(services):
    manager = make_manager(services)
    manager.shutdown()
    with pytest.raises(VideoError) as exc:
        manager.open(FRONT)
    assert "shut down" in str(exc.value)


def test_on_state_change_validates_callback(services):
    manager = make_manager(services)
    try:
        with pytest.raises(TypeError):
            manager.on_state_change(None) # type: ignore[arg-type]
        unsubscribe = manager.on_state_change(lambda _e: None)
        unsubscribe()
        unsubscribe() # 再次取消订阅必须是幂等的
    finally:
        manager.shutdown()


def test_abort_open_skips_entry_already_removed(services):
    """`_abort_open` 遇到已经被其它路径清掉的条目时不能报错（防御分支）。"""
    manager = make_manager(services)
    try:
        manager.open(FRONT)
        entry = manager._entries[FRONT] # noqa: SLF001
        manager._entries.clear() # noqa: SLF001 - 模拟条目已被清掉
        entry.refcount = 1
        manager._abort_open(FRONT, entry) # noqa: SLF001
        assert FRONT in manager._history # noqa: SLF001
    finally:
        manager.shutdown()


def test_close_from_state_callback_is_safe(services):
    """在状态回调里再次 close（回调跑在监督线程上）：不能死锁、不能崩。"""
    manager = make_manager(services)
    reentered: list = []

    def on_event(event):
        if event.kind is StreamEventKind.CLOSED and not reentered:
            reentered.append(event)
            manager.close(FRONT) # 重入：此时外层 close() 还没走完

    manager.on_state_change(on_event)
    try:
        manager.open(FRONT)
        manager.close(FRONT)
        assert reentered, "回调应当被调用"
        assert manager.get_stream_info(FRONT).state is StreamState.STOPPED
    finally:
        manager.shutdown()


def test_close_from_lost_callback_runs_on_supervisor_thread(services):
    """用户「看到断流就决定不看了」：回调跑在监督线程上，此时 close() 不能自己 join 自己。"""
    manager = make_manager(services)
    closed_in_callback: list = []

    def on_event(event):
        if event.kind is StreamEventKind.LOST and not closed_in_callback:
            manager.close(FRONT) # 就在监督线程里收摊
            closed_in_callback.append(event)

    manager.on_state_change(on_event)
    try:
        manager.open(FRONT)
        services.go2rtc.drop_producer() # 触发断流（在监督线程上回调）
        assert wait_for(lambda: bool(closed_in_callback), 3.0)
        assert wait_for(lambda: "dobot-video-supervisor" not in {t.name for t in threading.enumerate()}, 3.0)
        assert manager.get_stream_info(FRONT).state is StreamState.STOPPED
    finally:
        manager.shutdown()


def test_manager_context_manager_and_shutdown_join(services):
    with make_manager(services) as manager:
        manager.open(FRONT)
        assert "dobot-video-supervisor" in {t.name for t in threading.enumerate()}
    assert "dobot-video-supervisor" not in {t.name for t in threading.enumerate()}, (
        "shutdown() 必须把监督线程收掉"
    )


def test_abort_open_keeps_entry_when_other_user_remains(services):
    """`_abort_open` 只在引用计数归零时才清理（白盒：验证记账逻辑）。"""
    manager = make_manager(services)
    try:
        manager.open(FRONT)
        entry = manager._entries[FRONT] # noqa: SLF001
        entry.refcount = 2
        manager._abort_open(FRONT, entry) # noqa: SLF001
        assert entry.refcount == 1
        assert manager._entries.get(FRONT) is entry, "还有别的使用者时不能把条目删掉"
    finally:
        manager.shutdown()


# =====================================================================
# 5. StreamArbiter 单元分支（无网络）
# =====================================================================
def test_arbiter_properties():
    arbiter = make_arbiter()
    assert arbiter.camera is FRONT and arbiter.uri == URI
    assert arbiter.state is StreamState.STOPPED
    assert arbiter.sdk_started is False
    assert arbiter.needs_fast_sample is False

    arbiter.begin()
    assert arbiter.state is StreamState.PREPARING
    assert arbiter.needs_fast_sample is True
    assert arbiter.info().uri == URI and arbiter.info().state is StreamState.PREPARING


def test_wait_ready_after_release_is_rejected():
    arbiter = make_arbiter()
    arbiter.begin()
    arbiter.release(message="用户关闭")
    with pytest.raises(VideoError) as exc:
        arbiter.wait_ready(0.2)
    assert exc.value.reason is LossReason.CLOSED


def test_issue_start_is_idempotent_within_prepare():
    controller = FakeController()
    arbiter = make_arbiter(controller=controller)
    arbiter.begin()
    assert arbiter._issue_start(0.0) is True # noqa: SLF001
    assert arbiter._issue_start(0.0) is True # noqa: SLF001 - 第二次应直接复用
    assert controller.calls == ["start"], "PREPARING 阶段只允许下发一次 start"
    assert arbiter.sdk_started is True


def test_sample_dedup_and_bitrate_edge():
    """`_sample`：同一份快照不重复计数；两次采样时间戳相同不计算码率。"""
    arbiter = make_arbiter()
    cam = FRONT

    assert arbiter._sample(make_status(producers=1, bytes_recv=100, fetched_at=1.0), 5.0) is False # noqa: SLF001
    # 增长 + 与上次采样同一时刻（now == prev_at）→ 不算码率，但算增长
    assert arbiter._sample(make_status(producers=1, bytes_recv=200, fetched_at=2.0), 5.0) is True # noqa: SLF001
    assert arbiter.info().bitrate_kbps is None, "时间戳相同不能算出码率"
    # 同一份快照（fetched_at 不变）→ 直接复用上次结论
    assert arbiter._sample(make_status(producers=1, bytes_recv=999, fetched_at=2.0), 5.1) is True # noqa: SLF001
    # 采样时间前进 → 能算出码率
    assert arbiter._sample(make_status(producers=1, bytes_recv=1300, fetched_at=3.0), 5.6) is True # noqa: SLF001
    assert (arbiter.info().bitrate_kbps or 0) > 0
    # 探针不可用时不更新差分状态
    assert arbiter._sample(make_status(available=False, fetched_at=4.0), 5.7) is False # noqa: SLF001
    assert cam is FRONT


def test_fail_is_idempotent_and_messages():
    events = []
    arbiter = make_arbiter(on_event=events.append)
    arbiter.begin()
    arbiter._fail(LossReason.NO_DATA, "第一次失败") # noqa: SLF001
    arbiter._fail(LossReason.STALL, "第二次失败") # noqa: SLF001 - 已经是 ERROR → 直接返回
    assert arbiter.state is StreamState.ERROR
    assert arbiter.info().reason is LossReason.NO_DATA, "第二次 _fail 不应改写已有原因"
    assert [e.name for e in events] == ["StreamError"]

    assert "same network" in arbiter._fail_message(LossReason.PORT_UNREACHABLE) # noqa: SLF001
    assert "not start streaming in time" in arbiter._fail_message(LossReason.STALL) # noqa: SLF001
    assert "not start streaming in time" in arbiter._fail_message(LossReason.NO_DATA) # noqa: SLF001


def test_enter_recovering_only_from_ready():
    events = []
    arbiter = make_arbiter(on_event=events.append)
    arbiter._enter_recovering(LossReason.STALL, "不该生效") # noqa: SLF001
    assert arbiter.state is StreamState.STOPPED and events == []

    arbiter.begin()
    arbiter._enter_recovering(LossReason.EXTERNAL, "流没了") # noqa: SLF001 - PREPARING 也不允许
    assert arbiter.state is StreamState.PREPARING

    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001
    arbiter._enter_recovering(LossReason.EXTERNAL, "流没了") # noqa: SLF001
    assert arbiter.state is StreamState.RECOVERING
    assert [e.name for e in events] == ["StreamReady", "StreamLost"]


def test_emit_without_callback_is_safe():
    arbiter = make_arbiter(on_event=None)
    arbiter.begin()
    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001 - 没有回调也不能抛
    assert arbiter.state is StreamState.READY


def test_do_action_with_unreachable_switch():
    controller = FakeController(reachable=False)
    arbiter = make_arbiter(controller=controller)
    arbiter.begin()
    arbiter._become_ready(StreamOwner.EXTERNAL) # noqa: SLF001
    arbiter._enter_recovering(LossReason.EXTERNAL, "流被外部关闭") # noqa: SLF001
    arbiter._do_action(RecoveredBy.L1_RESUME, 0.0, LossReason.EXTERNAL) # noqa: SLF001
    assert arbiter.state is StreamState.ERROR
    assert arbiter.info().reason is LossReason.PORT_UNREACHABLE
    assert controller.calls == [], "开关都连不上时不能发任何请求"


def test_try_restart_with_unreachable_switch():
    controller = FakeController(reachable=False)
    arbiter = make_arbiter(controller=controller)
    arbiter.begin()
    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001
    arbiter._enter_recovering(LossReason.STALL, "卡住") # noqa: SLF001
    assert arbiter._try_restart(time.monotonic(), LossReason.STALL) is RestartOutcome.UNREACHABLE # noqa: SLF001
    assert arbiter.state is StreamState.ERROR
    assert arbiter.info().reason is LossReason.PORT_UNREACHABLE


def test_try_restart_outcomes_are_distinguishable():
    """「执行失败」「冷却中」「触顶」必须能区分（否则文案会误导用户）。"""
    controller = FakeController()
    controller.stop_error = OSError("网线掉了")
    arbiter = make_arbiter(controller=controller)
    arbiter.begin()
    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001
    arbiter._enter_recovering(LossReason.STALL, "卡住") # noqa: SLF001
    now = time.monotonic()

    assert arbiter._try_restart(now, LossReason.STALL) is RestartOutcome.FAILED # noqa: SLF001
    assert arbiter.state is StreamState.RECOVERING, "执行失败不能直接判死，应退避后重试"
    assert controller.calls == ["stop"]

    with arbiter._cv: # noqa: SLF001
        arbiter._restart_times = [now - 0.01] # 刚重启过 → 在冷却期
    assert arbiter._try_restart(now, LossReason.STALL) is RestartOutcome.COOLING # noqa: SLF001

    with arbiter._cv: # noqa: SLF001
        arbiter._restart_times = [now - 0.01, now - 0.02] # 窗口内已满额
    assert arbiter._try_restart(now, LossReason.STALL) is RestartOutcome.LIMIT # noqa: SLF001
    assert arbiter.state is StreamState.RECOVERING, "触顶由调用方决定是否放弃"

    # 经 tick：FAILED 不该被误报成「已达上限」
    arbiter.tick()
    assert arbiter.state is StreamState.RECOVERING


# =====================================================================
# 6. 状态机白盒：直接 tick，把时序分支跑成确定性
# =====================================================================
def test_tick_prepare_timeout_no_data():
    """producers 在但 bytes_recv 一直是 0 → 到点判 no_data（不留假地址）。"""
    probe = FakeProbe(make_status(producers=1, bytes_recv=0, fetched_at=1.0))
    arbiter = make_arbiter(probe=probe)
    arbiter.begin()
    arbiter._deadline = time.monotonic() - 1.0 # noqa: SLF001 - 把等待窗口拨到过去
    arbiter.tick()
    assert arbiter.state is StreamState.ERROR
    assert arbiter.info().reason is LossReason.NO_DATA


def test_tick_prepare_timeout_port_unreachable():
    """开关通道不可达时，超时的原因必须是 port_unreachable（提示检查网络）。"""
    probe = FakeProbe(make_status(available=False, fetched_at=1.0))
    controller = FakeController(reachable=False)
    arbiter = make_arbiter(probe=probe, controller=controller)
    arbiter.begin()
    with arbiter._cv: # noqa: SLF001 - 模拟「start 已经发过了」
        arbiter._sdk_started = True # noqa: SLF001
        arbiter._start_issued = True # noqa: SLF001
        arbiter._deadline = time.monotonic() - 1.0 # noqa: SLF001
    arbiter.tick()
    assert arbiter.state is StreamState.ERROR
    assert arbiter.info().reason is LossReason.PORT_UNREACHABLE


def test_tick_prepare_timeout_with_reachable_switch():
    """开关能连但流起不来 → 原因必须是 no_data（而不是误导成「网络问题」）。"""
    probe = FakeProbe(make_status(available=False, fetched_at=1.0))
    controller = FakeController(reachable=True)
    arbiter = make_arbiter(probe=probe, controller=controller)
    arbiter.begin()
    with arbiter._cv: # noqa: SLF001
        arbiter._sdk_started = True # noqa: SLF001
        arbiter._start_issued = True # noqa: SLF001
        arbiter._deadline = time.monotonic() - 1.0 # noqa: SLF001
    arbiter.tick()
    assert arbiter.state is StreamState.ERROR
    assert arbiter.info().reason is LossReason.NO_DATA


def test_tick_recover_acting_failure_switch_lost():
    """恢复动作做完后开关又掉了 → 必须报 port_unreachable，而不是默默重试。"""
    probe = FakeProbe(make_status(producers=1, bytes_recv=100, fetched_at=1.0))
    controller = FakeController()
    arbiter = make_arbiter(probe=probe, controller=controller)
    arbiter.begin()
    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001
    arbiter._enter_recovering(LossReason.EXTERNAL, "流没了") # noqa: SLF001
    probe.set(make_status(producers=0, bytes_recv=0, fetched_at=2.0))
    arbiter.tick() # 非 acting → _do_action(L1) → start()
    assert controller.calls == ["start"]

    controller.reachable_result = False
    with arbiter._cv: # noqa: SLF001
        arbiter._act_deadline = time.monotonic() - 1.0 # noqa: SLF001 - 等证据窗口已过
    arbiter.tick()
    assert arbiter.state is StreamState.ERROR
    assert arbiter.info().reason is LossReason.PORT_UNREACHABLE


def test_tick_prepare_stall_triggers_l2_restart(services):
    """PREPARING 阶段就卡住（producers 在、bytes 不动）→ 自动 stop+start 后成功。"""
    services.go2rtc.stuck = True # start 后 producer 出现但立即冻结
    observe = replace(FAST_OBSERVE, prepare_stall_seconds=0.15)
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=observe)
    controller = StreamingController("127.0.0.1", services.gcontroll.port, timeout=0.5)
    events: list = []
    arbiter = StreamArbiter(
        FRONT, URI, probe, controller, on_event=events.append, observe=observe, policy=FAST_RECOVERY
    )

    # 首次重启动作发生后立刻让推流恢复健康
    def heal() -> None:
        if wait_for(lambda: services.gcontroll.stop_calls >= 1, 2.0):
            services.go2rtc.stuck = False

    healer = threading.Thread(target=heal, daemon=True)
    healer.start()
    arbiter.begin()
    try:
        with Ticker(arbiter):
            assert wait_for(lambda: arbiter.state is StreamState.READY, 3.0), arbiter.info()
        assert services.gcontroll.stop_calls == 1 and services.gcontroll.start_calls >= 2
        assert [e.name for e in events] == ["StreamReady"]
    finally:
        arbiter.release()
        healer.join(timeout=2.0)


def test_tick_prepare_stall_gives_up_at_restart_limit(services):
    """PREPARING 阶段的卡住也受 L2 上限约束（不能无限重启）。"""
    services.go2rtc.stuck = True
    observe = replace(FAST_OBSERVE, prepare_stall_seconds=0.1, ready_timeout=3.0)
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=observe)
    controller = StreamingController("127.0.0.1", services.gcontroll.port, timeout=0.5)
    arbiter = StreamArbiter(FRONT, URI, probe, controller, observe=observe, policy=FAST_RECOVERY)
    arbiter.begin()
    try:
        with Ticker(arbiter):
            assert wait_for(lambda: arbiter.state is StreamState.ERROR, 4.0), arbiter.info()
        assert arbiter.info().reason is LossReason.STALL
        assert "sends no picture data" in arbiter.info().message
        assert services.gcontroll.stop_calls <= FAST_RECOVERY.restart_max_per_window
    finally:
        arbiter.release()


def test_tick_recover_gives_up_after_max_attempts(services):
    """恢复动作反复失败 → 退避重试到上限 → ERROR（A8 自愈不风暴）。"""
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    controller = StreamingController("127.0.0.1", services.gcontroll.port, timeout=0.5)
    events: list = []
    arbiter = StreamArbiter(
        FRONT, URI, probe, controller, on_event=events.append, observe=FAST_OBSERVE, policy=FAST_RECOVERY
    )
    arbiter.begin()
    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001
    # 外部关流，但让 start 再不产生 producer（模拟推流模块坏了）
    services.gcontroll.go2rtc = None
    services.go2rtc.drop_producer()
    try:
        with Ticker(arbiter):
            assert wait_for(lambda: arbiter.state is StreamState.ERROR, 5.0), arbiter.info()
        assert arbiter.info().reason is LossReason.EXTERNAL
        assert [e.name for e in events][-1] == "StreamError"
        assert services.gcontroll.start_calls >= FAST_RECOVERY.max_attempts, "每次退避都应重试一次"
    finally:
        arbiter.release()


def test_tick_recover_timeout(services):
    """恢复窗口耗尽（attempt 还没超上限）也要放弃，不能一直挂着。"""
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    controller = StreamingController("127.0.0.1", services.gcontroll.port, timeout=0.5)
    arbiter = StreamArbiter(FRONT, URI, probe, controller, observe=FAST_OBSERVE, policy=FAST_RECOVERY)
    arbiter.begin()
    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001
    services.gcontroll.go2rtc = None
    services.go2rtc.drop_producer()
    ticker = Ticker(arbiter)
    ticker.__enter__()
    try:
        assert wait_for(lambda: arbiter.state is StreamState.RECOVERING, 2.0)
        # 白盒：把「恢复开始时刻」和「下次重试时刻」都拨到过去，逼出超时分支
        with arbiter._cv: # noqa: SLF001
            arbiter._recover_started_at = time.monotonic() - 100.0 # noqa: SLF001
            arbiter._next_attempt_at = 0.0 # noqa: SLF001
            arbiter._acting = False # noqa: SLF001
        assert wait_for(lambda: arbiter.state is StreamState.ERROR, 2.0), arbiter.info()
        assert "timed out" in arbiter.info().message
    finally:
        ticker.__exit__()
        arbiter.release()


def test_tick_recover_switch_failure_is_not_misreported(services):
    """开关不可达/动作失败时，不能把原因错报成「重启次数已达上限」。"""
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    controller = StreamingController("127.0.0.1", services.gcontroll.port, timeout=0.3)
    arbiter = StreamArbiter(FRONT, URI, probe, controller, observe=FAST_OBSERVE, policy=FAST_RECOVERY)
    arbiter.begin()
    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001
    arbiter._enter_recovering(LossReason.STALL, "卡住") # noqa: SLF001
    try:
        services.gcontroll.set_unreachable()
        for _ in range(4):
            arbiter.tick()
            time.sleep(0.03)
        info = arbiter.info()
        assert "used up" not in info.message, "动作执行失败不能被误报成「触顶」"
        assert info.state in (StreamState.RECOVERING, StreamState.ERROR)
    finally:
        arbiter.release()


def test_tick_ready_ignores_unavailable_probe(services):
    """状态看不到时不能误判断流（安全侧）。"""
    probe = FakeProbe(make_status(producers=1, bytes_recv=100, fetched_at=1.0))
    arbiter = make_arbiter(probe=probe)
    arbiter.begin()
    arbiter.tick()   # 第一次采样只建立基线：外部流要看到「字节真的增长」才被采用
    probe.set(make_status(producers=1, bytes_recv=200, fetched_at=2.0))
    arbiter.tick()
    assert arbiter.state is StreamState.READY

    probe.set(make_status(available=False, fetched_at=3.0))
    arbiter.tick()
    assert arbiter.state is StreamState.READY, "看不到 ≠ 断流"


def test_tick_on_stopped_and_error_states_is_noop():
    arbiter = make_arbiter()
    arbiter.tick() # STOPPED
    assert arbiter.state is StreamState.STOPPED
    arbiter.begin()
    arbiter._fail(LossReason.NO_DATA, "失败") # noqa: SLF001
    arbiter.tick() # ERROR
    assert arbiter.state is StreamState.ERROR


def test_mark_force_stopped_is_idempotent():
    events: list = []
    arbiter = make_arbiter(on_event=events.append)
    arbiter.mark_force_stopped() # 从未 open → 不发事件
    assert events == []

    arbiter.begin()
    arbiter._become_ready(StreamOwner.SDK) # noqa: SLF001
    arbiter.mark_force_stopped(message="强停")
    arbiter.mark_force_stopped(message="再停一次")
    assert arbiter.state is StreamState.STOPPED and arbiter.sdk_started is False
    assert [e.name for e in events] == ["StreamReady", "StreamClosed"]
