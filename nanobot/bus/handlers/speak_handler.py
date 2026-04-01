"""Speak handler for speaker verification using voiceprint recognition."""

import base64
import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.handlers.base_handler import BaseHandler
from nanobot.config.schema import SpeakHandlerConfig
from nanobot.utils.media import pcm_to_wav, webm_to_wav
from nanobot.utils.message import RetType


class BaseSpeakHandler(BaseHandler, ABC):
    """Base class for speaker verification handlers."""

    def __init__(self, config: SpeakHandlerConfig):
        # Load reference speaker embedding in subclass
        self.ref_embs = []
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
    def _verify_speaker(
        self, audio_bytes: bytes, audio_format: str = "audio/wav"
    ) -> tuple[bool, float]:
        """
        Verify if the audio matches the reference speaker.

        Args:
            audio_bytes: Base64 encoded audio data
            audio_format: Audio format of the input media data (default: "audio/wav")

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
        if not self.ref_embs or not msg.media:
            logger.debug("Speaker verification disabled - no reference embedding")
            return msg

        try:
            media_data, audio_format = msg.media[0], msg.metadata.get("audio_format", "audio/wav")
            # If media is a dict with 'data' key, extract it
            if isinstance(media_data, dict):
                media_data = media_data.get("data", "")
            if isinstance(media_data, str) and media_data.startswith("data:"):
                header, media_data = media_data.split(",", 1)
                audio_format = header.split(";")[0].replace("data:", "")
            # Read base64 audio data
            if isinstance(media_data, bytes):
                audio_bytes = media_data
            elif os.path.isfile(media_data):
                with open(media_data, "rb") as f:
                    audio_bytes = f.read()
            else:
                audio_bytes = base64.b64decode(
                    media_data.split(",", 1)[1] if "," in media_data else media_data
                )

            try:
                # Verify speaker using temporary file
                score = self._verify_speaker(audio_bytes, audio_format)
                is_verified = score > self.threshold
                if not is_verified:
                    msg.content = f"Speaker not verified ({score:.2f}<{self.threshold})"
                    msg.media = []
                    msg.metadata.update(
                        {
                            "msg_type": "text",
                            "ret_type": RetType.PASSBY,
                            "_hide_message": False,
                            "need_tts": False,
                            "_warning_msg": "speaker_not_verify",
                        }
                    )
                    logger.debug(msg.content)
            finally:
                # Clean up temporary file if exists
                pass

        except Exception as e:
            msg.content, msg.media = "Failed to verify speaker: " + str(e), []
            msg.metadata.update(
                {
                    "msg_type": "text",
                    "ret_type": RetType.PASSBY,
                    "_hide_message": False,
                    "need_tts": False,
                    "_warning_msg": "speaker_not_verify",
                }
            )
            logger.debug(msg.content)
        return msg


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
        assert (
            "voices" in self.voice_config
            and isinstance(self.voice_config["voices"], list)
            and len(self.voice_config["voices"]) > 0
        ), "Voice configuration missing 'voices' array or it's empty"
        # Load reference speaker embeddings from all voices
        self.ref_embs = []
        for voice_entry in self.voice_config["voices"]:
            assert "audio" in voice_entry, f"Voice entry missing 'audio' key: {voice_entry}"
            ref_audio = self.depends_folder / voice_entry["audio"]
            if config.speaker and ref_audio.exists():
                try:
                    self.ref_embs.append(self.speaker.extract_embedding(str(ref_audio)))
                    logger.info(f"Loaded reference speaker embedding from {ref_audio}")
                except Exception as e:
                    logger.error(f"Failed to extract reference speaker embedding: {e}")

    def _verify_speaker(
        self, audio_bytes: bytes, audio_format: str = "audio/wav"
    ) -> tuple[bool, float]:
        """
        Verify speaker using WeSpeaker from raw audio data.

        Args:
            audio_bytes: Base64 encoded audio data
            audio_format: Audio format of the input audio data (default: "audio/wav")

        Returns:
            Tuple of (is_verified, similarity_score)
        """
        if not self.ref_embs:
            logger.warning("Cannot verify speaker - no reference embedding available")
            return 0.0

        media_dir = Path.home() / ".nanobot" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        speaker_file = media_dir / "speaker.wav"
        try:
            if audio_format == "audio/webm":
                speaker_file = webm_to_wav(audio_bytes, output_file=speaker_file)
            elif audio_format == "audio/pcm":
                speaker_file = pcm_to_wav(audio_bytes, output_file=speaker_file)
            else:
                speaker_file.write_bytes(audio_bytes)
            emb = self.speaker.extract_embedding(speaker_file)
            # Compute max score across all reference embeddings
            max_score = 0.0
            for ref_emb in self.ref_embs:
                score = self.speaker.compute_cosine_score(ref_emb.flatten(), emb.flatten())
                max_score = max(max_score, score)
            return max_score
        except Exception as e:
            logger.error(f"WeSpeaker verification error: {e}")
            return 0.0
        finally:
            # Clean up temporary file
            if speaker_file.exists():
                speaker_file.unlink()
