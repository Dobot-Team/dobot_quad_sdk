#!/usr/bin/env python3

import sys
import wave
from pathlib import Path
from pydub import AudioSegment


def convert_audio(input_file: str, output_file: str) -> None:
    # Detect input format from file extension
    input_path = Path(input_file)
    input_ext = input_path.suffix.lower().lstrip('.')

    supported_formats = ['wav', 'mp3', 'flac', 'ogg']

    if input_ext not in supported_formats:
        print(
            f"Error: Unsupported input format '{input_ext}'. Supported: {', '.join(supported_formats)}"
        )
        return

    print(f"Loading {input_ext.upper()} file...")
    audio = AudioSegment.from_file(input_file, format=input_ext)

    # Convert to target format: 24kHz, mono
    audio = audio.set_frame_rate(24000)
    audio = audio.set_channels(1)

    # Export as WAV with PCM s16le format
    audio.export(
        output_file, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1"]
    )

    # Verify output file exists
    if Path(output_file).exists():
        print(f"Conversion successful: {output_file}")

        # Verify format
        with wave.open(output_file, 'rb') as wav_file:
            if (
                wav_file.getframerate() == 24000 and wav_file.getnchannels() == 1
                and wav_file.getsampwidth() == 2
            ):  # 16-bit = 2 bytes
                print("Format verified: 24kHz, mono, 16-bit PCM")
            else:
                print("Warning: Output format does not match target specifications")
    else:
        print("Error: Output file not created")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python audio_file_convert.py <input_file> <output.wav>")
        print("Supported input formats: WAV, MP3, FLAC, OGG")
        print("Output format: WAV (24kHz, mono, 16-bit PCM)")
        sys.exit(1)

    convert_audio(sys.argv[1], sys.argv[2])
