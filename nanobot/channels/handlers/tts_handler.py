"""Text to TTS handler for converting text messages to audio messages."""

import base64
import io
import json
import time
import wave
from pathlib import Path

import numpy as np
from loguru import logger

from nanobot.channels.handlers.base_handler import BaseHandler, HandlerMessage
from nanobot.channels.handlers.utils.log import CaptureOutput
from nanobot.channels.handlers.utils.text_utils import check_emoji, clean_markdown
from nanobot.config.schema import Base


class TTSHandlerConfig(Base):
    """Configuration for TTS (Text-to-Speech) handler."""

    enabled: bool = False
    handler_type: str = "edge_tts"
    depends_folder: str = "~/.nanobot/depends/tts"  # Depends folder for voice configuration
    model: str | None = None  # Model name for TTS service (e.g., cosyvoice-v3.5-plus for Qwen TTS)
    voice: str = "zh-CN-XiaoxiaoNeural"
    audio_format: str = "opus"  # Edge TTS returns mp3 format
    sample_rate: int = 16000


class BaseTTSHandler(BaseHandler):
    """Base class for text-to-speech message handlers."""

    name = "tts"
    config_cls = TTSHandlerConfig

    def __init__(self, config: TTSHandlerConfig | None = None):
        """
        Initialize the TTS handler.

        Args:
            config: TTSHandlerConfig containing TTS settings
        """

        self.voice, self.audio_format = config.voice, config.audio_format
        self.sample_rate = config.sample_rate
        # get voice config
        self.depends_folder = Path(config.depends_folder).expanduser()
        voice_path = self.depends_folder / "voice.json"
        assert voice_path.exists(), f"Voice configuration not found: {voice_path}"
        with open(voice_path, "r", encoding="utf-8") as f:
            self.voice_config = json.load(f).get(self.voice, {})

    async def process(self, msg: HandlerMessage) -> HandlerMessage:
        """
        Process a text message and convert it to speech.

        Args:
            msg: The message with text content to convert

        Returns:
            The processed message with audio file path in media[0]
        """
        if not msg.content:
            return msg

        try:
            # Generate TTS audio from text
            msg.media = None
            audio_bytes = await self._to_tts_datas(msg.content)
            if audio_bytes:
                msg.media = [{"datas": audio_bytes, "format": self.audio_format}]
            else:
                msg.error = "Failed to convert to speech"
        except Exception as e:
            msg.error = f"TTS conversion failed: {e}"
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
        text = clean_markdown(text)
        text = check_emoji(text)
        max_repeat_time, audio_bytes = 5, None
        while max_repeat_time > 0:
            try:
                # Get raw audio bytes from TTS
                audio_bytes = await self._text_to_speak(text)
                if not audio_bytes:
                    max_repeat_time -= 1
                    continue
                return audio_bytes
            except Exception as e:
                logger.error(f"TTS conversion error: {e}")
                max_repeat_time -= 1
        return audio_bytes

    async def _text_to_speak(self, text: str) -> bytes | None:
        """
        Convert text to speech using TTS service. To be implemented by subclasses.

        Args:
            text: Text content to convert

        Returns:
            Audio bytes or None if failed
        """
        raise NotImplementedError("Subclasses must implement _text_to_speak method")


@BaseTTSHandler.register()
class EdgeTTSHandler(BaseTTSHandler):
    """Handler that converts text messages to speech using Edge TTS."""

    @classmethod
    def handler_type(cls) -> str:
        return "edge_tts"

    async def _text_to_speak(self, text: str) -> bytes | None:
        import edge_tts

        try:
            communicate = edge_tts.Communicate(text, voice=self.voice)
            # Return audio binary data
            audio_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes += chunk["data"]
            return audio_bytes
        except Exception as e:
            error_msg = f"Edge TTS 请求失败：{e}"
            raise Exception(error_msg)


@BaseTTSHandler.register()
class F5TTSHandler(BaseTTSHandler):
    """F5 TTS handler for voice cloning using reference audio."""

    @classmethod
    def handler_type(cls) -> str:
        return "f5_tts"

    def __init__(self, config: TTSHandlerConfig | None = None):
        """
        Initialize the F5 TTS handler.

        Args:
            config: TTSHandlerConfig containing TTS settings
        """
        try:
            from f5_tts.api import F5TTS
            from f5_tts.infer.utils_infer import preprocess_ref_audio_text
        except ImportError:
            error_msg = "Init F5TTSHandler failed. Install: pip install f5-tts"
            raise ImportError(error_msg)

        super().__init__(config)
        # Build reference audio path relative to depends folder
        assert (
            "voices" in self.voice_config
            and isinstance(self.voice_config["voices"], list)
            and len(self.voice_config["voices"]) > 0
        ), "Voice configuration missing 'voices' array or it's empty"
        first_voice = self.voice_config["voices"][0]
        assert "audio" in first_voice and "text" in first_voice, (
            "First voice entry missing 'audio' or 'text' key"
        )
        ref_audio = self.depends_folder / first_voice["audio"]
        ref_text = first_voice["text"]
        assert ref_audio.exists(), f"Reference audio not found: {ref_audio}"
        with CaptureOutput():
            self.tts = F5TTS(model=config.model)
            self.ref_audio, self.ref_text = preprocess_ref_audio_text(ref_audio, ref_text)
        logger.info(f"✅ F5 TTS: Reference voice registered from {ref_audio}")

    async def _text_to_speak(self, text: str) -> bytes | None:
        """
        Convert text to speech using F5 TTS with voice cloning.

        Args:
            text: Text content to convert

        Returns:
            Audio bytes or None if failed
        """

        try:
            if not self.ref_audio or not self.ref_text:
                raise ValueError("Reference audio and text are required for F5 TTS")

            # Run inference with reference audio/text and generation text
            with CaptureOutput():
                wav, sr, _ = self.tts.infer(
                    ref_file=self.ref_audio,
                    ref_text=self.ref_text,
                    gen_text=text,
                    speed=1.0,
                )

            # Convert numpy array to WAV bytes
            wav_bytes = self._wav_bytes(wav, sr)
            return wav_bytes

        except Exception as e:
            error_msg = f"F5 TTS conversion failed: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _wav_bytes(self, wav: np.ndarray, sr: int) -> bytes:
        """Convert numpy array to WAV bytes."""

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sr)
            wav_int16 = (wav * 32767).astype(np.int16)
            wav_file.writeframes(wav_int16.tobytes())
        return buffer.getvalue()


@BaseTTSHandler.register()
class QwenTTSHandler(BaseTTSHandler):
    """Qwen TTS handler for voice cloning using Alibaba Cloud CosyVoice service."""

    @classmethod
    def handler_type(cls) -> str:
        return "qwen_tts"

    def __init__(self, config: TTSHandlerConfig | None = None):
        """
        Initialize the Qwen TTS handler.

        Args:
            config: TTSHandlerConfig containing TTS settings
        """
        try:
            import dashscope
            from dashscope.audio.tts_v2 import SpeechSynthesizer, VoiceEnrollmentService
        except ImportError:
            error_msg = "Init QwenTTSHandler failed. Install: pip install dashscope"
            raise ImportError(error_msg)

        super().__init__(config)
        self.model = config.model
        self.voice_id = self.voice_config.get("cosyvoice_id")
        self.voice_service = VoiceEnrollmentService()
        self._qwen_audio_format = self._get_audio_format()
        # Check if API key is configured
        import os

        assert os.getenv("DASHSCOPE_API_KEY"), (
            "Qwen TTS: DASHSCOPE_API_KEY environment variable not set"
        )
        logger.info(
            f"✅ Qwen TTS: Initialized with model: {self.model}, format: {self._qwen_audio_format}"
        )
        if self._check_voice(self.voice_id):
            logger.info(f"Use registered voice id {self.voice_id}")
        else:
            assert (
                "voices" in self.voice_config
                and isinstance(self.voice_config["voices"], list)
                and len(self.voice_config["voices"]) > 0
            ), "Voice configuration missing 'voices' array or it's empty"
            first_voice = self.voice_config["voices"][0]
            assert "audio" in first_voice, "First voice entry missing 'audio' key"
            ref_audio = self.depends_folder / first_voice["audio"]
            self._clone_voice(str(ref_audio))

    async def _text_to_speak(self, text: str) -> bytes | None:
        """
        Convert text to speech using Qwen TTS with optional voice cloning.

        Args:
            text: Text content to convert

        Returns:
            Audio bytes or None if failed
        """
        try:
            from dashscope.audio.tts_v2 import SpeechSynthesizer

            synthesizer = SpeechSynthesizer(
                model=self.model, voice=self.voice_id, format=self._qwen_audio_format
            )
            # Synthesize speech
            audio_data = synthesizer.call(text)
            return audio_data

        except Exception as e:
            error_msg = f"Qwen TTS conversion failed: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _get_audio_format(self):
        """Get the audio format based on the model and voice ID."""

        # Create speech synthesizer with the model and voice
        from dashscope.audio.tts_v2 import AudioFormat

        if self.audio_format == "wav" and self.sample_rate == 8000:
            return AudioFormat.WAV_8000HZ_MONO_16BIT
        if self.audio_format == "wav" and self.sample_rate == 16000:
            return AudioFormat.WAV_16000HZ_MONO_16BIT
        if self.audio_format == "wav" and self.sample_rate == 24000:
            return AudioFormat.WAV_24000HZ_MONO_16BIT
        if self.audio_format == "mp3" and self.sample_rate == 8000:
            return AudioFormat.MP3_8000HZ_MONO_128KBPS
        if self.audio_format == "mp3" and self.sample_rate == 16000:
            return AudioFormat.MP3_16000HZ_MONO_128KBPS
        if self.audio_format == "mp3" and self.sample_rate == 24000:
            return AudioFormat.MP3_24000HZ_MONO_256KBPS
        return AudioFormat.DEFAULT

    def _check_voice(self, voice_id):
        """
        Check if the voice is ready for use.
        """
        try:
            voice_info = self.voice_service.query_voice(voice_id=voice_id)
            status = voice_info.get("status")
            return status == "OK"
        except Exception as e:
            logger.warning(f"Voice check failed: {str(e)}")
            return False

    def _clone_voice(self, ref_audio):
        """
        Clone voice using reference audio through Alibaba Cloud CosyVoice service.

        This method creates a custom voice by converting local audio file to
        base64 string and uploading to Alibaba Cloud's voice enrollment service.
        """
        try:
            # Convert audio file to base64 string (similar to image handling)
            audio_data_url = self._get_audio_data(ref_audio)
            logger.info(f"🎤 Qwen TTS: Starting voice cloning from {ref_audio}")

            # Create voice enrollment using data URL
            self.voice_id = self.voice_service.create_voice(
                target_model=self.model, prefix=self.voice, url=audio_data_url
            )
            if not self.voice_id:
                raise ValueError("Failed to get voice_id from voice enrollment response")
            logger.info(
                f"Voice enrollment submitted successfully. Request ID: {self.voice_service.get_last_request_id()}, Voice ID: {self.voice_id}"
            )

            # Poll for voice status until ready
            max_attempts = 30
            poll_interval = 10  # seconds

            for attempt in range(max_attempts):
                try:
                    voice_info = self.voice_service.query_voice(voice_id=self.voice_id)
                    status = voice_info.get("status")

                    logger.debug(f"Voice status check {attempt + 1}/{max_attempts}: {status}")

                    if status == "OK":
                        logger.info(
                            f"✅ Qwen TTS: Voice cloning complete, voice {self.voice_id} is ready"
                        )
                        break
                    elif status == "UNDEPLOYED":
                        raise RuntimeError(f"Voice processing failed with status: {status}")

                    # Wait for next check
                    time.sleep(poll_interval)

                except Exception as e:
                    logger.warning(f"Voice status check error: {e}")
                    time.sleep(poll_interval)
            else:
                logger.warning("⚠️ Qwen TTS: Voice enrollment timeout, will try to use anyway")

            logger.info(f"🎯 Qwen TTS: Custom voice {self.voice_id} registered from {ref_audio}")

        except Exception as e:
            error_msg = f"Voice cloning failed: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _get_audio_data(self, audio_path: str) -> str:
        """
        Get audio file data as base64 encoded string with MIME type.

        Args:
            audio_path: Absolute path to the audio file.

        Returns:
            Data URL formatted string: "data:<mime_type>;base64,<encoded_audio>"

        Raises:
            FileNotFoundError: If audio file doesn't exist.
            ValueError: If file is not a valid audio format.
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Check file extension
        valid_extensions = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".wma"}
        if path.suffix.lower() not in valid_extensions:
            raise ValueError(
                f"Unsupported audio format: {path.suffix}. "
                f"Supported formats: {', '.join(valid_extensions)}"
            )

        # Get MIME type
        mime_types = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".wma": "audio/x-ms-wma",
        }
        mime_type = mime_types.get(path.suffix.lower(), "audio/wav")

        # Read and encode audio file
        with open(path, "rb") as audio_file:
            encoded_audio = base64.b64encode(audio_file.read()).decode("utf-8")

        return f"data:{mime_type};base64,{encoded_audio}"
