"""Speak handler for speaker verification using voiceprint recognition."""

import base64
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.channels.handlers.base_handler import BaseHandler, HandlerMessage
from nanobot.channels.handlers.utils.log import CaptureOutput
from nanobot.channels.handlers.utils.media import (
    get_audio_bytes,
    get_media_dir,
    pcm_to_wav,
    webm_to_wav,
)
from nanobot.config.schema import SpeakHandlerConfig


class BaseSpeakHandler(BaseHandler, ABC):
    """Base class for speaker verification handlers."""

    def __init__(self, config: SpeakHandlerConfig):
        # Load reference speaker embedding in subclass
        self.threshold = config.threshold
        self.depends_folder = Path(config.depends_folder).expanduser()
        voice_path = self.depends_folder / "voice.json"
        assert voice_path.exists(), f"Voice configuration not found: {voice_path}"
        with open(voice_path, "r", encoding="utf-8") as f:
            self.voice_config = json.load(f).get(config.speaker, {})

    @abstractmethod
    def _verify_speaker(
        self, audio_bytes: bytes, audio_format: str = "audio/wav", msg: InboundMessage | None = None
    ) -> tuple[float, InboundMessage]:
        """
        Verify if the audio matches the reference speaker.

        Args:
            audio_bytes: Base64 encoded audio data
            audio_format: Audio format of the input media data (default: "audio/wav")
            msg: Optional InboundMessage to modify based on verification result

        Returns:
            Tuple of (similarity_score, modified_message)
        """
        pass

    async def process(self, msg: HandlerMessage) -> HandlerMessage:
        """
        Process an audio message for speaker verification.

        Args:
            msg: HandlerMessage with audio media

        Returns:
            Modified HandlerMessage with speaker verification result
        """

        if self.threshold == 0.0:
            return msg
        audio_format = msg.metadata.get("file_type", "audio/wav")
        audio_bytes, audio_format = get_audio_bytes(msg.media[0], audio_format)

        def _mark_failed(msg, err):
            msg.content, msg.media = "Speaker verify failed: " + str(err), []
            msg.metadata.update({"msg_type": "text", "_warning_msg": "speaker_not_verify"})
            return msg

        try:
            with CaptureOutput():
                score, msg = self._verify_speaker(audio_bytes, audio_format, msg)
            if score < self.threshold:
                msg = _mark_failed(msg, f"{score:.2f}<{self.threshold}")
        except Exception as e:
            msg = _mark_failed(msg, e)
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
        with CaptureOutput():
            self.speaker = wespeaker.Speaker(lang="chs")
        assert (
            "voices" in self.voice_config
            and isinstance(self.voice_config["voices"], list)
            and len(self.voice_config["voices"]) > 0
        ), "Voice configuration missing 'voices' array or it's empty"
        # Load reference speaker embeddings from all voices
        self.ref_embs, ref_audios = [], []
        for voice_entry in self.voice_config["voices"]:
            assert "audio" in voice_entry, f"Voice entry missing 'audio' key: {voice_entry}"
            ref_audio = self.depends_folder / voice_entry["audio"]
            if config.speaker and ref_audio.exists():
                try:
                    self.ref_embs.append(self.speaker.extract_embedding(str(ref_audio)))
                    ref_audios.append(voice_entry["audio"])
                except Exception as e:
                    logger.error(f"Failed to extract reference speaker embedding: {e}")
        logger.debug(f"Loaded reference speaker embedding from {ref_audios}")

    def _verify_speaker(
        self, audio_bytes: bytes, audio_format: str = "audio/wav", msg: InboundMessage | None = None
    ) -> tuple[float, InboundMessage]:
        """
        Verify speaker using WeSpeaker from raw audio data.

        Args:
            audio_bytes: Base64 encoded audio data
            audio_format: Audio format of the input audio data (default: "audio/wav")
            msg: Optional InboundMessage to modify based on verification result

        Returns:
            Tuple of (similarity_score, modified_message)
        """
        if not self.ref_embs:
            logger.warning("Cannot verify speaker - no reference embedding available")
            if msg:
                msg.content = "Speaker verification disabled - no reference embedding"
            return 0.0, msg or InboundMessage(content="")

        media_dir = get_media_dir()
        speaker_file = media_dir / "speaker.wav"
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
        if speaker_file.exists():
            speaker_file.unlink()
        return max_score, msg or InboundMessage(content="")


@BaseSpeakHandler.register()
class SbrainSpeakHandler(BaseSpeakHandler):
    """SpeechBrain-based speaker verification handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "sbrain_speak"

    def __init__(self, config: SpeakHandlerConfig):
        try:
            from speechbrain.inference.separation import SepformerSeparation as Separator
            from speechbrain.inference.speaker import SpeakerRecognition
        except ImportError:
            logger.error("Init SbrainSpeakHandler failed. Install with: pip install speechbrain")
            return

        super().__init__(config)
        # Initialize SpeechBrain speaker recognition with ECAPA-TDNN model
        ver_pretrained_dir = self.depends_folder / "pretrained_models" / "spkrec-ecapa-voxceleb"
        with CaptureOutput():
            self.verification = SpeakerRecognition.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb", savedir=str(ver_pretrained_dir)
            )
            # Initialize SpeechBrain speech separation model only if enabled
            if config.separate_speaker:
                sep_pretrained_dir = (
                    self.depends_folder / "pretrained_models" / "sepformer-wsj02mix"
                )
                self.separator = Separator.from_hparams(
                    source="speechbrain/sepformer-wsj02mix", savedir=str(sep_pretrained_dir)
                )
            else:
                self.separator = None
        assert (
            "voices" in self.voice_config
            and isinstance(self.voice_config["voices"], list)
            and len(self.voice_config["voices"]) > 0
        ), "Voice configuration missing 'voices' array or it's empty"
        # Load reference speaker audios from all voices
        self.ref_audios = []
        for voice_entry in self.voice_config["voices"]:
            assert "audio" in voice_entry, f"Voice entry missing 'audio' key: {voice_entry}"
            ref_audio = self.depends_folder / voice_entry["audio"]
            if config.speaker and ref_audio.exists():
                self.ref_audios.append(voice_entry["audio"])
        logger.debug(f"Loaded reference speaker audio from {self.ref_audios}")

    def _verify_speaker(
        self, audio_bytes: bytes, audio_format: str = "audio/wav", msg: InboundMessage | None = None
    ) -> tuple[float, InboundMessage]:
        """
        Verify speaker using SpeechBrain from raw audio data with speech separation.

        Args:
            audio_bytes: Base64 encoded audio data
            audio_format: Audio format of the input audio data (default: "audio/wav")
            msg: Optional InboundMessage to modify based on verification result

        Returns:
            Tuple of (similarity_score, modified_message)
        """
        import torchaudio

        if not self.ref_audios:
            logger.warning("Cannot verify speaker - no reference audio available")
            if msg:
                msg.content = "Speaker verification disabled - no reference audio"
            return 0.0, msg or InboundMessage(content="")

        media_dir = get_media_dir()
        speaker_file, separated_files = media_dir / "speaker.wav", []
        # Convert audio to wav format
        if audio_format == "audio/webm":
            speaker_file = webm_to_wav(audio_bytes, output_file=speaker_file)
        elif audio_format == "audio/pcm":
            speaker_file = pcm_to_wav(audio_bytes, output_file=speaker_file)
        else:
            speaker_file.write_bytes(audio_bytes)
        # Separate voices if enabled
        separated_files = []
        if self.separator:
            try:
                est_sources = self.separator.separate_file(path=str(speaker_file))
                # Save each separated source and verify against reference
                for i in range(est_sources.shape[2]):
                    sep_file = media_dir / f"speech_{i}.wav"
                    # Save separated source as mono 8kHz WAV
                    torchaudio.save(str(sep_file), est_sources[:, :, i].detach().cpu(), 8000)
                    separated_files.append(sep_file)
            except Exception as sep_error:
                # If separation fails, fall back to original mixed audio
                logger.warning(f"Speech separation failed: {sep_error}, using original audio")
                separated_files = [speaker_file]
        else:
            separated_files = [speaker_file]
        # Verify each separated source against all reference audios
        max_score = 0.0
        best_source_idx = -1
        for idx, sep_file in enumerate(separated_files):
            for ref_audio_path in self.ref_audios:
                score, _ = self.verification.verify_files(ref_audio_path, str(sep_file))
                score = (float(score) + 1) / 2
                if score > max_score:
                    max_score = score
                    best_source_idx = idx

        # Set the best matching separated source to msg.media
        if msg and best_source_idx >= 0 and max_score > 0:
            best_source_file = separated_files[best_source_idx]
            # Read the best source file and encode as base64
            with open(best_source_file, "rb") as f:
                best_audio_data = f.read()
            # Create data URL for the separated audio
            audio_data_url = (
                f"data:audio/wav;base64,{base64.b64encode(best_audio_data).decode('utf-8')}"
            )
            msg.media = [audio_data_url]
            msg.metadata["file_type"] = "audio/wav"
            logger.debug(f"Selected source {best_source_idx} with score {max_score:.2f}")
        if speaker_file.exists():
            speaker_file.unlink()
        for sep_file in separated_files:
            if sep_file.exists():
                sep_file.unlink()
        return max_score, msg or InboundMessage(content="")
