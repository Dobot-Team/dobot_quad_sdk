"""Camera state as reported by the robot (`GET http://<ip>:1984/api/streams`).

It answers two questions: is this camera pushing at all and is data still
flowing, and who else is watching (which decides whether closing may stop the
stream).

Limits worth remembering: it only sees watchers that connect through the robot's
video service, it cannot tell who started a stream, it cannot prove that a user
has stopped watching, and a camera missing from the answer means "no
information" rather than "nobody is watching".

No threads here: `VideoStreamManager`'s single supervisor thread calls into this
module periodically.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .types import CAMERA_SPECS, CameraId, ObserveConfig, monotonic_s

__all__ = ["Consumer", "StreamStatus", "StatusProbe", "kDefaultUserAgent"]

kDefaultUserAgent = "DobotQuadSDK/1.3.0"
kProbePath = "/api/streams"


@dataclass(frozen=True)
class Consumer:
    """One watcher of the stream: the phone app, a player, another program."""

    id: str = ""
    remote_addr: str = ""
    user_agent: str = ""
    is_streamer: bool = False

    @property
    def is_app_like(self) -> bool:
        """Whether the user agent looks like the phone app; informational only."""
        ua = self.user_agent.lower()
        return "uni-app" in ua or "webrtc" in ua or "mozilla" in ua

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.remote_addr}({self.user_agent[:24]})" if self.user_agent else self.remote_addr


@dataclass(frozen=True)
class StreamStatus:
    """One camera as seen at one moment.

    ``available=False`` means "no information this time" (the request failed or
    the camera was missing from the answer). That is not the same as "nobody is
    watching", and callers must keep the two apart.
    """

    camera: CameraId
    name: str = ""
    producers: Tuple[dict, ...] = ()
    consumers: Tuple[Consumer, ...] = ()
    bytes_recv: int = 0
    available: bool = False
    error: str = ""
    #: When this snapshot was taken (monotonic seconds); used to avoid counting
    #: the same answer twice.
    fetched_at: float = field(default_factory=monotonic_s)

    # -- is the stream up / is anybody watching --
    @property
    def has_producer(self) -> bool:
        """Whether the camera is pushing anything."""
        return self.available and len(self.producers) > 0

    @property
    def consumer_count(self) -> int:
        return len(self.consumers)

    @property
    def others_watching(self) -> Optional[bool]:
        """Whether anyone else is watching; ``None`` means unknown.

        The SDK opens no media connection of its own, so every watcher reported
        here belongs to somebody else.
        """
        if not self.available:
            return None
        return len(self.consumers) > 0

    def describe(self) -> str:  # pragma: no cover - display only
        if not self.available:
            return f"{self.name or self.camera.name}: unavailable({self.error or 'no data'})"
        return (
            f"{self.name or self.camera.name}: "
            f"producers={len(self.producers)} consumers={len(self.consumers)} "
            f"bytes_recv={self.bytes_recv}"
        )


@dataclass
class _CacheEntry:
    status: StreamStatus
    fetched_at: float = 0.0


class StatusProbe:
    """Reads the camera state, reusing the last answer for a short while."""

    def __init__(
        self,
        host: str,
        port: int = 1984,
        *,
        timeout: float = 1.0,
        observe: Optional[ObserveConfig] = None,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._timeout = float(timeout)
        self._observe = observe or ObserveConfig()
        self._cache: Dict[CameraId, _CacheEntry] = {}
        self._last_error = ""
        #: Injection point for tests: ``(url, timeout) -> (body_or_None, error)``
        self._fetch_override = None

    # ------------------------------------------------------------ configuration
    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}{kProbePath}"

    # ------------------------------------------------------------ sampling
    def status(self, camera: CameraId, *, force: bool = False) -> StreamStatus:
        """Snapshot of one camera.

        Args:
            camera: which camera.
            force: ask now, ignoring the cache (used while starting up or
                recovering).
        """
        now = monotonic_s()
        cached = self._cache.get(camera)
        ttl = self._observe.prepare_poll if force else self._observe.sample_interval
        if cached is not None and not force and (now - cached.fetched_at) < ttl:
            return cached.status

        allow_cache_on_failure = cached is not None and not force
        status = self._fetch_one(camera)
        if not status.available and allow_cache_on_failure:
            # one failed answer is not proof: reuse the previous one for a while
            if (now - cached.fetched_at) < max(ttl * 2, 3.0):
                return cached.status
        self._cache[camera] = _CacheEntry(status=status, fetched_at=now)
        return status

    def snapshot(self, *, force: bool = False) -> Dict[CameraId, StreamStatus]:
        """Snapshots of every camera. Closing always looks at all of them."""
        return {cam: self.status(cam, force=force) for cam in CAMERA_SPECS}

    def all_watching(self, *, samples: int = 2, interval: float = 0.3) -> Optional[bool]:
        """Whether anyone else is watching any camera.

        Returns ``True`` when at least one camera has another watcher, ``False``
        when none has, and ``None`` when that cannot be established - which is
        never a reason to stop a stream.

        ``samples`` fresh samples in a row must agree, because watchers come and
        go asynchronously.
        """
        import time as _time

        result = result_seen = None
        for i in range(max(1, samples)):
            if i:
                _time.sleep(interval)
            seen = False
            unknown = False
            for status in self.snapshot(force=True).values():
                watching = status.others_watching
                if watching is None:
                    unknown = True
                elif watching:
                    seen = True
            result_seen = None if unknown else seen
            if result is None:
                result = result_seen
            elif result != result_seen:
                # samples disagree: keep the "there may be a watcher" answer
                return True if (result or result_seen) else None
        return result

    def invalidate(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------ internals
    def _fetch_one(self, camera: CameraId) -> StreamStatus:
        name = CAMERA_SPECS[camera].rtsp_name
        body, error = self._request()
        if body is None:
            self._last_error = error
            return StreamStatus(camera=camera, name=name, available=False, error=error or "unreachable")
        try:
            data = json.loads(body)
        except (ValueError, TypeError) as exc:
            self._last_error = f"invalid json: {exc}"
            return StreamStatus(camera=camera, name=name, available=False, error=self._last_error)
        if not isinstance(data, dict):
            return StreamStatus(camera=camera, name=name, available=False, error="unexpected body")

        entry = data.get(name)
        if entry is None:
            # camera missing from the answer: unknown, not "nobody watching"
            return StreamStatus(
                camera=camera, name=name, available=False,
                error="stream not present in go2rtc response",
            )
        if not isinstance(entry, dict):
            return StreamStatus(camera=camera, name=name, available=False, error="invalid stream entry")

        producers = tuple(p for p in entry.get("producers") or [] if isinstance(p, dict))
        consumers = tuple(self._parse_consumer(c) for c in entry.get("consumers") or [] if isinstance(c, dict))
        return StreamStatus(
            camera=camera,
            name=name,
            producers=producers,
            consumers=consumers,
            bytes_recv=self._sum_bytes(producers),
            available=True,
        )

    @staticmethod
    def _sum_bytes(producers: Tuple[dict, ...]) -> int:
        total = 0
        for p in producers:
            try:
                total += int(p.get("bytes_recv") or 0)
            except (TypeError, ValueError):
                continue
        return total

    @staticmethod
    def _parse_consumer(raw: dict) -> Consumer:
        return Consumer(
            id=str(raw.get("id") or ""),
            remote_addr=str(raw.get("remote_addr") or raw.get("addr") or ""),
            user_agent=str(raw.get("user_agent") or ""),
            is_streamer=bool(raw.get("is_streamer") or False),
        )

    def _request(self) -> Tuple[Optional[str], str]:
        if self._fetch_override is not None:
            return self._fetch_override(self.url, self._timeout)
        try:
            request = urllib.request.Request(self.url, headers={"User-Agent": kDefaultUserAgent})
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:  # noqa: S310
                raw = resp.read()
            if not raw:
                return None, "empty response"
            return raw.decode("utf-8", errors="replace"), ""
        except urllib.error.HTTPError as exc:  # pragma: no cover - needs a real network
            return None, f"http {exc.code}"
        except (urllib.error.URLError, socket.timeout, OSError, ValueError) as exc:  # pragma: no cover
            return None, str(exc) or exc.__class__.__name__
