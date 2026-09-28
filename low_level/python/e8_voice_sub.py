"""
VoiceState Subscription and Recording Example (E8)

Subscribe to the robot's microphone audio stream (rt/voice/state) and save it
as a WAV file (PCM 16bit, 24000Hz, mono) for playback or analysis.

Usage:
  python e8_voice_sub.py                                    # Save to voice_capture.wav
  python e8_voice_sub.py /tmp/output.wav                     # Custom output path
  python e8_voice_sub.py --no-save                           # Only print, don't save
"""

import sys
import time
import wave

import dds_middleware_python as dds

RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16bit

CONFIG_FILE = "config/dds_config.yaml"
TOPIC_NAME = "rt/voice/state"
DEFAULT_OUTPUT = "voice_capture.wav"

QOS_CONFIG = {
    "reliability": "best_effort",
    "history_kind": "keep_last",
    "history_depth": 1,
    "durability": "volatile",
}


def main():
    output_path = DEFAULT_OUTPUT
    save_to_file = True

    for arg in sys.argv[1:]:
        if arg == "--no-save":
            save_to_file = False
        elif not arg.startswith("--"):
            output_path = arg

    wav_writer = None
    if save_to_file:
        wav_writer = wave.open(output_path, "wb")
        wav_writer.setnchannels(CHANNELS)
        wav_writer.setsampwidth(SAMPLE_WIDTH)
        wav_writer.setframerate(RATE)
        print(f"Recording to: {output_path}")

    def voice_state_callback(voice_state_msg):
        data = voice_state_msg.data_()
        print(f"Received VoiceState: {len(data)} bytes, angle={voice_state_msg.angle_():.1f} deg")

        if wav_writer and data:
            wav_writer.writeframes(bytearray(data))

    middleware = dds.PyDDSMiddleware(CONFIG_FILE)

    print(f"Subscribing to topic: {TOPIC_NAME}")
    middleware.subscribeVoiceState(TOPIC_NAME, voice_state_callback, QOS_CONFIG)

    print("VoiceState subscriber started. Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if wav_writer:
            wav_writer.close()
            print(f"Saved audio to: {output_path}")


if __name__ == "__main__":
    main()
