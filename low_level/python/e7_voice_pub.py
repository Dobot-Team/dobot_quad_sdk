#!/usr/bin/env python3
"""
Voice Command Publisher

Supports two modes:
1. file mode: publish a local audio file path once
2. streaming mode: capture audio from microphone in real-time and publish
"""

import sys
import subprocess
import time
import threading
import queue
import dds_middleware_python as dds


class AudioCaptureThread(threading.Thread):
    """Background thread for continuous low-latency audio capture (24kHz, mono, 16bit)."""

    def __init__(self, chunk_duration_ms=100):
        super().__init__(daemon=True)
        self.chunk_duration_ms = chunk_duration_ms
        self.audio_queue = queue.Queue(maxsize=2)  # small buffer to avoid lag
        self.running = True

    def run(self):
        process = subprocess.Popen(
            ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "24000"],
            stdout=subprocess.PIPE,
            bufsize=0,  # unbuffered for lowest latency
        )
        # 24kHz * 16bit mono = 2 bytes/sample
        bytes_per_chunk = int(24000 * self.chunk_duration_ms / 1000 * 2)
        try:
            while self.running:
                chunk = process.stdout.read(bytes_per_chunk)
                if not chunk:
                    break
                # Drop the oldest chunk if the queue is full to stay real-time.
                if self.audio_queue.full():
                    self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(bytearray(chunk))
        except Exception as e:
            print(f"Audio capture thread error: {e}")
        finally:
            process.terminate()

    def get_audio(self):
        """Return the next available audio chunk, or None if the queue is empty."""
        try:
            return self.audio_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        self.running = False


def make_header():
    """Build a std_msgs Header stamped with the current time.

    The refactored VoiceCmd (dds-middleware >= 0.23.x) carries a Header,
    matching the canonical voice publisher examples.
    """
    header = dds.Header()
    stamp = dds.Time()
    now = time.time()
    stamp.sec(int(now))
    stamp.nanosec(int((now - int(now)) * 1e9))
    header.stamp(stamp)
    header.frame_id("voice_cmd")
    return header


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "file"

    middleware = dds.PyDDSMiddleware(0)
    qos_config = {
        "reliability": "reliable",
        "history_kind": "keep_last",
        "history_depth": 5,
        "durability": "volatile",
    }
    middleware.createVoiceCmdWriter("rt/voice/cmd", qos_config)

    print(f"Mode: {mode}, QoS: RELIABLE, KEEP_LAST(5), VOLATILE")

    if mode == "file":
        file_path = "/root/test2.flac"

        voice_cmd = dds.VoiceCmd()
        voice_cmd.header(make_header())
        voice_cmd.priority(dds.VoicePriority.kNormal)  # kNormal: ordinary audio file
        voice_cmd.task_id("e7_voice_pub")
        voice_cmd.type("file")
        voice_cmd.path(file_path)
        voice_cmd.data([])
        voice_cmd.flag(False)  # stream-end flag, unused in file mode

        time.sleep(1)  # wait for DDS discovery
        middleware.publishVoiceCmd(voice_cmd)
        print(f"Published VoiceCmd (file): {voice_cmd.path()}")

    elif mode == "streaming":
        print("Streaming mode: capture and publish from microphone (low-latency)")

        capture_thread = AudioCaptureThread(chunk_duration_ms=100)
        capture_thread.start()

        try:
            while True:
                audio = capture_thread.get_audio()
                if audio is None:
                    time.sleep(0.01)
                    continue

                voice_cmd = dds.VoiceCmd()
                voice_cmd.header(make_header())
                voice_cmd.priority(dds.VoicePriority.kNormal)  # kNormal: ordinary audio stream
                voice_cmd.task_id("e7_voice_pub")
                voice_cmd.type("streaming")
                voice_cmd.path("")
                voice_cmd.data(list(audio))
                voice_cmd.flag(False)  # False: stream not finished yet

                middleware.publishVoiceCmd(voice_cmd)
                print(f"Published VoiceCmd (streaming): {len(voice_cmd.data())} bytes")

        except KeyboardInterrupt:
            print("Stopping streaming...")
        finally:
            capture_thread.stop()

    else:
        print("Unknown mode, use 'file' or 'streaming'")


if __name__ == "__main__":
    main()
