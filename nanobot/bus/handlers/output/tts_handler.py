"""Text to TTS handler for converting text messages to audio messages."""

import asyncio
import base64
import io
import os
import time
import wave
from pathlib import Path

import numpy as np
from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.handlers.output.output_handler import OutputHandler
from nanobot.config.schema import TTSHandlerConfig
from nanobot.utils.log import CaptureOutput
from nanobot.utils.media import audio_bytes_to_data_stream
from nanobot.utils.text_utils import check_emoji, clean_markdown


class BaseTTSHandler(OutputHandler):
    """Base class for text-to-speech message handlers."""

    def __init__(self, config: TTSHandlerConfig | None = None):
        """
        Initialize the TTS handler.

        Args:
            config: TTSHandlerConfig containing TTS settings
        """

        try:
            import opuslib_next
            import pydub
        except ImportError:
            error_msg = "Init EdgeTTSHandler failed. Install: pip install opuslib_next pydub"
            raise ImportError(error_msg)
        self.voice = config.voice
        self.audio_format = config.audio_format
        self.sample_rate = config.sample_rate
        self.encoder_type, self.encoder = config.encoder_type, None
        # Expand ~ to home directory and convert to absolute path
        self.output_dir = Path(config.output_dir).expanduser().resolve()
        if self.encoder_type == "opus":
            self.encoder = opuslib_next.Encoder(self.sample_rate, 1, opuslib_next.APPLICATION_AUDIO)

    @classmethod
    def msg_type(cls) -> str:
        return "text"

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
                msg.metadata.update({"msg_type": "audio", "encoder_type": self.encoder_type})
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
        text = clean_markdown(text)
        text = check_emoji(text)
        max_repeat_time, audio_bytes = 5, None

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
        """
        Convert text to speech using TTS service. To be implemented by subclasses.

        Args:
            text: Text content to convert
            output_file: Optional output file path (can be None)

        Returns:
            Audio bytes or None if output_file is provided
        """
        raise NotImplementedError("Subclasses must implement _text_to_speak method")


@BaseTTSHandler.register()
class EdgeTTSHandler(BaseTTSHandler):
    """Handler that converts text messages to speech using Edge TTS."""

    @classmethod
    def handler_type(cls) -> str:
        return "edge_tts"

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
            error_msg = f"Edge TTS 请求失败：{e}"
            raise Exception(error_msg)  # 抛出异常，让调用方捕获


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
        # Disable encoder
        self.encoder_type = ""

        # Initialize F5 TTS model
        self.tts = F5TTS(model="F5TTS_v1_Base")

        # Preprocess reference audio and text for voice cloning
        self.ref_audio = None
        self.ref_text = None
        if config and config.ref_audio and config.ref_text:
            with CaptureOutput():
                self.ref_audio, self.ref_text = preprocess_ref_audio_text(
                    Path(config.ref_audio).expanduser(), config.ref_text
                )
            logger.info(f"✅ F5 TTS: Reference voice registered from {config.ref_audio}")

    async def _text_to_speak(self, text, output_file):
        """
        Convert text to speech using F5 TTS with voice cloning.

        Args:
            text: Text content to convert
            output_file: Optional output file path (can be None)

        Returns:
            Audio bytes or None if output_file is provided
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

            if output_file:
                # Save to output file
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "wb") as f:
                    f.write(wav_bytes)
                return None
            else:
                # Return raw WAV bytes
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
        # Disable encoder for Qwen TTS (uses direct audio format)
        self.encoder_type = ""
        self.model = config.model
        # Voice ID will be lazily initialized on first use
        # cosyvoice-v3.5-plus-nanobot-874c66864fd34610ba502d22cdaf1698
        self.voice_id = config.voice
        # self.voice_id = "cosyvoice-v3.5-plus-nanobot-874c66864fd34610ba502d22cdaf1698"
        self.voice_service = VoiceEnrollmentService()
        # Check if API key is configured
        assert os.getenv("DASHSCOPE_API_KEY"), (
            "Qwen TTS: DASHSCOPE_API_KEY environment variable not set"
        )
        logger.info(f"✅ Qwen TTS: Initialized with model {self.model}")
        if self._check_voice(self.voice_id):
            logger.info(f"Use registered voice id {self.voice_id}")
        else:
            self._clone_voice(config.ref_audio)

    async def _text_to_speak(self, text, output_file):
        """
        Convert text to speech using Qwen TTS with optional voice cloning.

        Args:
            text: Text content to convert
            output_file: Optional output file path (can be None)

        Returns:
            Audio bytes or None if output_file is provided
        """
        try:
            from dashscope.audio.tts_v2 import SpeechSynthesizer

            # Create speech synthesizer with the model and voice
            synthesizer = SpeechSynthesizer(model=self.model, voice=self.voice_id)
            # Synthesize speech
            audio_data = synthesizer.call(text)

            if output_file:
                # Save to output file
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "wb") as f:
                    f.write(audio_data)
                return None
            else:
                # Return raw audio bytes
                return audio_data

        except Exception as e:
            error_msg = f"Qwen TTS conversion failed: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

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
                target_model=self.model, prefix="nanobot", url=audio_data_url
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
