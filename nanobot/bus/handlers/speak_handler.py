"""Speak handler for speaker verification using voiceprint recognition."""

import base64
import json
import os
import tempfile
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.handlers.base_handler import BaseHandler
from nanobot.config.schema import SpeakHandlerConfig
from nanobot.utils.message import RetType


class BaseSpeakHandler(BaseHandler, ABC):
    """Base class for speaker verification handlers."""

    def __init__(self, config: SpeakHandlerConfig):
        # Load reference speaker embedding in subclass
        self.ref_emb = None
        self.threshold = config.threshold
        self.depends_folder = Path(config.depends_folder).expanduser()
        voice_path = self.depends_folder / "voice.json"
        assert voice_path.exists(), f"Voice configuration not found: {voice_path}"
        with open(voice_path, "r", encoding="utf-8") as f:
            self.voice_config = json.load(f).get(config.speaker, {})

    def can_handle_input(self, msg: InboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The inbound message to check

        Returns:
            True if the message type is audio
        """
        msg_type = msg.metadata.get("msg_type", "text")
        return msg_type == "audio" and not msg.content and msg.media

    @abstractmethod
    def _verify_speaker(self, media_data: str | bytes, audio_format: str) -> tuple[bool, float]:
        """
        Verify if the audio matches the reference speaker.

        Args:
            media_data: Audio data (bytes, file path, or base64 string)
            audio_format: Audio format string ('wav' or 'pcm')

        Returns:
            Tuple of (is_verified, similarity_score)
        """
        pass

    async def handle_input(self, msg: InboundMessage) -> InboundMessage:
        """
        Process an audio message for speaker verification.

        Args:
            msg: InboundMessage with audio media

        Returns:
            Modified InboundMessage with speaker verification result
        """
        if self.ref_emb is None or not msg.media:
            logger.debug("Speaker verification disabled - no reference embedding")
            return msg

        try:
            media_data = msg.media[0]
            if isinstance(media_data, dict):
                media_data = media_data.get("data", "")
            elif isinstance(media_data, str) and media_data.startswith("data:"):
                media_data = base64.b64decode(media_data.split(",", 1)[1])
            try:
                # Verify speaker using temporary file
                score = self._verify_speaker(media_data, msg.metadata.get("audio_format", "wav"))
                is_verified = score > self.threshold
                logger.debug(f"Speaker verified({is_verified}) with score: {score:.4f}")
                if not is_verified:
                    msg.content = f"Speaker not allowed ({score:.4f}<{self.threshold})"
                    msg.media = []
                    msg.metadata.update({"msg_type": "text", "ret_type": RetType.PASSBY})
            finally:
                # Clean up temporary file if exists
                pass

        except Exception as e:
            msg.content, msg.media = "Failed to verify speaker: " + str(e), []
            msg.metadata.update({"msg_type": "text", "ret_type": RetType.PASSBY})
            logger.debug(msg.content)
        return msg

    def _convert_to_wav(self, pcm_chunks: List[bytes]) -> bytes:
        """
        Convert PCM audio chunks to WAV format.

        Args:
            pcm_chunks: List of PCM audio data chunks

        Returns:
            WAV formatted audio data
        """
        import io

        # Concatenate all PCM chunks
        pcm_data = b"".join(pcm_chunks)

        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(pcm_data)

        return wav_buffer.getvalue()


@BaseSpeakHandler.register()
class WeSpeakHandler(BaseSpeakHandler):
    """WeSpeaker-based speaker verification handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "we_speak"

    def __init__(self, config: SpeakHandlerConfig):
        try:
            import wespeakerruntime as wespeaker
        except ImportError:
            logger.error("Init WeSpeakHandler failed. Install with: pip install wespeakerruntime")
            return

        super().__init__(config)
        self.speaker = wespeaker.Speaker(lang="chs")
        assert "audio" in self.voice_config, "Voice configuration missing 'audio' key"
        ref_audio = self.depends_folder / self.voice_config["audio"]
        # Load reference speaker embedding
        if config.speaker and ref_audio.exists():
            try:
                self.ref_emb = self.speaker.extract_embedding(str(ref_audio))
                logger.info(f"Loaded reference speaker embedding from {ref_audio}")
            except Exception as e:
                logger.error(f"Failed to extract reference speaker embedding: {e}")

    def _verify_speaker(self, media_data: str | bytes, audio_format: str) -> tuple[bool, float]:
        """
        Verify speaker using WeSpeaker from raw audio data.

        Args:
            media_data: Audio data (bytes, file path, or base64 string)
            audio_format: Audio format string ('wav' or 'pcm')

        Returns:
            Tuple of (is_verified, similarity_score)
        """
        if self.ref_emb is None:
            logger.warning("Cannot verify speaker - no reference embedding available")
            return False, 0.0

        # Extract audio bytes from various formats (similar to ASR handler)
        audio_bytes = None
        try:
            if isinstance(media_data, bytes):
                audio_bytes = media_data
            elif isinstance(media_data, str) and os.path.isfile(media_data):
                with open(media_data, "rb") as f:
                    audio_bytes = f.read()
            elif isinstance(media_data, str):
                # Handle base64 encoded string
                audio_bytes = base64.b64decode(
                    media_data.split(",", 1)[1] if "," in media_data else media_data
                )
        except Exception as e:
            logger.error(f"Failed to extract audio bytes: {e}")
            return False, 0.0

        tmp_path = None
        try:
            # Create temporary WAV file for speaker verification
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_path = tmp_file.name
                if audio_format == "wav":
                    tmp_file.write(audio_bytes)
                else:
                    wav_buffer = self._convert_to_wav([audio_bytes])
                    tmp_file.write(wav_buffer)
            # Extract embedding from input audio file
            emb = self.speaker.extract_embedding(tmp_path)
            return self.speaker.compute_cosine_score(self.ref_emb.flatten(), emb.flatten())

        except Exception as e:
            logger.error(f"WeSpeaker verification error: {e}")
            return False, 0.0
        finally:
            # Clean up temporary file
            if tmp_path and Path(tmp_path).exists():
                Path(tmp_path).unlink()
