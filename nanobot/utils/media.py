"""媒体文件处理工具函数"""

import base64
import io
import os
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from loguru import logger


def opus_to_wav(opus_data, sample_rate: int = 16000):
    """将Opus数据转换为WAV格式的字节流

    Args:
        output_dir: 输出目录（保留参数以保持接口兼容）
        opus_data: opus音频数据

    Returns:
        bytes: WAV格式的音频数据
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
            raise ValueError("没有有效的PCM数据")

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
            except Exception as e:
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


def webm_to_wav(audio_bytes: bytes, output_file: Path = None) -> io.BytesIO | Path | None:
    """
    Convert non-WAV audio to WAV format using ffmpeg.

    Args:
        audio_bytes: Raw audio data bytes

    Returns:
        BytesIO object with WAV data, or None if conversion fails
    """

    in_path, out_path = None, None
    try:
        # Create temporary input file
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
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg conversion failed: {e.stderr.decode() if e.stderr else e}")
        return None
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install ffmpeg to convert non-WAV audio.")
        return None
    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        return None
    finally:
        # Cleanup temporary files
        if in_path and os.path.exists(in_path):
            os.unlink(in_path)
        if not output_file and out_path and os.path.exists(out_path):
            os.unlink(out_path)


def save_media(
    media_data: str,
    filename: str | None = None,
    media_dir: Path | None = None,
    target_type: str = "",
) -> tuple[Path, str]:
    """
    保存媒体文件到指定目录

    Args:
        media_data: Base64 编码的媒体数据（包含 data URI 前缀）
        media_dir: 保存文件的目录路径
        filename: 文件名，如果为 None 则自动生成

    Returns:
        tuple[Path, str]: (文件路径，MIME 类型)
    """

    # Parse data URI
    header, b64_data = media_data.split(",", 1)
    mime_type = header.split(";")[0].replace("data:", "")

    if not media_dir:
        media_dir = Path.home() / ".nanobot" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

    # Decode base64
    file_data = base64.b64decode(b64_data)

    if not filename:
        # Determine file extension from mime type
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "audio/webm": ".webm",
            "audio/mp3": ".mp3",
            "audio/aac": ".aac",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
            "video/mp4": ".mp4",
        }
        if target_type:
            ext = ext_map.get(target_type, ".bin")
        else:
            ext = ext_map.get(mime_type, ".bin")
        # Save to temporary file
        filename = f"media_{ext}"

    file_path = media_dir / filename
    if mime_type == "audio/webm" and target_type == "audio/wav":
        file_path = webm_to_wav(file_data, file_path)
    else:
        file_path.write_bytes(file_data)
    logger.debug("Saved base64 media to {}", file_path)
    return file_path, filename


def pcm_to_data_stream(
    raw_data,
    is_opus=True,
    callback: Callable[[Any], Any] = None,
    sample_rate=16000,
    opus_encoder=None,
):
    """
    将PCM数据流式编码为Opus或直接输出PCM

    Args:
        raw_data: PCM原始数据
        is_opus: 是否编码为Opus
        callback: 回调函数
        sample_rate: 采样率
        opus_encoder: OpusEncoderUtils对象(推荐提供以保持编码器状态连续)
    """

    import opuslib_next

    using_temp_encoder = False
    if is_opus and opus_encoder is None:
        encoder = opuslib_next.Encoder(sample_rate, 1, opuslib_next.APPLICATION_AUDIO)
        using_temp_encoder = True

    # 编码参数
    frame_duration = 60  # 60ms per frame
    frame_size = int(sample_rate * frame_duration / 1000)  # samples/frame

    # 按帧处理所有音频数据（包括最后一帧可能补零）
    for i in range(0, len(raw_data), frame_size * 2):  # 16bit=2bytes/sample
        # 获取当前帧的二进制数据
        chunk = raw_data[i : i + frame_size * 2]

        # 如果最后一帧不足，补零
        if len(chunk) < frame_size * 2:
            chunk += b"\x00" * (frame_size * 2 - len(chunk))

        if is_opus:
            if using_temp_encoder:
                # 使用临时编码器（仅用于独立音频场景）
                np_frame = np.frombuffer(chunk, dtype=np.int16)
                frame_data = encoder.encode(np_frame.tobytes(), frame_size)
                callback(frame_data)
            else:
                # 使用外部编码器（TTS流式场景,保持状态连续）
                is_last = i + frame_size * 2 >= len(raw_data)
                opus_encoder.encode_pcm_to_opus_stream(
                    chunk, end_of_stream=is_last, callback=callback
                )
        else:
            # PCM模式,直接输出
            frame_data = chunk if isinstance(chunk, bytes) else bytes(chunk)
            callback(frame_data)


def audio_bytes_to_data_stream(
    audio_bytes,
    file_type,
    is_opus,
    callback: Callable[[Any], Any],
    sample_rate=16000,
    opus_encoder=None,
) -> None:
    """
    直接用音频二进制数据转为opus/pcm数据，支持wav、mp3、p3
    """

    from pydub import AudioSegment

    audio = AudioSegment.from_file(BytesIO(audio_bytes), format=file_type, parameters=["-nostdin"])
    audio = audio.set_channels(1).set_frame_rate(sample_rate).set_sample_width(2)
    raw_data = audio.raw_data
    pcm_to_data_stream(raw_data, is_opus, callback, sample_rate, opus_encoder)
