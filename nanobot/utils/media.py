"""媒体文件处理工具函数"""

import base64
import subprocess
import tempfile
from pathlib import Path

from loguru import logger


def save_media(media_data: str, media_dir: Path, filename: str | None = None) -> tuple[Path, str]:
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
        ext = ext_map.get(mime_type, ".bin")
        # Save to temporary file
        filename = f"media_{ext}"

    file_path = media_dir / filename

    # Handle WebM to WAV conversion for audio files
    if filename.endswith(".webm"):
        # Change file extension from .webm to .wav
        file_path = Path(str(file_path).replace(".webm", ".wav"))
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
            tmp_in.write(file_data)
            tmp_in_path = tmp_in.name

        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                tmp_in_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                "-y",
                str(file_path),
            ],
            capture_output=True,
            check=True,
        )
        # Check if conversion was successful
        if result.returncode != 0:
            logger.error(f"FFmpeg conversion failed: {result.stderr.decode()}")
            raise RuntimeError(f"FFmpeg conversion failed with code {result.returncode}")
        logger.info("Successfully converted audio to WAV format")

        # Clean up temporary file
        try:
            Path(tmp_in_path).unlink()
        except Exception as e:
            logger.warning(f"Failed to clean up temporary file: {e}")
    else:
        file_path.write_bytes(file_data)
    logger.debug("Saved base64 media to {}", file_path)
    return file_path, filename
