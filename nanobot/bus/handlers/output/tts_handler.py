"""Text to TTS handler for converting text messages to audio messages."""

import os
from pathlib import Path

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.handlers.output.output_handler import OutputHandler
from nanobot.config.schema import TTSHandlerConfig
from nanobot.utils.media import audio_bytes_to_data_stream


class BaseTTSHandler(OutputHandler):
    """Base class for text-to-speech message handlers."""

    @classmethod
    def msg_type(cls) -> str:
        return "text"


@BaseTTSHandler.register()
class EdgeTTSHandler(BaseTTSHandler):
    """Handler that converts text messages to speech using TTS."""

    @classmethod
    def handler_type(cls) -> str:
        return "edge_tts"

    def __init__(self, config: TTSHandlerConfig | None = None):
        """
        Initialize the TTS handler.

        Args:
            config: TTSHandlerConfig containing TTS settings
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
        # Expand ~ to home directory and convert to absolute path
        self.output_dir = Path(config.output_dir).expanduser().resolve()
        if self.encoder_type == "opus":
            self.encoder = opuslib_next.Encoder(self.sample_rate, 1, opuslib_next.APPLICATION_AUDIO)

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
        return (
            msg_type == "text"
            and msg.metadata.get("need_tts", False)
            and not msg.metadata.get("_progress", False)
        )

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
            audio_datas = await self._to_tts_datas(msg.content)
            if audio_datas:
                # Add audio data to message
                msg.media.extend(audio_datas)
                # Update message type to indicate it now contains audio
                msg.metadata["msg_type"] = "audio"
                msg.metadata.pop("need_tts")
        except Exception as e:
            # If TTS fails, keep original text message
            msg.metadata["tts_error"] = str(e)

        return msg

    async def _to_tts_datas(self, text: str) -> bytes | None:
        """
        Convert text to speech audio stream.

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
                audio_bytes = await self._text_to_speak(text, None)
                if not audio_bytes:
                    max_repeat_time -= 1
                    continue
                if self.encoder_type == "opus":
                    audio_datas = []
                    audio_bytes_to_data_stream(
                        audio_bytes,
                        file_type=self.audio_format,
                        is_opus=True,
                        callback=lambda data: audio_datas.append(data),
                        sample_rate=self.sample_rate,
                    )
                    return audio_datas
                return [audio_bytes]
            except Exception as e:
                logger.error(f"TTS conversion error: {e}")
                max_repeat_time -= 1
        return audio_bytes

    async def _text_to_speak(self, text, output_file):
        import edge_tts

        try:
            communicate = edge_tts.Communicate(text, voice=self.voice)
            if output_file:
                # 确保目录存在并创建空文件
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "wb") as f:
                    pass

                # 流式写入音频数据
                with open(output_file, "ab") as f:  # 改为追加模式避免覆盖
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":  # 只处理音频数据块
                            f.write(chunk["data"])
            else:
                # 返回音频二进制数据
                audio_bytes = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes += chunk["data"]
                return audio_bytes
        except Exception as e:
            error_msg = f"Edge TTS请求失败: {e}"
            raise Exception(error_msg)  # 抛出异常，让调用方捕获

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
