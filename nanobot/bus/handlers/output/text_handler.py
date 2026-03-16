"""Text to TTS handler for converting text messages to audio messages."""

import traceback
from io import BytesIO
from typing import Any, Callable, Optional

import numpy as np
from botpy import Type as BotType
from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.handlers.output.output_handler import OutputHandler
from nanobot.config.schema import TextHandlerConfig


class BaseTextHandler(OutputHandler):
    """Base class for text message handlers."""

    @classmethod
    def register(cls, handler_type: str):
        """
        Decorator to register a subclass with a specific handler type.

        Args:
            handler_type: The handler type to register (e.g., "edge_tts", "azure_tts")

        Usage:
            @BaseTextHandler.register("edge_tts")
            class EdgeTTSHanlder(BaseTextHandler):
                pass
        """

        def decorator(subclass: BotType["BaseTextHandler"]) -> BotType["BaseTextHandler"]:
            OutputHandler._registry[f"text.{handler_type}"] = subclass
            return subclass

        return decorator

    @classmethod
    def get_registered_type(cls, handler_type: str) -> BotType["BaseTextHandler"] | None:
        """
        Get a registered handler class by handler type.

        Args:
            handler_type: The handler type to look up

        Returns:
            The registered handler class, or None if not found
        """
        return OutputHandler.get_registered_type("text", handler_type)


class OpusEncoderUtils:
    """PCM到Opus的编码器"""

    def __init__(self, sample_rate: int, channels: int, frame_size_ms: int):
        """
        初始化Opus编码器

        Args:
            sample_rate: 采样率 (Hz)
            channels: 通道数 (1=单声道, 2=立体声)
            frame_size_ms: 帧大小 (毫秒)
        """

        from opuslib_next import Encoder, constants

        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size_ms = frame_size_ms
        # 计算每帧样本数 = 采样率 * 帧大小(毫秒) / 1000
        self.frame_size = (sample_rate * frame_size_ms) // 1000
        # 总帧大小 = 每帧样本数 * 通道数
        self.total_frame_size = self.frame_size * channels

        # 比特率和复杂度设置
        self.bitrate = 24000  # bps
        self.complexity = 10  # 最高质量

        # 缓冲区初始化为空
        self.buffer = np.array([], dtype=np.int16)

        try:
            # 创建Opus编码器
            self.encoder = Encoder(
                sample_rate,
                channels,
                constants.APPLICATION_AUDIO,  # 音频优化模式
            )
            self.encoder.bitrate = self.bitrate
            self.encoder.complexity = self.complexity
            self.encoder.signal = constants.SIGNAL_VOICE  # 语音信号优化
        except Exception as e:
            logger.error(f"初始化Opus编码器失败: {e}")
            raise RuntimeError("初始化失败") from e

    def reset_state(self):
        """重置编码器状态"""
        self.encoder.reset_state()
        self.buffer = np.array([], dtype=np.int16)

    def encode_pcm_to_opus_stream(self, pcm_data: bytes, end_of_stream: bool):
        """
        将PCM数据编码为Opus格式，以流式方式进行处理

        Args:
            pcm_data: PCM字节数据
            end_of_stream: 是否为流的结束,
            callback: opus处理方法

        Returns:
            Opus数据包列表
        """
        # 将字节数据转换为short数组
        new_samples = self._convert_bytes_to_shorts(pcm_data)

        # 校验PCM数据
        self._validate_pcm_data(new_samples)

        # 将新数据追加到缓冲区
        self.buffer = np.append(self.buffer, new_samples)
        offset = 0

        # 处理所有完整帧
        output_datas = []
        while offset <= len(self.buffer) - self.total_frame_size:
            frame = self.buffer[offset : offset + self.total_frame_size]
            output = self._encode(frame)
            if output:
                output_datas.append(output)
            offset += self.total_frame_size

        # 保留未处理的样本
        self.buffer = self.buffer[offset:]

        # 流结束时处理剩余数据
        if end_of_stream and len(self.buffer) > 0:
            # 创建最后一帧并用0填充
            last_frame = np.zeros(self.total_frame_size, dtype=np.int16)
            last_frame[: len(self.buffer)] = self.buffer

            output = self._encode(last_frame)
            if output:
                output_datas.append(output)

            self.buffer = np.array([], dtype=np.int16)
        return output_datas

    def _encode(self, frame: np.ndarray) -> Optional[bytes]:
        """编码一帧音频数据"""
        try:
            # 编码器已释放，跳过编码
            if not hasattr(self, "encoder") or self.encoder is None:
                return None
            # 将numpy数组转换为bytes
            frame_bytes = frame.tobytes()
            # opuslib要求输入字节数必须是channels*2的倍数
            encoded = self.encoder.encode(frame_bytes, self.frame_size)
            return encoded
        except Exception as e:
            logger.error(f"Opus编码失败: {e}")
            traceback.print_exc()
            return None

    def _convert_bytes_to_shorts(self, bytes_data: bytes) -> np.ndarray:
        """将字节数组转换为short数组 (16位PCM)"""
        # 假设输入是小端字节序的16位PCM
        return np.frombuffer(bytes_data, dtype=np.int16)

    def _validate_pcm_data(self, pcm_shorts: np.ndarray) -> None:
        """验证PCM数据是否有效"""
        # 16位PCM数据范围是 -32768 到 32767
        if np.any((pcm_shorts < -32768) | (pcm_shorts > 32767)):
            invalid_samples = pcm_shorts[(pcm_shorts < -32768) | (pcm_shorts > 32767)]
            logger.warning(f"发现无效PCM样本: {invalid_samples[:5]}...")
            # 在实际应用中可以选择裁剪而不是抛出异常
            # np.clip(pcm_shorts, -32768, 32767, out=pcm_shorts)

    def close(self):
        """关闭编码器并释放资源"""
        if hasattr(self, "encoder") and self.encoder:
            try:
                del self.encoder
                self.encoder = None
            except Exception as e:
                logger.error(f"Error releasing Opus encoder: {e}")


@BaseTextHandler.register("edge_tts")
class EdgeTTSHandler(BaseTextHandler):
    """Handler that converts text messages to speech using TTS."""

    def __init__(self, config: TextHandlerConfig | None = None):
        """
        Initialize the TTS handler.

        Args:
            config: TextHandlerConfig containing TTS settings
        """

        try:
            import edge_tts
            import opuslib_next
            import pydub
        except ImportError:
            error_msg = (
                "Init EdgeTTSHandler failed. Install: pip install edge-tts opuslib_next pydub"
            )
            raise ImportError(error_msg)
        self.voice = config.voice
        self.audio_format = config.audio_format
        self.sample_rate = config.sample_rate
        self.encoder_type, self.encoder = config.encoder_type, None
        if self.encoder_type == "opus":
            self.encoder = OpusEncoderUtils(
                sample_rate=self.sample_rate, channels=1, frame_size_ms=60
            )

    def can_handle(self, msg: OutboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The outbound message to check

        Returns:
            True if the message is text type and should be converted to speech
        """
        msg_type = msg.metadata.get("msg_type", "text")
        # Only handle text messages that need TTS conversion
        return msg_type == "text" and msg.metadata.get("need_tts", False)

    async def handle(self, msg: OutboundMessage) -> OutboundMessage:
        """
        Process a text message and convert it to speech.

        Args:
            msg: The outbound message to process

        Returns:
            The processed message with audio data added
        """
        if not msg.content:
            return msg

        try:
            # Generate TTS audio from text
            audio_data = await self._to_tts_stream(msg.content)

            if audio_data:
                # Add audio data to message
                msg.media.append(audio_data)
                # Update message type to indicate it now contains audio
                msg.metadata["msg_type"] = "audio"
                msg.metadata["tts_processed"] = True

        except Exception as e:
            # If TTS fails, keep original text message
            msg.metadata["tts_error"] = str(e)

        return msg

    async def _to_tts_stream(self, text: str) -> bytes | None:
        """
        Convert text to speech audio stream.

        This method references the implementation from:
        /Users/tongmeng/Desktop/codes/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/base.py::to_tts_stream

        Args:
            text: Text content to convert to speech

        Returns:
            Opus encoded audio bytes or None if failed
        """
        # Clean markdown formatting from text
        text, audio_bytes = self._clean_markdown(text), None
        max_repeat_time = 5
        while max_repeat_time > 0:
            try:
                # Get raw audio bytes from TTS
                raw_audio_bytes = await self._text_to_speak(text)
                if not raw_audio_bytes:
                    max_repeat_time -= 1
                    continue

                if self.encoder_type == "opus":
                    # Convert to opus stream
                    opus_datas = self._audio_bytes_to_data_stream(
                        audio_bytes, file_type=self.audio_format, is_opus=True
                    )
                    # Combine all opus frames
                    audio_bytes = b"".join(opus_datas)
                else:
                    audio_bytes = raw_audio_bytes
                if audio_bytes:
                    break
                else:
                    max_repeat_time -= 1
            except Exception as e:
                logger.error(f"TTS conversion error: {e}")
                max_repeat_time -= 1
        return audio_bytes

    async def _text_to_speak(self, text: str) -> bytes | None:
        """
        Convert text to speech audio using Edge TTS.

        Args:
            text: Text to convert
            output_file: Optional file path to save audio (None for in-memory)

        Returns:
            Audio bytes if output_file is None, otherwise None (audio saved to file)
        """
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, voice=self.voice)
            # Return audio binary data
            audio_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes += chunk["data"]
            return audio_bytes

        except ImportError:
            error_msg = "edge-tts not installed. Install with: pip install edge-tts"
            raise ImportError(error_msg)
        except Exception as e:
            error_msg = f"Edge TTS request failed: {e}"
            raise Exception(error_msg)

    def _audio_bytes_to_data_stream(self, audio_bytes, file_type, is_opus) -> None:
        """
        直接用音频二进制数据转为opus/pcm数据，支持wav、mp3、p3
        """

        from pydub import AudioSegment

        audio = AudioSegment.from_file(
            BytesIO(audio_bytes), format=file_type, parameters=["-nostdin"]
        )
        audio = audio.set_channels(1).set_frame_rate(self.sample_rate).set_sample_width(2)
        raw_data = audio.raw_data
        return self._pcm_to_data_stream(raw_data, is_opus)

    def _pcm_to_data_stream(self, raw_data, is_opus=True):
        """
        将PCM数据流式编码为Opus或直接输出PCM

        Args:
            raw_data: PCM原始数据
            is_opus: 是否编码为Opus
            callback: 回调函数
            sample_rate: 采样率
            opus_encoder: OpusEncoderUtils对象(推荐提供以保持编码器状态连续)
        """

        # 编码参数
        frame_duration = 60  # 60ms per frame
        frame_size = int(self.sample_rate * frame_duration / 1000)  # samples/frame

        # 按帧处理所有音频数据（包括最后一帧可能补零）
        output_datas = []
        for i in range(0, len(raw_data), frame_size * 2):  # 16bit=2bytes/sample
            # 获取当前帧的二进制数据
            chunk = raw_data[i : i + frame_size * 2]

            # 如果最后一帧不足，补零
            if len(chunk) < frame_size * 2:
                chunk += b"\x00" * (frame_size * 2 - len(chunk))

            if is_opus:
                # 使用外部编码器（TTS流式场景,保持状态连续）
                is_last = i + frame_size * 2 >= len(raw_data)
                output_datas.extend(
                    self.encoder.encode_pcm_to_opus_stream(chunk, end_of_stream=is_last)
                )
            else:
                # PCM模式,直接输出
                frame_data = chunk if isinstance(chunk, bytes) else bytes(chunk)
                output_datas.append(frame_data)
        return output_datas

    def _clean_markdown(self, text: str) -> str:
        """
        Clean markdown formatting from text.

        References: MarkdownCleaner.clean_markdown from xiaozhi TTS base

        Args:
            text: Text with potential markdown formatting

        Returns:
            Cleaned text without markdown
        """
        import re

        # Remove common markdown patterns
        # Bold: **text** or __text__
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)

        # Italic: *text* or _text_
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)

        # Code: `code`
        text = re.sub(r"`(.+?)`", r"\1", text)

        # Links: [text](url)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)

        # Headers: # text
        text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)

        return text
