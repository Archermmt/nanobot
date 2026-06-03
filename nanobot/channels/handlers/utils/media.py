"""Media file processing utility functions"""

import base64
import io
import os
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import numpy as np
from loguru import logger


def get_mime_type(file_path: str) -> str:
    """Get MIME type based on file extension (generic)."""
    ext = Path(file_path).suffix.lower()

    # Image types
    image_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }

    # Video types
    video_types = {
        ".mp4": "video/mp4",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
    }

    # Audio types
    audio_types = {
        ".mp3": "audio/mp3",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".wma": "audio/x-ms-wma",
    }

    # HTML type
    html_types = {
        ".html": "text/html",
        ".htm": "text/htm",
    }

    # Mesh types
    mesh_types = {
        ".stl": "mesh/stl",
        ".3mf": "mesh/3mf",
        ".obj": "mesh/obj",
        ".fbx": "mesh/fbx",
    }

    all_types = {**image_types, **video_types, **audio_types, **html_types, **mesh_types}
    return all_types.get(ext, "application/octet-stream")


def opus_to_wav(opus_data, sample_rate: int = 16000):
    """Convert Opus data to WAV format byte stream

    Args:
        output_dir: Output directory (kept for interface compatibility)
        opus_data: Opus audio data

    Returns:
        bytes: WAV format audio data
    """

    import opuslib_next

    decoder = None
    try:
        decoder = opuslib_next.Decoder(sample_rate, 1)  # 16kHz, 单声道
        pcm_data = []

        for opus_packet in opus_data:
            pcm_frame = decoder.decode(opus_packet, 960)  # 960 samples = 60ms
            pcm_data.append(pcm_frame)

        if not pcm_data:
            raise ValueError("No valid PCM data")

        # 创建WAV文件头
        pcm_data_bytes = b"".join(pcm_data)

        # WAV文件头
        wav_header = bytearray()
        wav_header.extend(b"RIFF")  # ChunkID
        wav_header.extend((36 + len(pcm_data_bytes)).to_bytes(4, "little"))  # ChunkSize
        wav_header.extend(b"WAVE")  # Format
        wav_header.extend(b"fmt ")  # Subchunk1ID
        wav_header.extend((16).to_bytes(4, "little"))  # Subchunk1Size
        wav_header.extend((1).to_bytes(2, "little"))  # AudioFormat (PCM)
        wav_header.extend((1).to_bytes(2, "little"))  # NumChannels
        wav_header.extend((16000).to_bytes(4, "little"))  # SampleRate
        wav_header.extend((32000).to_bytes(4, "little"))  # ByteRate
        wav_header.extend((2).to_bytes(2, "little"))  # BlockAlign
        wav_header.extend((16).to_bytes(2, "little"))  # BitsPerSample
        wav_header.extend(b"data")  # Subchunk2ID
        wav_header.extend(len(pcm_data_bytes).to_bytes(4, "little"))  # Subchunk2Size

        # 返回完整的WAV数据
        return bytes(wav_header) + pcm_data_bytes
    finally:
        if decoder is not None:
            try:
                del decoder
            except Exception:
                pass


def pcm_to_wav(
    pcm_data: bytes | list[bytes], output_file: Path = None, sample_rate: int = 16000
) -> bytes | Path | None:
    """
    Convert PCM data to WAV format.

    Args:
        pcm_data: PCM audio data bytes or list of bytes (decoded from opus)
        output_file: Optional output file path. If None, returns bytes.
        sample_rate: Sample rate in Hz (default: 16000)

    Returns:
        bytes if output_file is None, otherwise Path to the output file
    """
    try:
        # Handle list of PCM chunks
        if isinstance(pcm_data, list):
            pcm_data = b"".join(pcm_data)

        # Create WAV header
        wav_header = bytearray()
        wav_header.extend(b"RIFF")  # ChunkID
        wav_header.extend((36 + len(pcm_data)).to_bytes(4, "little"))  # ChunkSize
        wav_header.extend(b"WAVE")  # Format
        wav_header.extend(b"fmt ")  # Subchunk1ID
        wav_header.extend((16).to_bytes(4, "little"))  # Subchunk1Size
        wav_header.extend((1).to_bytes(2, "little"))  # AudioFormat (PCM)
        wav_header.extend((1).to_bytes(2, "little"))  # NumChannels
        wav_header.extend((sample_rate).to_bytes(4, "little"))  # SampleRate
        wav_header.extend((sample_rate * 2).to_bytes(4, "little"))  # ByteRate
        wav_header.extend((2).to_bytes(2, "little"))  # BlockAlign
        wav_header.extend((16).to_bytes(2, "little"))  # BitsPerSample
        wav_header.extend(b"data")  # Subchunk2ID
        wav_header.extend(len(pcm_data).to_bytes(4, "little"))  # Subchunk2Size

        wav_data = bytes(wav_header) + pcm_data

        if output_file:
            output_file.write_bytes(wav_data)
            return output_file
        else:
            return wav_data

    except Exception as e:
        logger.error(f"PCM to WAV conversion error: {e}")
        return None


def webm_to_wav(
    audio_bytes: bytes = None, input_file: Path = None, output_file: Path = None
) -> io.BytesIO | Path | None:
    """
    Convert non-WAV audio to WAV format using ffmpeg.

    Args:
        audio_bytes: Raw audio data bytes (optional if input_file is provided)
        input_file: Path to input audio file (optional if audio_bytes is provided)
        output_file: Path to output WAV file (optional, returns BytesIO if not provided)

    Returns:
        BytesIO object with WAV data, or Path if output_file is specified, or None if conversion fails

    Note:
        Either audio_bytes or input_file must be provided, but not both.
    """
    # Validate input parameters
    if audio_bytes is None and input_file is None:
        raise ValueError("Either audio_bytes or input_file must be provided")
    if audio_bytes is not None and input_file is not None:
        raise ValueError("Cannot provide both audio_bytes and input_file")

    in_path, out_path = None, None
    try:
        # Prepare input file
        if input_file is not None:
            # Use the provided input file directly
            in_path = str(input_file)
        else:
            # Create temporary input file from audio_bytes
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
                tmp_in.write(audio_bytes)
                in_path = tmp_in.name

        # Create temporary output file for WAV
        if output_file:
            out_path = str(output_file)
        else:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
                out_path = tmp_out.name
        # Use ffmpeg to convert to WAV
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                in_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                "-y",
                out_path,
            ],
            capture_output=True,
            check=True,
        )
        if output_file:
            return output_file
        # Read converted WAV file
        with open(out_path, "rb") as f:
            wav_io = io.BytesIO(f.read())
        return wav_io
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        return None
    except Exception:
        return None
    finally:
        # Cleanup temporary files
        if in_path and os.path.exists(in_path):
            os.unlink(in_path)
        if not output_file and out_path and os.path.exists(out_path):
            os.unlink(out_path)


def pcm_to_data_stream(
    raw_data,
    is_opus=True,
    callback: Callable[[Any], Any] = None,
    sample_rate=16000,
    opus_encoder=None,
):
    """
    Stream encode PCM data to Opus or output PCM directly

    Args:
        raw_data: Raw PCM data
        is_opus: Whether to encode as Opus
        callback: Callback function
        sample_rate: Sample rate
        opus_encoder: OpusEncoderUtils object (recommended to maintain encoder state continuity)
    """

    import opuslib_next

    using_temp_encoder = False
    if is_opus and opus_encoder is None:
        encoder = opuslib_next.Encoder(sample_rate, 1, opuslib_next.APPLICATION_AUDIO)
        using_temp_encoder = True

    # Encode parameters
    frame_duration = 60  # 60ms per frame
    frame_size = int(sample_rate * frame_duration / 1000)  # samples/frame

    # Process all audio data by frames (including zero-padding for the last frame)
    for i in range(0, len(raw_data), frame_size * 2):  # 16bit=2bytes/sample
        # Get current frame binary data
        chunk = raw_data[i : i + frame_size * 2]

        # Zero-pad if the last frame is insufficient
        if len(chunk) < frame_size * 2:
            chunk += b"\x00" * (frame_size * 2 - len(chunk))

        if is_opus:
            if using_temp_encoder:
                # Use temporary encoder (only for standalone audio scenarios)
                np_frame = np.frombuffer(chunk, dtype=np.int16)
                frame_data = encoder.encode(np_frame.tobytes(), frame_size)
                callback(frame_data)
            else:
                # Use external encoder (TTS streaming scenario, maintain state continuity)
                is_last = i + frame_size * 2 >= len(raw_data)
                opus_encoder.encode_pcm_to_opus_stream(
                    chunk, end_of_stream=is_last, callback=callback
                )
        else:
            # PCM mode, output directly
            frame_data = chunk if isinstance(chunk, bytes) else bytes(chunk)
            callback(frame_data)


def get_audio_bytes(media_data, audio_format: str = "audio/wav") -> tuple[bytes, str]:
    """
    Extract audio byte data and audio format from various media data formats

    Args:
        media_data: Media data, can be in the following formats:
            - dict: Dictionary containing 'data' key
            - str: Data URI format (data:audio/wav;base64,...) or base64 string
            - bytes: Raw audio byte data
            - str: File path
        audio_format: Default audio format, defaults to "audio/wav"

    Returns:
        tuple[bytes, str]: (audio byte data, audio format)
    """
    # If media is a dict with 'data' key, extract it
    if isinstance(media_data, dict):
        media_data = media_data.get("data", "")

    # Handle data URI format
    if isinstance(media_data, str) and media_data.startswith("data:"):
        header, media_data = media_data.split(",", 1)
        audio_format = header.split(";")[0].replace("data:", "")

    # Read audio data based on type
    if isinstance(media_data, bytes):
        audio_bytes = media_data
    elif os.path.isfile(media_data):
        with open(media_data, "rb") as f:
            audio_bytes = f.read()
    else:
        # Assume it's base64 encoded string
        audio_bytes = base64.b64decode(
            media_data.split(",", 1)[1] if "," in media_data else media_data
        )

    return audio_bytes, audio_format


def audio_bytes_to_data_stream(
    audio_bytes,
    file_type,
    is_opus,
    callback: Callable[[Any], Any],
    sample_rate=16000,
    opus_encoder=None,
) -> None:
    """
    Convert audio binary data directly to opus/pcm data, supporting wav, mp3, p3
    """

    from pydub import AudioSegment

    audio = AudioSegment.from_file(BytesIO(audio_bytes), format=file_type, parameters=["-nostdin"])
    audio = audio.set_channels(1).set_frame_rate(sample_rate).set_sample_width(2)
    raw_data = audio.raw_data
    pcm_to_data_stream(raw_data, is_opus, callback, sample_rate, opus_encoder)
