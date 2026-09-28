"""`robot.video`: the entry point of the camera video streaming API.

It switches the stream on, watches it and hands you an address.

* Media handling (pulling, decoding, muxing) is not part of this module:
  `open()` returns an address and your own player or vision code connects to it.
* One supervisor thread drives the state machine of every camera.

The public methods are `list_cameras` / `open` / `is_streaming` / `get_stream_info`
/ `on_state_change` / `close` / `stop_stream`。
"""

from __future__ import annotations

import atexit
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .arbiter import StreamArbiter
from .controller import StreamingController
from .probe import StatusProbe
from .types import (
    CAMERA_SPECS,
    CameraId,
    CameraStreamInfo,
    LossReason,
    ObserveConfig,
    RecoveredBy,
    RecoveryPolicy,
    StreamEvent,
    StreamState,
    VideoError,
    monotonic_s,
)

__all__ = ["VideoStreamManager", "Endpoints", "CameraId"]

_log = logging.getLogger("dobot_quad.video")


@dataclass(frozen=True)
class Endpoints:
    """Service ports (defaults match the robot; tests inject their own)."""

    http_port: int = 22000    # Robot streaming switch (HTTP)
    go2rtc_port: int = 1984   # Camera state API (HTTP)
    rtsp_port: int = 8554     # RTSP media port (your player connects here)


@dataclass
class _Entry:
    arbiter: StreamArbiter
    refcount: int = 1


class VideoStreamManager:
    """Implementation behind ``robot.video``; thread-safe."""

    def __init__(
        self,
        host: str,
        *,
        endpoints: Optional[Endpoints] = None,
        rtsp_port: Optional[int] = None,
        go2rtc_port: Optional[int] = None,
        http_port: Optional[int] = None,
        controller: Optional[StreamingController] = None,
        probe: Optional[StatusProbe] = None,
        observe: Optional[ObserveConfig] = None,
        policy: Optional[RecoveryPolicy] = None,
        register_atexit: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._log = logger or _log
        self._host = str(host).strip()
        ep = endpoints or Endpoints()
        if rtsp_port is not None or go2rtc_port is not None or http_port is not None:
            ep = Endpoints(
                http_port=http_port if http_port is not None else ep.http_port,
                go2rtc_port=go2rtc_port if go2rtc_port is not None else ep.go2rtc_port,
                rtsp_port=rtsp_port if rtsp_port is not None else ep.rtsp_port,
            )
        self._endpoints = ep
        self._observe = observe or ObserveConfig()
        self._policy = policy or RecoveryPolicy()

        self._controller = controller or StreamingController(
            self._host, port=ep.http_port, timeout=self._observe.probe_timeout
        )
        self._probe = probe or StatusProbe(
            self._host, port=ep.go2rtc_port,
            timeout=self._observe.probe_timeout, observe=self._observe,
        )

        self._lock = threading.RLock()
        self._teardown_cv = threading.Condition(self._lock)
        self._entries: Dict[CameraId, _Entry] = {}
        #: Last known state of every camera, kept after close()
        self._history: Dict[CameraId, CameraStreamInfo] = {}
        #: Cameras being closed right now: no longer usable, still releasing
        #: (which may include telling the robot to stop). open() waits for them.
        self._closing: Dict[CameraId, _Entry] = {}
        #: Streams this process has ever started: adopting our own earlier stream
        #: must still count as ours when it is released later.
        self._sdk_owned: Dict[CameraId, bool] = {}
        self._listeners: List[Callable[[StreamEvent], None]] = []
        self._thread: Optional[threading.Thread] = None
        self._thread_stop = threading.Event()
        self._closed = False

        if register_atexit:
            atexit.register(self._atexit_cleanup)

    # ------------------------------------------------------------------ accessors
    @property
    def host(self) -> str:
        return self._host

    @property
    def endpoints(self) -> Endpoints:
        return self._endpoints

    def uri(self, camera: CameraId) -> str:
        """RTSP address of this camera; does not touch the robot."""
        cam = CameraId(camera)
        return f"rtsp://{self._host}:{self._endpoints.rtsp_port}/{CAMERA_SPECS[cam].rtsp_name}"

    # ------------------------------------------------------------------ cameras
    def list_cameras(self) -> List[CameraId]:
        """Cameras available on this robot."""
        return list(CAMERA_SPECS.keys())

    # ------------------------------------------------------------------ open
    def open(self, camera: CameraId) -> str:
        """Starts this camera's stream, or adopts one that is already running.

        Blocks until data is really flowing, then returns the address to play.

        Opening a camera that is already open is cheap: it only raises a
        reference count and returns the same address.

        Args:
            camera: which camera.

        Returns:
            RTSP address to hand to your player / `cv2.VideoCapture` / `ffmpeg`.

        Raises:
            VideoError: the stream was not ready in time, or the robot's
                streaming service could not be reached.
        """
        cam = CameraId(camera)
        with self._lock:
            if self._closed:
                raise VideoError(f"{cam.name}: the video manager was shut down", camera=cam)
            # A close() that is still running may be about to stop the robot's
            # stream: wait for it, or it would kill the stream we open now.
            self._teardown_cv.wait_for(lambda: cam not in self._closing, timeout=5.0)
            entry = self._entries.get(cam)
            if entry is None:
                entry = _Entry(arbiter=self._make_arbiter(cam), refcount=0)
                self._entries[cam] = entry
            entry.refcount += 1
        self._ensure_supervisor()
        try:
            entry.arbiter.begin()
            uri = entry.arbiter.wait_ready()
        except VideoError:
            self._abort_open(cam, entry)
            raise
        if entry.arbiter.sdk_started:
            with self._lock:
                self._sdk_owned[cam] = True
        return uri

    def _abort_open(self, cam: CameraId, entry: _Entry) -> None:
        with self._lock:
            entry.refcount -= 1
            if entry.refcount > 0:
                return
            if self._entries.get(cam) is entry:
                del self._entries[cam]
            self._closing[cam] = entry
        entry.arbiter.release(reason=LossReason.CLOSED, message="open() failed; local state released")
        with self._lock:
            self._history[cam] = entry.arbiter.info()
            # Unconditional: open() waits for this marker before it can create a
            # new entry, so the marker can only be ours.
            self._closing.pop(cam, None)
        self._signal_teardown()
        self._maybe_stop_supervisor()

    # ---------------------------------------------------------------- queries
    def is_streaming(self, camera: CameraId) -> bool:
        """Whether this camera's stream is ready to play right now."""
        with self._lock:
            entry = self._find_entry(CameraId(camera))
        return entry is not None and entry.arbiter.state is StreamState.READY

    def get_stream_info(self, camera: CameraId) -> CameraStreamInfo:
        """Snapshot of this camera (state is STOPPED before the first open()).

        After close() the last known state stays readable, including the address
        and whether the stream was left running.
        """
        cam = CameraId(camera)
        with self._lock:
            entry = self._find_entry(cam)
            if entry is None:
                return self._history.get(cam) or CameraStreamInfo(
                    camera=cam, state=StreamState.STOPPED
                )
        return entry.arbiter.info()

    # ----------------------------------------------------------------- events
    def on_state_change(self, callback: Callable[[StreamEvent], None]) -> Callable[[], None]:
        """Subscribes to stream events; the returned function unsubscribes.

        Callbacks run on the SDK's supervisor thread: do not call blocking
        methods from one (`open()` in particular).
        """
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            self._listeners.append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._listeners.remove(callback)
                except ValueError:
                    pass

        return _unsubscribe

    # ------------------------------------------------------------------ close
    def close(self, camera: CameraId) -> None:
        """Stops using this camera (idempotent).

        The stream is stopped only when the last user releases it and nobody else
        is watching (phone app, player).
        """
        cam = CameraId(camera)
        with self._lock:
            entry = self._entries.get(cam)
            if entry is None:
                return
            entry.refcount -= 1
            if entry.refcount > 0:
                return
            # Out of _entries right away: a concurrent open() must not adopt a
            # stream that is being released (it would be cancelled halfway).
            del self._entries[cam]
            self._closing[cam] = entry
        sdk_started = entry.arbiter.sdk_started
        with self._lock:
            # adopting a stream we started earlier: sdk_started is false this time
            if self._sdk_owned.get(cam):
                sdk_started = True
        # Only stop when no other watcher is known to exist on any camera.
        watching = self._probe.all_watching(
            samples=2, interval=self._observe.settle_seconds
        )
        if watching:
            message = "Stream left running: another watcher (app or player) is using it"
            keep = True
        elif watching is None:
            message = "Stream left running: could not confirm that nobody else is watching"
            keep = True
        elif sdk_started:
            message = "Stream stopped, resources released"
            keep = False
        else:
            message = "Stream left running: it was not started by this SDK"
            keep = False

        entry.arbiter.release(reason=LossReason.CLOSED, message=message)
        if not keep and sdk_started:
            try:
                self._controller.stop()
                self._log.info("[video] nobody is watching, stopping the stream")
            except Exception as exc:  # pragma: no cover - needs a real network
                self._log.warning("[video] could not stop the stream: %s", exc)

        with self._lock:
            self._history[cam] = entry.arbiter.info()
            if not keep:
                self._sdk_owned[cam] = False  # stopped now, no longer ours
            # Unconditional: open() waits for this marker before it can create a
            # new entry, so the marker can only be ours.
            self._closing.pop(cam, None)
        self._signal_teardown()
        self._maybe_stop_supervisor()

    def close_all(self, *, reason: LossReason = LossReason.CLOSED, message: str = "") -> None:
        """Releases every camera (idempotent, never touches the robot).

        Use it on your way out of the program.
        """
        with self._lock:
            entries = [(cam, e) for cam, e in self._entries.items()]
            self._entries.clear()
        for _cam, entry in entries:
            entry.refcount = 0
            try:
                entry.arbiter.release(reason=reason, message=message)
            except Exception:  # pragma: no cover
                self._log.exception("[video] releasing %s failed", entry.arbiter.camera.name)
            with self._lock:
                self._history[entry.arbiter.camera] = entry.arbiter.info()
        self._maybe_stop_supervisor()

    # ------------------------------------------------------------- stop_stream
    def stop_stream(self, camera: CameraId) -> None:
        """Stops pushing without asking anyone: the robot is told to stop even
        while another app is watching.

        The robot has one switch for both cameras, so this also clears the local
        state of the other camera.
        """
        cam = CameraId(camera)
        with self._lock:
            entries = list(self._entries.values())
        for entry in entries:
            entry.arbiter.mark_force_stopped(
                message=f"Stopped by stop_stream({cam.name})"
            )
            with self._lock:
                self._history[entry.arbiter.camera] = entry.arbiter.info()
        try:
            self._controller.stop()
        except Exception as exc:  # pragma: no cover - needs a real network
            self._log.warning("[video] could not stop the stream: %s", exc)
        with self._lock:
            self._sdk_owned.clear()  # one switch for both cameras: nothing is ours
        self._maybe_stop_supervisor()

    # -------------------------------------------------------------- life cycle
    def shutdown(self) -> None:
        """Stops the supervisor thread and drops all local state (no HTTP call)."""
        self.close_all(reason=LossReason.CLOSED, message="manager shut down; local state released")
        with self._lock:
            self._closed = True
            self._listeners.clear()
            self._closing.clear()
        self._stop_supervisor()

    def close_manager(self) -> None:  # pragma: no cover - alias kept for compatibility
        self.shutdown()

    def __enter__(self) -> "VideoStreamManager":
        return self

    def __exit__(self, *_exc) -> None:
        self.shutdown()

    def _atexit_cleanup(self) -> None:
        """Leaving the process: drop local state only, never call the robot."""
        try:
            with self._lock:
                self._entries.clear()
            self._stop_supervisor()
        except Exception:  # pragma: no cover - interpreter shutdown
            pass

    # ------------------------------------------------------------------ internals
    def _signal_teardown(self) -> None:
        """Wakes open() calls that are waiting for a close() to finish."""
        with self._teardown_cv:
            self._teardown_cv.notify_all()

    def _find_entry(self, cam: CameraId) -> Optional[_Entry]:
        """Live registry first, then cameras that are still being released."""
        entry = self._entries.get(cam)
        if entry is not None:
            return entry
        return self._closing.get(cam)
    def _make_arbiter(self, camera: CameraId) -> StreamArbiter:
        return StreamArbiter(
            camera,
            self.uri(camera),
            self._probe,
            self._controller,
            on_event=self._dispatch,
            observe=self._observe,
            policy=self._policy,
            logger=self._log,
        )

    def _dispatch(self, event: StreamEvent) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for callback in listeners:
            try:
                callback(event)
            except Exception:  # pragma: no cover - stay alive on callback errors
                self._log.exception("[video] state callback raised")

    # ----------------------------------------------------------- supervisor thread
    def _ensure_supervisor(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread_stop.clear()
            self._thread = threading.Thread(
                target=self._supervise, name="dobot-video-supervisor", daemon=True
            )
            self._thread.start()

    def _maybe_stop_supervisor(self) -> None:
        with self._lock:
            if self._entries or self._thread is None:
                return
            thread = self._thread
            self._thread = None
            self._thread_stop.set()
        if thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _stop_supervisor(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._thread_stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _supervise(self) -> None:
        """The single background thread: drives every camera state machine."""
        while not self._thread_stop.is_set():
            started = monotonic_s()
            with self._lock:
                arbiters = [entry.arbiter for entry in self._entries.values()]
            for arbiter in arbiters:
                arbiter.tick(started)
            elapsed = monotonic_s() - started
            self._thread_stop.wait(max(0.01, self._observe.tick - elapsed))
