"""e12_video_stream.py - get an RTSP address and hand it to your own player.

The SDK switches the stream on, watches it and returns an address. Pulling,
decoding and muxing are up to your own player or vision code.

Usage::

    python examples/e12_video_stream.py                    # 192.168.5.2:50051
    python examples/e12_video_stream.py 10.30.12.4:50051 --camera rear
    python examples/e12_video_stream.py --pull             # also pull it with ffmpeg
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dobot_quad import CameraId, RobotClient  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="robot.video example")
    parser.add_argument("address", nargs="?", default="192.168.5.2:50051", help="ip[:port]")
    parser.add_argument("--camera", choices=["front", "rear"], default="front")
    parser.add_argument("--seconds", type=float, default=6.0, help="seconds to watch")
    parser.add_argument("--pull", action="store_true", help="also pull the address with ffmpeg")
    return parser.parse_args()


def pull_once(uri: str, seconds: float) -> bool:
    """Opens the address with an external player: media handling is outside the SDK."""
    if not shutil_which("ffprobe") and not shutil_which("ffplay"):
        print("[pull] no ffprobe / ffplay found; open the address with your own player")
        return False
    if shutil_which("ffprobe"):
        command = [
            "ffprobe", "-v", "error", "-rtsp_transport", "tcp",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height",
            "-of", "default=nw=1", uri,
        ]
    else:  # pragma: no cover - depends on this machine
        command = [
            "ffplay", "-hide_banner", "-rtsp_transport", "tcp", "-fflags", "nobuffer",
            "-flags", "low_delay", "-framedrop", "-autoexit", "-t", str(int(seconds)), uri,
        ]
    print(f"[pull] $ {' '.join(command)}")
    return subprocess.run(command, timeout=seconds + 20).returncode == 0


def shutil_which(name: str) -> str:
    from shutil import which

    return which(name)


def main() -> int:
    args = parse_args()
    camera = CameraId.FRONT_RGB if args.camera == "front" else CameraId.REAR_RGB

    robot = RobotClient(args.address)
    video = robot.video

    # Stream events: drops, stops from outside this program, recoveries.
    unsubscribe = video.on_state_change(
        lambda event: print(f"[state] {event.camera.name} {event}")  # noqa: B023
    )

    print("=== cameras:", ", ".join(c.name for c in video.list_cameras()), "===")
    print(f"=== open({camera.name}) (blocks until data is flowing) ===")

    started = time.monotonic()
    try:
        uri = video.open(camera)
    except Exception as exc:  # noqa: BLE001 - show the message as it is
        print(f"[error] {exc}")
        return 1
    print(f"open() took {time.monotonic() - started:.2f}s")
    print("RTSP address:", uri)
    print("State:", video.get_stream_info(camera))

    if args.pull:
        pull_once(uri, args.seconds)
    else:
        print("Open the address with your own player, for example")
        print(f"  ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay {uri}")

    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        time.sleep(1.0)
        info = video.get_stream_info(camera)
        bitrate = f"{info.bitrate_kbps:.0f} kbps" if info.bitrate_kbps else "n/a"
        print(f"[watch] state={info.state.value} owner={info.owner.value} bitrate={bitrate}")

    unsubscribe()

    # close() checks whether anyone else is watching before stopping anything.
    video.close(camera)
    print("State after close():", video.get_stream_info(camera))
    robot.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
