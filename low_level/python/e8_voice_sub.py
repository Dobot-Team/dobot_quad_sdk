"""
VoiceState Subscription and Saving Example (e9)

Functionality: Subscribe to `rt/voice/state` topic and continuously write received
audio stream as PCM 16bit/24000Hz/mono to a WAV file for playback or analysis.

Usage:
- Default save to voice_state_capture.wav:   python e9_voice_sub.py
- Specify output file path:                   python e9_voice_sub.py /tmp/out.wav
"""

import sys
import time
import wave
from pathlib import Path
from queue import Queue

import dds_middleware_python as dds


RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16bit
CONFIG_FILE = "config/dds_config.yaml"
TOPIC_NAME = "rt/voice/state"
qos_config = {
    "reliability": "best_effort",  # Best effort delivery
    "history_kind": "keep_last",  # Keep last N messages
    "history_depth": 1,  # Keep 1 historical message
    "durability": "volatile"  # Local persistence
}


def main():

    def _voice_state_callback(voice_state_msg):
        """
        VoiceState message callback function, called when a VoiceState message is received
        """
        print(f"Received VoiceState message:")
        print(f"  Data size: {len(voice_state_msg.data_())} bytes")
        print(f"  Angle: {voice_state_msg.angle_():.2f} degrees")
        print("---")

    middleware = dds.PyDDSMiddleware(CONFIG_FILE)

    print("Starting DDS Python VoiceState subscriber...")
    # Subscribe to VoiceState topic
    topic_name = "rt/voice/state"
    print(f"Subscribing to topic: {topic_name}")
    # Subscribe to VoiceState topic and register callback function with QoS config
    middleware.subscribeVoiceState(topic_name, _voice_state_callback, qos_config)

    print("VoiceState subscriber started, waiting for voice state messages...")
    print("Press Ctrl+C to exit")

    # Keep the program running to receive messages
    while True:
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
