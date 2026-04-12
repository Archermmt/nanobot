"""Audio encode handler for encoding audio data to various formats."""

from abc import abstractmethod

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.handlers.base_handler import BaseHandler
from nanobot.config.schema import AudioEncodeHandlerConfig
from nanobot.utils.log import CaptureOutput
from nanobot.utils.media import audio_bytes_to_data_stream, get_audio_bytes


class BaseAudioEncodeHandler(BaseHandler):
    """Base class for audio encoding handlers."""

    @classmethod
    def handler_type(cls) -> str:
        return "audio_encode"

    def __init__(self, config: AudioEncodeHandlerConfig | None = None):
        """
        Initialize the base audio encode handler.

        Args:
            config: AudioEncodeHandlerConfig containing audio encoding settings
        """
        self.sample_rate = config.sample_rate if config else 16000

    def can_handle_output(self, msg: OutboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The outbound message to check

        Returns:
            True if the message contains audio data that needs encoding
        """
        msg_type = msg.metadata.get("msg_type", "")
        return msg_type == "audio" and not msg.metadata.get("encoder_type")

    async def handle_output(self, msg: OutboundMessage) -> OutboundMessage:
        """
        Process an outbound message and encode audio data.

        Args:
            msg: The outbound message to process

        Returns:
            The processed message with encoded audio data
        """
        if not msg.media:
            return msg

        try:
            audio_format = msg.metadata.get("file_type", "audio/wav")
            audio_bytes, audio_format = get_audio_bytes(msg.media[0], audio_format)
            with CaptureOutput():
                encode_bytes, info = await self._encode_audio(audio_bytes, audio_format)
            if encode_bytes:
                msg.media = encode_bytes
                msg.metadata.update(info)
            else:
                msg.content = "Failed to encode audio"
                msg.metadata["_warning_msg"] = "audio_encode_failed"
        except Exception as e:
            logger.error(f"Audio encoding error: {e}")
            msg.content = "Failed to encode audio: " + str(e)
            msg.metadata["_warning_msg"] = "audio_encode_failed"

        return msg

    @abstractmethod
    async def _encode_audio(
        self, audio_bytes: bytes, audio_format: str
    ) -> tuple[bytes | None, dict]:
        """
        Encode audio bytes to target format. To be implemented by subclasses.

        Args:
            audio_bytes: Raw audio bytes in various formats (wav, mp3, etc.)
            audio_format: Audio format string (e.g., 'audio/wav', 'audio/mp3')

        Returns:
            Tuple of (encoded bytes or None, metadata dict)
        """
        pass


@BaseAudioEncodeHandler.register()
class OpusAudioEncodeHandler(BaseAudioEncodeHandler):
    """Handler that encodes audio data to Opus format."""

    @classmethod
    def handler_type(cls) -> str:
        return "opus_encode"

    def __init__(self, config: AudioEncodeHandlerConfig | None = None):
        """
        Initialize the Opus audio encode handler.

        Args:
            config: AudioEncodeHandlerConfig containing audio encoding settings
        """
        try:
            import opuslib_next
            import pydub
        except ImportError:
            error_msg = (
                "Init OpusAudioEncodeHandler failed. Install: pip install opuslib_next pydub"
            )
            raise ImportError(error_msg)

        super().__init__(config)
        self.encoder = opuslib_next.Encoder(self.sample_rate, 1, opuslib_next.APPLICATION_AUDIO)

    async def _encode_audio(
        self, audio_bytes: bytes, audio_format: str
    ) -> tuple[bytes | None, dict]:
        """
        Encode audio bytes to Opus frames.

        Args:
            audio_bytes: Raw audio bytes in various formats (wav, mp3, etc.)
            audio_format: Audio format string (e.g., 'audio/wav', 'audio/mp3')

        Returns:
            Tuple of (encoded bytes or None, metadata dict)
        """

        audio_datas = []
        audio_format = audio_format.split("audio/")[-1]
        audio_bytes_to_data_stream(
            audio_bytes,
            file_type=audio_format,
            is_opus=True,
            callback=lambda data: audio_datas.append(data),
            sample_rate=self.sample_rate,
        )
        return audio_datas, {"encoder_type": "opus", "frame_duration": 60}
