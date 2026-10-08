"""Streaming switch on the robot (HTTP ``:22000``).

* ``POST /settings/streaming/start`` is idempotent: starting a stream that is
  already running does not disturb whoever is watching it.
* The switch cannot be queried, so "is anything being pushed right now?" is
  answered by the camera state endpoint (see :mod:`.probe`).
* A ``200`` answer does not mean data is flowing: callers must check the pushed
  byte counts reported by the camera state endpoint.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from typing import Optional

from .types import VideoConnectionError, VideoTimeoutError


__all__ = ["StreamingController"]


class StreamingController:
    """Sends the start / stop command to the robot.

    The class holds no shared state - one connection per call - so it is safe to
    call from several threads.
    """

    def __init__(self, host: str, port: int = 22000, timeout: float = 2.0) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)

    # -----------------------------------------------------------------

    def start(self) -> None:
        """Starts pushing this robot's camera streams (idempotent).

        Raises:
            VideoConnectionError: the robot cannot be reached.
            VideoTimeoutError: the robot did not answer in time.
            VideoError: the robot answered with an error status.
        """
        self._post("start")

    def stop(self) -> None:
        """Stops pushing the robot's camera streams (idempotent).

        Note:
            The switch is global: both cameras stop.
        """
        self._post("stop")

    def reachable(self, timeout: Optional[float] = None) -> bool:
        """Whether the switch port accepts a TCP connection.

        A quick "can I reach the robot" check, used to tell a network problem
        apart from a camera problem.
        """
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=timeout or min(self.timeout, 1.0)
            ):
                return True
        except OSError:
            return False

    # -----------------------------------------------------------------

    def _post(self, action: str) -> dict:
        url = f"http://{self.host}:{self.port}/settings/streaming/{action}"
        body = json.dumps({}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise VideoConnectionError(
                f"Failed to {action} the stream: HTTP {exc.code} from "
                f"{self.host}:{self.port}"
            ) from exc
        except socket.timeout as exc:
            raise VideoTimeoutError(
                f"Timed out after {self.timeout}s while trying to {action} the stream on "
                f"{self.host}:{self.port}"
            ) from exc
        except urllib.error.URLError as exc:
            raise VideoConnectionError(
                f"Cannot reach the streaming service at {self.host}:{self.port} "
                f"({exc.reason}). Check that this host and the robot are on the same "
                "network."
            ) from exc
        except OSError as exc:
            raise VideoConnectionError(
                f"Cannot reach the streaming service at {self.host}:{self.port} ({exc})"
            ) from exc

        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            return {}
