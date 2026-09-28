"""`robot.video`（控制面）离线测试。

覆盖：

* 地址可用 / 不打断 App / 不误停他人流 / 状态正确
* 断流自愈 / 卡住自愈 / 自愈不风暴
* 零解码依赖 / 资源释放（全局 1 线程）/ 有人看时不停流

对端行为（go2rtc 状态、GControll 全局开关）由 `mock_go2rtc.py` 的真实 HTTP
服务复现；媒体面不在 SDK 内，因此「地址可播放」用真实 ffmpeg 对着 mock RTSP
服务端验证一次（证明交付出去的地址形式是可用的）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time

import pytest

from dobot_quad.video import (
    CameraId,
    CameraStreamInfo,
    Endpoints,
    LossReason,
    ObserveConfig,
    RecoveredBy,
    RecoveryPolicy,
    StatusProbe,
    StreamEventKind,
    StreamOwner,
    StreamState,
    VideoConnectionError,
    VideoError,
    VideoStreamManager,
    VideoTimeoutError,
)

from mock_go2rtc import MockRobotServices


# =====================================================================
# 夹具：让状态机在毫秒级跑完（真实默认值是 0.25s / 2s / 8s）
# =====================================================================
FAST_OBSERVE = ObserveConfig(
    tick=0.02,
    sample_interval=0.1,
    stall_samples=2,
    ready_timeout=1.5,
    probe_timeout=0.5,
    prepare_poll=0.02,
    settle_seconds=0.05,
    prepare_stall_seconds=0.4, # 必须小于 ready_timeout，否则准备阶段只会超时
)
FAST_RECOVERY = RecoveryPolicy(
    backoff=(0.05, 0.1, 0.2),
    max_attempts=3,
    restart_cooldown=0.3,
    restart_max_per_window=2,
    restart_window=5.0,
    act_timeout=0.4,
)

RTSP_PORT = 18554


@pytest.fixture
def services():
    srv = MockRobotServices(start_delay=0.05)
    try:
        yield srv
    finally:
        srv.close()


def make_manager(services: MockRobotServices, **kwargs) -> VideoStreamManager:
    kwargs.setdefault("observe", FAST_OBSERVE)
    kwargs.setdefault("policy", FAST_RECOVERY)
    kwargs.setdefault("register_atexit", False)
    return VideoStreamManager(
        "127.0.0.1",
        endpoints=Endpoints(
            http_port=services.gcontroll.port,
            go2rtc_port=services.go2rtc.port,
            rtsp_port=RTSP_PORT,
        ),
        **kwargs,
    )


def wait_for(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


def thread_names() -> set:
    return {t.name for t in threading.enumerate()}


# =====================================================================
# 1. 类型与命名（编号映射只有一个点）
# =====================================================================
def test_camera_id_maps_two_numbering_schemes():
    assert CameraId.FRONT_RGB.rtsp_name == "camera1"
    assert CameraId.FRONT_RGB.dds_index == 0
    assert CameraId.REAR_RGB.rtsp_name == "camera2"
    assert CameraId.REAR_RGB.dds_index == 1


def test_uri_uses_rtsp_stream_name(services):
    mgr = make_manager(services)
    try:
        assert mgr.uri(CameraId.FRONT_RGB) == f"rtsp://127.0.0.1:{RTSP_PORT}/camera1"
        assert mgr.uri(CameraId.REAR_RGB) == f"rtsp://127.0.0.1:{RTSP_PORT}/camera2"
    finally:
        mgr.shutdown()


# =====================================================================
# 2. 状态探针（go2rtc）
# =====================================================================
def test_probe_reports_producer_and_bytes(services):
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    assert probe.status(CameraId.FRONT_RGB, force=True).has_producer is False

    services.go2rtc.start_pushing("camera1")
    time.sleep(0.05)
    st = probe.status(CameraId.FRONT_RGB, force=True)
    assert st.available and st.has_producer and st.bytes_recv > 0

    time.sleep(0.05)
    st2 = probe.status(CameraId.FRONT_RGB, force=True)
    assert st2.bytes_recv > st.bytes_recv, "bytes_recv 应当单调增长（R2 判据依据）"


def test_probe_missing_stream_is_unavailable_not_nobody_watching(services):
    """响应里没有这一路流 ≠ 没人看。"""
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    services.go2rtc.hide("camera1")
    st = probe.status(CameraId.FRONT_RGB, force=True)
    assert st.available is False
    assert st.others_watching is None, "看不到 ≠ 没人看"


def test_probe_empty_body_is_unavailable(services):
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    services.go2rtc.set_body("")
    st = probe.status(CameraId.FRONT_RGB, force=True)
    assert st.available is False and st.others_watching is None


def test_probe_offline_is_unavailable(services):
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    services.go2rtc.set_offline(True)
    st = probe.status(CameraId.FRONT_RGB, force=True)
    assert st.available is False and st.has_producer is False


def test_probe_counts_consumers(services):
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    services.go2rtc.start_pushing("camera1")
    assert probe.status(CameraId.FRONT_RGB, force=True).consumer_count == 0
    services.go2rtc.add_consumer("camera1", ua="Mozilla/5.0 (uni-app)", addr="10.0.15.40:43776")
    st = probe.status(CameraId.FRONT_RGB, force=True)
    assert st.consumer_count == 1 and st.others_watching is True
    assert st.consumers[0].is_app_like is True


def test_probe_all_watching_semantics(services):
    probe = StatusProbe("127.0.0.1", services.go2rtc.port, timeout=0.5, observe=FAST_OBSERVE)
    services.go2rtc.start_pushing()
    assert probe.all_watching(samples=2, interval=0.01) is False
    services.go2rtc.add_consumer("camera2")
    assert probe.all_watching(samples=2, interval=0.01) is True, "任一相机有人看就必须让路"
    services.go2rtc.clear_consumers()
    services.go2rtc.set_offline(True)
    assert probe.all_watching(samples=2, interval=0.01) is None, "看不到 → 安全侧"


# =====================================================================
# 3. open()：A1 / A3 / A5
# =====================================================================
def test_open_starts_stream_and_returns_address(services):
    mgr = make_manager(services)
    try:
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri == f"rtsp://127.0.0.1:{RTSP_PORT}/camera1"
        assert services.gcontroll.start_calls == 1, "流不存在时应下发 start"
        assert services.gcontroll.stop_calls == 0
        info = mgr.get_stream_info(CameraId.FRONT_RGB)
        assert info.state is StreamState.READY
        assert info.owner is StreamOwner.SDK
        assert info.uri == uri and info.codec == "H.264"
        assert mgr.is_streaming(CameraId.FRONT_RGB) is True
    finally:
        mgr.shutdown()


def test_open_adopts_existing_stream_without_touching_switch(services):
    """A3：App 已在推流时 open() 不得产生任何开关动作。"""
    services.go2rtc.start_pushing()
    time.sleep(0.05)
    mgr = make_manager(services)
    try:
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri.endswith("/camera1")
        assert services.gcontroll.calls == [], "采用已在推的流时不能碰开关"
        info = mgr.get_stream_info(CameraId.FRONT_RGB)
        assert info.state is StreamState.READY and info.owner is StreamOwner.EXTERNAL
    finally:
        mgr.shutdown()


def test_open_takes_over_a_stuck_external_stream(services):
    """外部流在推但卡住（字节不再增长）：不得当成「已在推的流」直接用。

    旧行为：计数非零就采用 → 地址先给出去，再靠 R2 自愈（真机上会先拿到一个 404 死地址）。
    新行为：不采用；用幂等 start() 接管成 SDK 自己的流，再由卡住/重启逻辑自愈。
    """
    services.go2rtc.start_pushing()
    time.sleep(0.05)
    services.go2rtc.freeze()
    mgr = make_manager(services)
    try:
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri.endswith("/camera1")
        info = mgr.get_stream_info(CameraId.FRONT_RGB)
        assert info.owner is StreamOwner.SDK, "不增长的外部流不能被当成采用来的流"
        assert services.gcontroll.start_calls >= 1, "应由 SDK 自己接管"
        assert wait_for(
            lambda: (mgr.get_stream_info(CameraId.FRONT_RGB).bitrate_kbps or 0) > 0, 2.0
        ), "接管后要有数据在动（不能是死地址）"
    finally:
        mgr.shutdown()


def test_open_rejects_an_external_stream_that_never_grows(services):
    """真机的坑：流刚被停掉（或卡住）时 producer 还在、bytes_recv 是历史值。

    只看「计数非零」就采用，会把这条流当成可用流，返回一个 404 的死地址
    （实测：open() 16 ms 返回，DESCRIBE 404）。卡住且救不回来的外部流必须报错，
    不能把死地址交出去。
    """
    services.go2rtc.start_pushing()
    time.sleep(0.05)
    services.go2rtc.freeze()          # producer 在，但计数不再增长
    services.go2rtc.stuck = True      # 怎么 start 也救不回来
    mgr = make_manager(services)
    try:
        with pytest.raises(VideoTimeoutError) as exc:
            mgr.open(CameraId.FRONT_RGB)
        assert exc.value.reason is LossReason.NO_DATA
    finally:
        mgr.shutdown()


def test_open_after_a_dying_stream_disappears_starts_it_itself(services):
    """正在关闭的流：producer 短暂存在→消失，SDK 必须自己开流，而不是采用死地址。"""
    services.go2rtc.start_pushing()
    time.sleep(0.05)
    services.go2rtc.freeze()          # 正在关闭：计数不再增长
    threading.Timer(0.3, services.go2rtc.drop_producer).start()
    mgr = make_manager(services)
    try:
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri.endswith("/camera1")
        info = mgr.get_stream_info(CameraId.FRONT_RGB)
        assert info.state is StreamState.READY
        assert info.owner is StreamOwner.SDK, "这条流是 SDK 自己开的，不是「采用」来的"
    finally:
        mgr.shutdown()


def test_open_second_caller_shares_state_and_no_extra_start(services):
    mgr = make_manager(services)
    try:
        uri1 = mgr.open(CameraId.FRONT_RGB)
        uri2 = mgr.open(CameraId.FRONT_RGB)
        assert uri1 == uri2
        assert services.gcontroll.start_calls == 1, "同一相机重复 open() 不应重复开流"
        assert mgr.is_streaming(CameraId.FRONT_RGB) is True
    finally:
        mgr.shutdown()


def test_open_times_out_without_data(services):
    """R4：start 返回 200 但没有数据在流时，open() 必须失败（不能给假地址）。"""
    services.gcontroll.go2rtc = None # start 成功，但 producer 永不会出现
    mgr = make_manager(services)
    try:
        started = time.monotonic()
        with pytest.raises(VideoTimeoutError) as exc:
            mgr.open(CameraId.FRONT_RGB)
        assert exc.value.reason is LossReason.NO_DATA
        assert time.monotonic() - started < FAST_OBSERVE.ready_timeout + 1.0
        assert services.gcontroll.start_calls == 1
        assert mgr.is_streaming(CameraId.FRONT_RGB) is False
    finally:
        mgr.shutdown()


def test_open_fails_fast_when_switch_unreachable(services):
    services.gcontroll.set_unreachable()
    mgr = make_manager(services)
    try:
        with pytest.raises(VideoConnectionError) as exc:
            mgr.open(CameraId.FRONT_RGB)
        assert exc.value.reason is LossReason.PORT_UNREACHABLE
        assert "same network" in str(exc.value), "错误信息必须给出下一步动作"
    finally:
        mgr.shutdown()


def test_open_reports_bitrate_from_bytes_recv(services):
    """不拉流也要能报出「有没有数据在动」。"""
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        assert wait_for(
            lambda: (mgr.get_stream_info(CameraId.FRONT_RGB).bitrate_kbps or 0) > 0, 2.0
        ), "bitrate_kbps 应来自 bytes_recv 差分"
    finally:
        mgr.shutdown()


def test_open_adopting_stuck_stream_then_auto_restarts(services):
    """卡住的**外部**流：旧契约是「先采用再自愈」，现在改为「不采用、接管后自愈」。

    接管后的行为已由 test_open_takes_over_a_stuck_external_stream 覆盖
    （owner=SDK、有数据在动）；这里只保留「接管确实发了 start」这一条。
    """
    services.go2rtc.start_pushing()
    time.sleep(0.05)
    services.go2rtc.freeze()
    mgr = make_manager(services)
    try:
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri.endswith("/camera1")
        assert mgr.is_streaming(CameraId.FRONT_RGB) is True
        assert services.gcontroll.start_calls >= 1, "卡住的外部流应由 SDK 接管"
    finally:
        mgr.shutdown()


# =====================================================================
# 4. 观测与恢复：A5 / A6 / A7 / A8
# =====================================================================
def test_external_loss_triggers_l1_recovery(services):
    mgr = make_manager(services)
    events = []
    mgr.on_state_change(events.append)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()

        services.go2rtc.drop_producer() # App 退出 → 流被关
        assert wait_for(
            lambda: any(e.kind is StreamEventKind.LOST and e.reason is LossReason.EXTERNAL for e in events),
            2.0,
        ), "producers 变空必须被检出（R1）"
        assert wait_for(
            lambda: any(e.kind is StreamEventKind.RECONNECTED for e in events), 2.0
        ), "断流后应自动续流（L1）"

        reconnected = [e for e in events if e.kind is StreamEventKind.RECONNECTED][0]
        assert reconnected.recovered_by is RecoveredBy.L1_RESUME
        assert services.gcontroll.start_calls >= 1
        assert services.gcontroll.stop_calls == 0, "L1 续流不应该先 stop（不打断别人）"
        assert mgr.is_streaming(CameraId.FRONT_RGB) is True
    finally:
        mgr.shutdown()


def test_stall_triggers_l2_restart(services):
    """A7：推流卡住时允许自动 stop + start。"""
    mgr = make_manager(services)
    events = []
    mgr.on_state_change(events.append)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()

        services.go2rtc.freeze()
        assert wait_for(
            lambda: any(e.kind is StreamEventKind.LOST and e.reason is LossReason.STALL for e in events),
            2.0,
        )
        assert wait_for(lambda: any(e.kind is StreamEventKind.RECONNECTED for e in events), 2.0)
        reconnected = [e for e in events if e.kind is StreamEventKind.RECONNECTED][0]
        assert reconnected.recovered_by is RecoveredBy.L2_RESTART
        assert services.gcontroll.stop_calls >= 1 and services.gcontroll.start_calls >= 1
    finally:
        mgr.shutdown()


def test_l2_respects_limit_then_error(services):
    """A8：自愈不能变成风暴——超上限就放弃（L3）。"""
    mgr = make_manager(services)
    events = []
    mgr.on_state_change(events.append)
    try:
        mgr.open(CameraId.FRONT_RGB)   # 先正常起来
        services.gcontroll.reset_calls()
        services.go2rtc.stuck = True   # 之后怎么重启都救不回来
        services.go2rtc.freeze()     # 现在卡住
        # 等待预算放宽到 15 s：机器负载高时监督线程的 tick 会变慢，6 s 会偶发超时
        assert wait_for(
            lambda: mgr.get_stream_info(CameraId.FRONT_RGB).state is StreamState.ERROR, 15.0
        ), "反复卡住应最终进入 ERROR"
        assert services.gcontroll.stop_calls <= FAST_RECOVERY.restart_max_per_window
        assert events[-1].kind is StreamEventKind.ERROR

        calls_at_error = list(services.gcontroll.calls)
        time.sleep(0.4)
        assert services.gcontroll.calls == calls_at_error, "ERROR 之后不允许任何自动动作"
    finally:
        mgr.shutdown()


def test_error_is_recoverable_by_new_open(services):
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.go2rtc.stuck = True
        services.go2rtc.freeze()
        assert wait_for(
            lambda: mgr.get_stream_info(CameraId.FRONT_RGB).state is StreamState.ERROR, 15.0
        )
        services.go2rtc.stuck = False
        services.go2rtc.drop_producer()
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri.endswith("/camera1")
        assert mgr.get_stream_info(CameraId.FRONT_RGB).state is StreamState.READY
    finally:
        mgr.shutdown()


def test_probe_unavailable_does_not_fake_lost(services):
    """go2rtc 暂时看不到状态时，不允许误判「断流」（安全侧）。"""
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.go2rtc.set_offline(True)
        time.sleep(0.3)
        assert mgr.get_stream_info(CameraId.FRONT_RGB).state is StreamState.READY
    finally:
        mgr.shutdown()


def test_events_and_unsubscribe(services):
    mgr = make_manager(services)
    events = []
    unsubscribe = mgr.on_state_change(events.append)
    try:
        mgr.open(CameraId.FRONT_RGB)
        assert [e.kind for e in events] == [StreamEventKind.READY]
        assert events[0].name == "StreamReady"
        assert events[0].uri.endswith("/camera1")

        services.go2rtc.start_pushing() # 已在推 → 关流后再自愈
        unsubscribe()
        mgr.close(CameraId.FRONT_RGB)
        assert [e.kind for e in events] == [StreamEventKind.READY], "取消订阅后不应再收到事件"
    finally:
        mgr.shutdown()


def test_callback_exception_does_not_break_state_machine(services):
    mgr = make_manager(services)

    def boom(_event):
        raise RuntimeError("用户回调炸了")

    mgr.on_state_change(boom)
    try:
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri.endswith("/camera1")
        assert mgr.is_streaming(CameraId.FRONT_RGB) is True
    finally:
        mgr.shutdown()


# =====================================================================
# 5. 关闭决策：A4 / A16
# =====================================================================
def test_close_stops_when_nobody_else_watching(services):
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()
        mgr.close(CameraId.FRONT_RGB)
        assert services.gcontroll.stop_calls == 1, "无人观看且流由 SDK 开启 → 应回收"
        assert mgr.get_stream_info(CameraId.FRONT_RGB).state is StreamState.STOPPED
    finally:
        mgr.shutdown()


def test_close_keeps_stream_when_consumer_present(services):
    """A4：还有人在看就不能停推流。"""
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.go2rtc.add_consumer("camera1", ua="Mozilla/5.0 (uni-app)")
        services.gcontroll.reset_calls()
        mgr.close(CameraId.FRONT_RGB)
        assert services.gcontroll.calls == [], "有人在看时 close() 不能停推流"
    finally:
        mgr.shutdown()


def test_close_keeps_external_stream(services):
    """A4：流不是 SDK 开的，即使没人看也不该由 SDK 停掉。"""
    services.go2rtc.start_pushing()
    time.sleep(0.05)
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()
        mgr.close(CameraId.FRONT_RGB)
        assert services.gcontroll.calls == []
    finally:
        mgr.shutdown()


def test_close_keeps_when_consumers_unknown(services):
    """回退：看不到 consumers 时按安全侧处理（不停流）。"""
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()
        services.go2rtc.set_offline(True)
        mgr.close(CameraId.FRONT_RGB)
        assert services.gcontroll.calls == []
        assert "could not confirm" in mgr.get_stream_info(CameraId.FRONT_RGB).message
    finally:
        mgr.shutdown()


def test_close_stops_stream_we_started_earlier(services):
    """本进程早先开过这条流：之后采纳它（owner=external）时 close() 仍要负责回收。

    否则会留下「没人看但一直在推」的空转流。
    """
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB) # 本进程开启
        services.go2rtc.set_offline(True)
        mgr.close(CameraId.FRONT_RGB) # 看不到 consumers → 不停流，但释放本地状态
        services.go2rtc.set_offline(False)

        services.gcontroll.reset_calls()
        mgr.open(CameraId.FRONT_RGB) # 采纳自己早先开的流
        assert mgr.get_stream_info(CameraId.FRONT_RGB).owner is StreamOwner.EXTERNAL
        assert services.gcontroll.calls == [], "采纳自己的流也不应再开一次"

        services.gcontroll.reset_calls()
        mgr.close(CameraId.FRONT_RGB)
        assert services.gcontroll.stop_calls == 1, "自己开的流最终必须被回收"
    finally:
        mgr.shutdown()


def test_close_respects_refcount(services):
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()
        mgr.close(CameraId.FRONT_RGB)
        assert services.gcontroll.calls == [], "还有使用者时不该关流"
        mgr.close(CameraId.FRONT_RGB)
        assert services.gcontroll.stop_calls == 1
    finally:
        mgr.shutdown()


def test_close_is_idempotent(services):
    mgr = make_manager(services)
    try:
        mgr.close(CameraId.FRONT_RGB) # 从未打开
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()
        mgr.close(CameraId.FRONT_RGB)
        mgr.close(CameraId.FRONT_RGB)
        assert services.gcontroll.stop_calls == 1
    finally:
        mgr.shutdown()


def test_open_waits_for_a_close_that_is_still_running(services, monkeypatch):
    """close() 还在收尾（可能马上要停流）时，open() 必须等它做完再开。

    否则新的流会被上一次 close() 的 stop 打断，甚至被对方的 release 取消。
    """
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        mgr.open(CameraId.FRONT_RGB) # 两个使用者，便于分两步关闭

        entered = threading.Event()
        release = threading.Event()
        real_all_watching = mgr._probe.all_watching # noqa: SLF001

        def slow_all_watching(*args, **kwargs):
            entered.set()
            release.wait(20.0)      # 预算放宽：高负载下 close() 可能很久才走到慢路径
            return real_all_watching(*args, **kwargs)

        monkeypatch.setattr(mgr._probe, "all_watching", slow_all_watching) # noqa: SLF001

        mgr.close(CameraId.FRONT_RGB) # 先降引用计数，这一步不会进慢路径
        closer = threading.Thread(target=mgr.close, args=(CameraId.FRONT_RGB,))
        closer.start()
        assert entered.wait(10.0), "close() 应停在慢路径上"

        opened: dict = {}

        def reopen() -> None:
            opened["uri"] = mgr.open(CameraId.FRONT_RGB)

        opener = threading.Thread(target=reopen)
        opener.start()
        time.sleep(0.2)
        assert "uri" not in opened, "close() 未收尾时 open() 不应返回"
        release.set()
        closer.join(20.0)
        opener.join(20.0)

        assert opened.get("uri") == mgr.uri(CameraId.FRONT_RGB)
        assert mgr.is_streaming(CameraId.FRONT_RGB), "新的流不能被上一次 close() 取消"
    finally:
        mgr.shutdown()


def test_open_works_with_chunked_answers(services):
    """真机在响应体变大时会改用 chunked 传输（拉流时响应里带 SDP 就会触发）。

    连「尾随 CRLF 落到下一个 TCP 段」一起覆盖：分帧解码最容易在这里把
    「还没读全」误判成「报文坏了」。
    """
    services.go2rtc.force_chunked = True
    services.go2rtc.chunked_split = True
    mgr = make_manager(services)
    try:
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri == mgr.uri(CameraId.FRONT_RGB)
        assert services.go2rtc.chunked_responses > 0, "mock 应发出 chunked 响应"
        assert services.go2rtc.chunked_splits > 0, "mock 应把 CRLF 拆到下一段发"
        assert mgr.is_streaming(CameraId.FRONT_RGB)
    finally:
        mgr.shutdown()
        services.go2rtc.force_chunked = False
        services.go2rtc.chunked_split = False


def test_stop_stream_forces_stop_and_kills_selfhealing(services):
    """stop_stream()：用户意图明确 → 直接停，并且不能被自愈拉起来。"""
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()
        mgr.stop_stream(CameraId.FRONT_RGB)
        assert services.gcontroll.stop_calls == 1
        assert mgr.is_streaming(CameraId.FRONT_RGB) is False

        time.sleep(0.4)
        assert services.gcontroll.start_calls == 0, "强制停流后不允许自动续流"
        assert services.go2rtc.has_producer("camera1") is False
    finally:
        mgr.shutdown()


def test_stop_stream_also_releases_other_camera(services):
    """stop 是全局开关：另一路的状态也必须归零，否则会被自愈拉起来。"""
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        mgr.open(CameraId.REAR_RGB)
        services.gcontroll.reset_calls()
        mgr.stop_stream(CameraId.FRONT_RGB)
        assert mgr.is_streaming(CameraId.FRONT_RGB) is False
        assert mgr.is_streaming(CameraId.REAR_RGB) is False
        time.sleep(0.3)
        assert services.gcontroll.start_calls == 0
    finally:
        mgr.shutdown()


# =====================================================================
# 6. 生命周期：A14
# =====================================================================
def test_no_supervisor_thread_before_open(services):
    mgr = make_manager(services)
    try:
        assert "dobot-video-supervisor" not in thread_names()
        assert mgr.list_cameras() == [CameraId.FRONT_RGB, CameraId.REAR_RGB]
    finally:
        mgr.shutdown()


def test_supervisor_thread_starts_lazily_and_exits(services):
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        assert "dobot-video-supervisor" in thread_names(), "全局只有 1 个监督线程"
        # 两路相机共用同一个线程
        mgr.open(CameraId.REAR_RGB)
        supervisors = [t for t in threading.enumerate() if t.name == "dobot-video-supervisor"]
        assert len(supervisors) == 1

        mgr.close_all()
        assert wait_for(lambda: "dobot-video-supervisor" not in thread_names(), 3.0)
    finally:
        mgr.shutdown()


def test_close_all_does_not_send_http(services):
    """进程退出 / SDK 关闭时只释放本地状态，不发 HTTP。"""
    mgr = make_manager(services)
    try:
        mgr.open(CameraId.FRONT_RGB)
        services.gcontroll.reset_calls()
        mgr.close_all()
        assert services.gcontroll.calls == []
        assert mgr.get_stream_info(CameraId.FRONT_RGB).state is StreamState.STOPPED
    finally:
        mgr.shutdown()


def test_unknown_camera_degrades_gracefully(services):
    mgr = make_manager(services)
    try:
        assert mgr.is_streaming(CameraId.REAR_RGB) is False
        info = mgr.get_stream_info(CameraId.REAR_RGB)
        assert isinstance(info, CameraStreamInfo)
        assert info.state is StreamState.STOPPED and info.uri == ""
        mgr.close(CameraId.REAR_RGB) # 幂等
    finally:
        mgr.shutdown()


# =====================================================================
# 7. 交付边界：A9（零解码依赖）/ A1（地址可播放）
# =====================================================================
def test_core_package_imports_without_decode_dependencies():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "python"))
    code = (
        "import sys; import dobot_quad; from dobot_quad.video import VideoStreamManager, CameraId;"
        "bad=[m for m in ('av','cv2','numpy') if m in sys.modules];"
        "print('loaded:' + ','.join(bad))"
    )
    env = dict(os.environ, PYTHONPATH=root)
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("loaded:"), out.stdout
    assert not hasattr(VideoStreamManager, "read")
    assert not hasattr(VideoStreamManager, "frames")
    assert not hasattr(VideoStreamManager, "on_frame")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="需要 ffmpeg")
def test_delivered_address_is_playable_by_real_player(services, tmp_path):
    """A1：SDK 交付的地址形式（rtsp://host:port/cameraN）能被标准播放器直接拉取。

    媒体面不在 SDK 内，所以这里用真实 ffmpeg 对着 mock RTSP 服务端验证一次：
    它证明「地址 + 相机编号映射」这一交付契约是对的。
    """
    from mock_rtsp_server import MockRtspServer, make_sample_h264

    sample = make_sample_h264(str(tmp_path / "sample.h264"), width=320, height=240)
    server = MockRtspServer(sample, fps=30.0)
    port = server.start()
    services.go2rtc.start_pushing()
    time.sleep(0.05)

    mgr = make_manager(services, rtsp_port=port)
    try:
        uri = mgr.open(CameraId.FRONT_RGB)
        assert uri == f"rtsp://127.0.0.1:{port}/camera1"

        out = tmp_path / "frame.jpg"
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-rtsp_transport", "tcp", "-i", uri,
                "-frames:v", "1", "-f", "image2", "-y", str(out),
            ],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        assert out.exists() and out.stat().st_size > 0
        assert server.clients_served >= 1
    finally:
        mgr.shutdown()
        try:
            server.stop()
        except Exception: # pragma: no cover
            pass
