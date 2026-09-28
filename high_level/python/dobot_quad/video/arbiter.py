"""Per-camera stream state machine and recovery.

For one camera it starts the stream, adopting one that is already running when
possible, and only reports success once data really flows. It keeps watching the
stream while it is up, and brings it back after a drop: resume first, restart
when data had stalled, then give up with a reason the user can act on.

No thread of its own: `VideoStreamManager`'s supervisor thread drives `tick()`,
while `open()` waits on the calling thread.
"""

from __future__ import annotations

import enum
import logging
import threading
from typing import Callable, List, Optional, Tuple

from .probe import StatusProbe, StreamStatus
from .types import (
    CAMERA_SPECS,
    STREAM_CODEC,
    CameraId,
    CameraStreamInfo,
    LossReason,
    ObserveConfig,
    RecoveredBy,
    RecoveryPolicy,
    StreamEvent,
    StreamEventKind,
    StreamOwner,
    StreamState,
    VideoError,
    monotonic_s,
    raise_video_error,
)

__all__ = ["StreamArbiter", "RestartOutcome"]

_log = logging.getLogger("dobot_quad.video")


class RestartOutcome(enum.Enum):
    """Result of a restart attempt.

    "Out of attempts" and "the attempt itself failed" are reported separately so
    that the message shown to the user is accurate.
    """

    DONE = "done"              # Restarted; now waiting for data
    COOLING = "cooling"        # Too soon after the last restart; will retry later
    LIMIT = "limit"            # Restart budget used up; recovery gives up
    FAILED = "failed"          # The attempt failed (network); it will be retried
    UNREACHABLE = "unreachable"  # The robot cannot be reached; stream goes to ERROR


class StreamArbiter:
    """State machine of one camera stream."""

    def __init__(
        self,
        camera: CameraId,
        uri: str,
        probe: StatusProbe,
        controller,
        *,
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        observe: Optional[ObserveConfig] = None,
        policy: Optional[RecoveryPolicy] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._camera = camera
        self._uri = uri
        self._probe = probe
        self._controller = controller
        self._observe = observe or ObserveConfig()
        self._policy = policy or RecoveryPolicy()
        self._on_event = on_event
        self._log = logger or _log

        self._cv = threading.Condition(threading.RLock())
        self._state = StreamState.STOPPED
        self._owner = StreamOwner.UNKNOWN
        self._reason = LossReason.NONE
        self._message = ""

        # starting up / recovering
        self._deadline = 0.0
        self._sdk_started = False
        self._start_issued = False
        self._recovered_by = RecoveredBy.NONE

        # byte counter difference
        self._prev_bytes: Optional[int] = None
        self._prev_at: Optional[float] = None
        self._prev_fetch_at: float = -1.0
        self._last_grew = False
        self._stall_count = 0
        self._no_growth_since: Optional[float] = None
        self._bitrate_kbps: Optional[float] = None

        # recovery scheduling
        self._attempt = 0
        self._next_attempt_at = 0.0
        self._acting = False
        self._act_deadline = 0.0
        self._recover_started_at = 0.0
        self._restart_times: List[float] = []

    # ------------------------------------------------------------ read-only
    @property
    def camera(self) -> CameraId:
        return self._camera

    @property
    def uri(self) -> str:
        return self._uri

    @property
    def state(self) -> StreamState:
        with self._cv:
            return self._state

    @property
    def sdk_started(self) -> bool:
        """Whether this SDK started the stream (used when closing)."""
        with self._cv:
            return self._sdk_started

    @property
    def needs_fast_sample(self) -> bool:
        """Whether this stream is in a phase that needs quick sampling."""
        with self._cv:
            return self._state in (StreamState.PREPARING, StreamState.RECOVERING)

    def info(self) -> CameraStreamInfo:
        with self._cv:
            return CameraStreamInfo(
                camera=self._camera,
                state=self._state,
                owner=self._owner,
                # the address belongs to the camera and stays valid while it streams
                uri=self._uri,
                codec=STREAM_CODEC,
                bitrate_kbps=self._bitrate_kbps,
                reason=self._reason,
                message=self._message,
            )

    # ------------------------------------------------------------ life cycle
    def begin(self) -> None:
        """Entry point of open(): starts this camera (idempotent)."""
        now = monotonic_s()
        with self._cv:
            if self._state in (StreamState.READY, StreamState.PREPARING):
                return  # already open or opening
            self._state = StreamState.PREPARING
            self._reason = LossReason.NONE
            self._message = ""
            self._deadline = now + self._observe.ready_timeout
            self._start_issued = False
            self._sdk_started = False
            self._owner = StreamOwner.UNKNOWN
            self._recovered_by = RecoveredBy.NONE
            self._attempt = 0
            self._acting = False
            self._next_attempt_at = 0.0
            self._restart_times = []
            self._prev_bytes = None
            self._prev_at = None
            self._prev_fetch_at = -1.0
            self._stall_count = 0
            self._no_growth_since = None
            self._bitrate_kbps = None
        self._log.debug("[%s] opening the stream (uri=%s)", self._camera.name, self._uri)

    def wait_ready(self, timeout: Optional[float] = None) -> str:
        """Waits until the stream is ready, or fails.

        Returns:
            Address your player can open.

        Raises:
            VideoError: the stream timed out, recovery gave up, or it was
                released while waiting.
        """
        limit = self._observe.ready_timeout if timeout is None else timeout
        end = monotonic_s() + limit
        with self._cv:
            while True:
                if self._state is StreamState.READY:
                    return self._uri
                if self._state is StreamState.ERROR:
                    # 按 reason 归类：用户能 except VideoConnectionError /
                    # VideoTimeoutError，而不是只能 except 基类（except VideoError
                    # 仍然照常工作）。
                    raise_video_error(
                        f"{self._camera.name}: stream is not ready: "
                        f"{self._message or self._reason.value}",
                        reason=self._reason,
                        camera=self._camera,
                    )
                if self._state is StreamState.STOPPED:
                    raise_video_error(
                        f"{self._camera.name}: opening was cancelled",
                        reason=LossReason.CLOSED,
                        camera=self._camera,
                    )
                remaining = end - monotonic_s()
                if remaining <= 0:
                    break
                self._cv.wait(min(remaining, 0.2))
        raise_video_error(
            f"{self._camera.name}: the stream was not ready within {limit:.1f} s. "
            f"It may still be starting up: try again in a few seconds.",
            reason=LossReason.NO_DATA,
            camera=self._camera,
        )

    def release(self, *, reason: LossReason = LossReason.CLOSED, message: str = "") -> None:
        """Called by close(): drops this user (idempotent)."""
        event = None
        with self._cv:
            old = self._state
            if old is StreamState.STOPPED:
                return
            self._state = StreamState.STOPPING
        with self._cv:
            self._state = StreamState.STOPPED
            self._reason = reason
            self._message = message
            self._deadline = 0.0
            self._acting = False
            self._prev_bytes = None
            self._prev_at = None
            self._prev_fetch_at = -1.0
            self._stall_count = 0
            self._bitrate_kbps = None
            self._cv.notify_all()
            event = StreamEvent(
                kind=StreamEventKind.CLOSED,
                camera=self._camera,
                old_state=old,
                new_state=StreamState.STOPPED,
                reason=reason,
                uri=self._uri,
                message=message,
            )
        self._emit(event)

    def mark_force_stopped(self, *, message: str = "Stopped by stop_stream()") -> None:
        """Called by stop_stream(): resets to STOPPED and stops recovering."""
        with self._cv:
            old = self._state
            self._state = StreamState.STOPPED
            self._sdk_started = False
            self._start_issued = False
            self._reason = LossReason.CLOSED
            self._message = message
            self._acting = False
            self._prev_bytes = None
            self._prev_at = None
            self._stall_count = 0
            self._bitrate_kbps = None
            self._cv.notify_all()
        if old is not StreamState.STOPPED:
            self._emit(
                StreamEvent(
                    kind=StreamEventKind.CLOSED,
                    camera=self._camera,
                    old_state=old,
                    new_state=StreamState.STOPPED,
                    reason=LossReason.CLOSED,
                    uri=self._uri,
                    message=message,
                )
            )

    # ------------------------------------------------------------ supervisor tick
    def tick(self, now: Optional[float] = None) -> None:
        """Called periodically by the manager's supervisor thread."""
        now = monotonic_s() if now is None else now
        state = self.state
        try:
            if state is StreamState.PREPARING:
                self._tick_prepare(now)
            elif state is StreamState.READY:
                self._tick_ready(now)
            elif state is StreamState.RECOVERING:
                self._tick_recover(now)
        except Exception:  # pragma: no cover - stay alive on callback errors
            self._log.exception("[%s] tick failed", self._camera.name)

    # ---- start up
    def _tick_prepare(self, now: float) -> None:
        status = self._probe.status(self._camera, force=True)
        grew = self._sample(status, now)
        with self._cv:
            deadline = self._deadline
            started = self._sdk_started

        if status.available and status.has_producer:
            if grew:
                self._become_ready(StreamOwner.SDK if started else StreamOwner.EXTERNAL)
                self._log.info(
                    "[%s] %s: %s",
                    self._camera.name,
                    "stream ready" if started else "adopting the running stream",
                    self._uri,
                )
                return
            # A stream that is already running is adopted only once the byte
            # counter really grew between two samples. A non-zero count alone is
            # not evidence: a stream that was just stopped (or one that is
            # stuck) keeps reporting its historical count for a moment, and
            # adopting it hands the caller an address that answers 404.
            # A genuinely running stream grows within one poll interval
            # (prepare_poll); one that never grows falls through to the
            # ready_timeout below, and one that disappears is started by us in
            # the ``else`` branch.
            if self._no_growth_since is None:
                with self._cv:
                    self._no_growth_since = now
            elif (now - self._no_growth_since) >= self._observe.prepare_stall_seconds:
                if started:
                    # the stream exists but carries nothing: restart it
                    if self._try_restart(now, LossReason.STALL) is RestartOutcome.LIMIT:
                        self._fail(
                            LossReason.STALL,
                            "The camera is set to stream but sends no picture data; "
                            "automatic recovery gave up.",
                        )
                    return
                # Somebody else's stream is sitting there without carrying any
                # data (it was just stopped, or it is stuck). That is not
                # "already running" in any useful sense, and adopting it would
                # hand the caller an address that answers 404, so take it over
                # with an idempotent start() and let the normal stall / restart
                # logic above heal it from here.
                self._log.info(
                    "[%s] the running stream carries no new data; taking it over",
                    self._camera.name,
                )
                if not self._issue_start(now):
                    return
        else:
            with self._cv:
                self._no_growth_since = None
            if not started:
                if not self._issue_start(now):
                    return
            elif now >= deadline:
                reason = LossReason.NO_DATA
                if not self._controller_reachable():
                    reason = LossReason.PORT_UNREACHABLE
                self._fail(reason, self._fail_message(reason))
                return

        if now >= deadline:
            reason = LossReason.NO_DATA if self._controller_reachable() else LossReason.PORT_UNREACHABLE
            self._fail(reason, self._fail_message(reason))

    # ---- observe
    def _tick_ready(self, now: float) -> None:
        status = self._probe.status(self._camera)
        grew = self._sample(status, now)
        if not status.available:
            return  # no state at all: change nothing

        if not status.has_producer:
            self._enter_recovering(
                LossReason.EXTERNAL, "The stream was stopped outside the SDK."
            )
            return

        with self._cv:
            stalled = self._stall_count >= self._observe.stall_samples
        if stalled and not grew:
            self._enter_recovering(
                LossReason.STALL,
                f"Streaming stalled: no new data in {self._observe.stall_samples} samples.",
            )

    # ---- recover
    def _tick_recover(self, now: float) -> None:
        status = self._probe.status(self._camera, force=True)
        grew = self._sample(status, now)
        with self._cv:
            acting = self._acting
            act_deadline = self._act_deadline
            next_at = self._next_attempt_at
            reason = self._reason
            started_at = self._recover_started_at

        # recovery worked: the stream is back and data is flowing again
        if status.available and status.has_producer and grew:
            self._become_ready(
                self._owner,
                recovered_by=RecoveredBy.L2_RESTART if self._used_l2() else RecoveredBy.L1_RESUME,
            )
            return

        if acting:
            if now < act_deadline:
                return
            # the attempt did not help
            with self._cv:
                self._acting = False
                self._attempt += 1
                attempt = self._attempt
            if reason is LossReason.PORT_UNREACHABLE or not self._controller_reachable():
                self._fail(LossReason.PORT_UNREACHABLE, self._fail_message(LossReason.PORT_UNREACHABLE))
                return
            if attempt > self._policy.max_attempts:
                self._fail(
                    reason,
                    f"Automatic recovery failed after {self._policy.max_attempts} attempts.",
                )
                return
            backoff = self._policy.backoff[min(attempt - 1, len(self._policy.backoff) - 1)]
            with self._cv:
                self._next_attempt_at = now + backoff
            self._log.info(
                "[%s] recovery attempt %d failed, retrying in %.1fs",
                self._camera.name,
                attempt,
                backoff,
            )
            return

        if now < next_at:
            return
        if now - started_at > self._observe.ready_timeout * self._policy.max_attempts:
            self._fail(reason, "Automatic recovery timed out.")
            return

        # run the recovery action
        if reason is LossReason.STALL:
            if self._try_restart(now, reason) is RestartOutcome.LIMIT:
                self._fail(
                    reason,
                    f"The stream keeps stalling and automatic restarts are used up "
                    f"({self._policy.restart_max_per_window} in "
                    f"{self._policy.restart_window / 60:.0f} minutes).",
                )
        else:
            self._do_action(RecoveredBy.L1_RESUME, now, reason)

    def _enter_recovering(self, reason: LossReason, message: str) -> None:
        event = None
        with self._cv:
            old = self._state
            if old not in (StreamState.READY,):
                return
            self._state = StreamState.RECOVERING
            self._reason = reason
            self._message = message
            self._attempt = 0
            self._acting = False
            self._next_attempt_at = 0.0
            self._recover_started_at = monotonic_s()
            self._stall_count = 0
            self._no_growth_since = None
            window_start = self._recover_started_at - self._policy.restart_window
            self._restart_times = [t for t in self._restart_times if t >= window_start]
            event = StreamEvent(
                kind=StreamEventKind.LOST,
                camera=self._camera,
                old_state=old,
                new_state=StreamState.RECOVERING,
                reason=reason,
                uri=self._uri,
                message=message,
            )
        self._log.warning("[%s] stream problem: %s", self._camera.name, message)
        self._emit(event)

    def _try_restart(self, now: float, reason: LossReason) -> RestartOutcome:
        """Restarts the stream (``stop`` + ``start``), honouring cooldown and budget.

        Returns:
            RestartOutcome, which separates "done", "cooling down", "out of
            attempts", "the attempt failed" and "the robot is unreachable", so
            the caller can report what really happened.
        """
        with self._cv:
            window_start = now - self._policy.restart_window
            self._restart_times = [t for t in self._restart_times if t >= window_start]
            if len(self._restart_times) >= self._policy.restart_max_per_window:
                return RestartOutcome.LIMIT
            last = self._restart_times[-1] if self._restart_times else None
        if last is not None and (now - last) < self._policy.restart_cooldown:
            # still cooling down: not a failure, just wait for the cooldown
            with self._cv:
                self._next_attempt_at = last + self._policy.restart_cooldown
            return RestartOutcome.COOLING
        if not self._controller_reachable():
            self._fail(LossReason.PORT_UNREACHABLE, self._fail_message(LossReason.PORT_UNREACHABLE))
            return RestartOutcome.UNREACHABLE
        self._log.warning("[%s] streaming stalled, restarting (stop + start)", self._camera.name)
        try:
            self._controller.stop()
            self._controller.start()
        except Exception as exc:  # pragma: no cover - needs a real network
            self._log.warning("[%s] restart failed: %s", self._camera.name, exc)
            with self._cv:
                self._next_attempt_at = now + self._policy.backoff[0]
                self._no_growth_since = now
            return RestartOutcome.FAILED
        with self._cv:
            self._restart_times.append(now)
            self._sdk_started = True
            self._start_issued = True
            self._recovered_by = RecoveredBy.L2_RESTART
            self._acting = True
            self._act_deadline = now + self._policy.act_timeout
            self._prev_bytes = None
            self._prev_at = None
            self._prev_fetch_at = -1.0
            self._stall_count = 0
            self._no_growth_since = now
        if self.state is StreamState.PREPARING:
            with self._cv:
                self._deadline = max(self._deadline, now + self._observe.ready_timeout)
        return RestartOutcome.DONE

    def _do_action(self, action: RecoveredBy, now: float, reason: LossReason) -> None:
        if not self._controller_reachable():
            self._fail(LossReason.PORT_UNREACHABLE, self._fail_message(LossReason.PORT_UNREACHABLE))
            return
        try:
            if action is RecoveredBy.L1_RESUME:
                self._log.info("[%s] resuming the stream (POST /start)", self._camera.name)
                self._controller.start()
            else:  # pragma: no cover - resume is the only action so far
                self._controller.stop()
                self._controller.start()
        except Exception as exc:  # pragma: no cover - needs a real network
            self._log.warning("[%s] recovery action failed: %s", self._camera.name, exc)
            with self._cv:
                self._next_attempt_at = now + self._policy.backoff[0]
            return
        with self._cv:
            self._sdk_started = True
            self._start_issued = True
            self._recovered_by = action
            self._acting = True
            self._act_deadline = now + self._policy.act_timeout
            self._prev_bytes = None
            self._prev_at = None
            self._prev_fetch_at = -1.0
            self._stall_count = 0
            self._no_growth_since = None

    def _used_l2(self) -> bool:
        with self._cv:
            return self._recovered_by is RecoveredBy.L2_RESTART

    def _become_ready(
        self,
        owner: StreamOwner,
        *,
        recovered_by: RecoveredBy = RecoveredBy.NONE,
    ) -> None:
        event = None
        with self._cv:
            old = self._state
            self._state = StreamState.READY
            self._owner = owner
            self._reason = LossReason.NONE
            self._acting = False
            self._deadline = 0.0
            self._stall_count = 0
            self._no_growth_since = None
            if recovered_by is RecoveredBy.NONE:
                self._recovered_by = RecoveredBy.NONE
            else:
                self._recovered_by = recovered_by
            self._message = ""
            kind = StreamEventKind.READY if recovered_by is RecoveredBy.NONE else StreamEventKind.RECONNECTED
            message = (
                "Ready to play."
                if recovered_by is RecoveredBy.NONE
                else f"Recovered ({recovered_by.value}); watchers may have seen a short "
                "interruption."
            )
            event = StreamEvent(
                kind=kind,
                camera=self._camera,
                old_state=old,
                new_state=StreamState.READY,
                reason=LossReason.NONE,
                recovered_by=recovered_by,
                uri=self._uri,
                message=message,
            )
            self._cv.notify_all()
        self._emit(event)

    def _fail(self, reason: LossReason, message: str) -> None:
        event = None
        with self._cv:
            old = self._state
            if old is StreamState.ERROR:
                return
            self._state = StreamState.ERROR
            self._reason = reason
            self._message = message
            self._acting = False
            self._deadline = 0.0
            self._cv.notify_all()
            event = StreamEvent(
                kind=StreamEventKind.ERROR,
                camera=self._camera,
                old_state=old,
                new_state=StreamState.ERROR,
                reason=reason,
                uri=self._uri,
                message=message,
            )
        self._log.error("[%s] %s", self._camera.name, message)
        self._emit(event)

    def _fail_message(self, reason: LossReason) -> str:
        if reason is LossReason.PORT_UNREACHABLE:
            return (
                "Cannot reach the robot's streaming service. Check that this host and "
                "the robot are on the same network."
            )
        return (
            "The camera did not start streaming in time. It may still be starting up: "
            "try again in a few seconds."
        )

    # ---- actions
    def _issue_start(self, now: float) -> bool:
        """Sends ``start`` once while preparing; returns whether to keep waiting."""
        with self._cv:
            if self._start_issued:
                return True
            self._start_issued = True
        if not self._controller_reachable():
            self._fail(LossReason.PORT_UNREACHABLE, self._fail_message(LossReason.PORT_UNREACHABLE))
            return False
        self._log.info("[%s] no stream yet, sending POST /start", self._camera.name)
        try:
            self._controller.start()
        except Exception as exc:  # pragma: no cover - needs a real network
            self._log.warning("[%s] POST /start failed: %s", self._camera.name, exc)
            with self._cv:
                self._start_issued = False
            return True
        with self._cv:
            self._sdk_started = True
            self._owner = StreamOwner.SDK
            self._prev_bytes = None
            self._prev_at = None
            self._prev_fetch_at = -1.0
            self._no_growth_since = None
        return True

    def _controller_reachable(self) -> bool:
        try:
            return bool(self._controller.reachable())
        except Exception:  # pragma: no cover - needs a real network
            return False

    # ---- difference
    def _sample(self, status: StreamStatus, now: float) -> bool:
        """Updates the byte counter difference; True when data grew since the last
        sample."""
        with self._cv:
            if status.fetched_at == self._prev_fetch_at:
                return self._last_grew  # same snapshot as before: do not count it twice
            prev = self._prev_bytes
            prev_at = self._prev_at
            ready = self._state is StreamState.READY
            self._prev_fetch_at = status.fetched_at

        grew = False
        if status.available:
            if prev is not None and status.bytes_recv > prev:
                grew = True
                if prev_at is not None and now > prev_at:
                    self._bitrate_kbps = (status.bytes_recv - prev) * 8.0 / (now - prev_at) / 1000.0

        with self._cv:
            if status.available:
                self._prev_bytes = status.bytes_recv
                self._prev_at = now
            if grew:
                self._stall_count = 0
                self._no_growth_since = None
            elif ready and status.available and status.has_producer:
                self._stall_count += 1
            self._last_grew = grew
        return grew

    # ---- events
    def _emit(self, event: Optional[StreamEvent]) -> None:
        if event is None or self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:  # pragma: no cover - callback errors must not disturb us
            self._log.exception("[%s] event callback raised", self._camera.name)
