#!/usr/bin/env python3
"""
Voice Command Publisher

Supports two modes:
1. file mode: publish local file paths
2. streaming mode: capture audio from microphone in real-time and publish
"""

import sys
import subprocess
import time
import threading
import queue
import dds_middleware_python as dds


class AudioCaptureThread(threading.Thread):
    """Background thread for continuous low-latency audio capture"""

    def __init__(self, chunk_duration_ms=100):
        super().__init__(daemon=True)
        self.chunk_duration_ms = chunk_duration_ms
        self.audio_queue = queue.Queue(maxsize=2)  # Small buffer to avoid lag
        self.running = True

    def run(self):
        """Continuously capture audio chunks from microphone"""
        duration_sec = self.chunk_duration_ms / 1000.0

        try:
            # Start arecord process that will run continuously
            process = subprocess.Popen(
                ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "24000"],
                stdout=subprocess.PIPE,
                bufsize=0  # Unbuffered for lowest latency
            )

            # Calculate bytes per chunk (24kHz, 16bit, mono = 2 bytes per sample)
            bytes_per_chunk = int(24000 * duration_sec * 2)

            while self.running:
                chunk = process.stdout.read(bytes_per_chunk)
                if not chunk:
                    break

                # Drop old chunks if queue is full to maintain real-time performance
                try:
                    self.audio_queue.put_nowait(bytearray(chunk))
                except queue.Full:
                    # Remove oldest chunk and add new one
                    try:
                        self.audio_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self.audio_queue.put_nowait(bytearray(chunk))
                    except queue.Full:
                        pass

        except Exception as e:
            print(f"Audio capture thread error: {e}")
        finally:
            try:
                process.terminate()
            except:
                pass

    def get_audio(self):
        """Get next available audio chunk (non-blocking)"""
        try:
            return self.audio_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        """Stop the capture thread"""
        self.running = False


# def capture_audio_chunk():
#     """
#     Capture ~100ms of PCM audio from microphone using arecord (24kHz, mono, 16bit)
#     """
#     try:
#         # Capture 100ms of audio (shorter duration = less latency)
#         result = subprocess.run(
#             ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "24000", "-d", "0.1"],
#             capture_output=True,
#             timeout=1
#         )
#         return bytearray(result.stdout)
#     except Exception as e:
#         print(f"Microphone capture failed: {e}")
#         return bytearray()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "file"

    # Create DDS middleware instance
    middleware = dds.PyDDSMiddleware(0)

    # Configure QoS
    qos_config = {
        "reliability": "reliable",
        "history_kind": "keep_last",
        "history_depth": 5,
        "durability": "volatile"
    }

    # Create VoiceCmd publisher
    middleware.createVoiceCmdWriter("rt/voice/cmd", qos_config)

    print(f"Mode: {mode}")
    print("QoS: RELIABLE, KEEP_LAST(5), VOLATILE")

    if mode == "file":
        # file_path = "/root/test1.wav"
        file_path = "/root/test2.flac"
        # file_path = "/root/test3.mp3"

        print("File mode: publish local file paths cyclically")
        voice_cmd = dds.VoiceCmd()
        voice_cmd.type("file")
        voice_cmd.path(file_path)
        voice_cmd.data([])
        # sleep 1 second for dds discovery
        time.sleep(1)
        middleware.publishVoiceCmd(voice_cmd)

        print("Published VoiceCmd (file)")
        print(f"  Path: {voice_cmd.path()}")
        print(f"  Data size: 0 bytes")
        print("---------------------------")


    elif mode == "streaming":
        print("Streaming mode: capture and publish from microphone (low-latency)")

        # Start background audio capture thread
        capture_thread = AudioCaptureThread(chunk_duration_ms=100)
        capture_thread.start()

        try:
            while True:
                # Get audio from capture queue (non-blocking)
                audio = capture_thread.get_audio()

                if audio is None:
                    # No audio available, sleep briefly and try again
                    time.sleep(0.01)  # 10ms instead of 200ms
                    continue

                voice_cmd = dds.VoiceCmd()
                voice_cmd.type("streaming")
                voice_cmd.path("")
                voice_cmd.data(list(audio))

                middleware.publishVoiceCmd(voice_cmd)

                print("Published VoiceCmd (streaming)")
                print(f"  Data size: {len(voice_cmd.data())} bytes")
                print("---------------------------")
                # No sleep - publish immediately when audio is available

        except KeyboardInterrupt:
            print("Stopping streaming...")
        finally:
            capture_thread.stop()

    else:
        print("Unknown mode, use 'file' or 'streaming'")


if __name__ == "__main__":
    main()
