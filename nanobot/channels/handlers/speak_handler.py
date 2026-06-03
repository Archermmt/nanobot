"""Speak handler for speaker verification using voiceprint recognition."""

import json
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger

from nanobot.channels.handlers.base_handler import BaseHandler, HandlerMessage
from nanobot.channels.handlers.utils.log import CaptureOutput
from nanobot.config.paths import get_media_dir
from nanobot.config.schema import Base
from nanobot.utils.media_decode import pcm_to_wav, webm_to_wav


class SpeakHandlerConfig(Base):
    """Configuration for Speaker Verification handler."""

    enabled: bool = False
    handler_type: str = "we_speak"
    depends_folder: str = "~/.nanobot/depends/speak"  # Folder for speaker reference audio files
    speaker: str = ""  # Reference speaker audio file name (relative to depends_folder)
    threshold: float = 0.9  # Similarity threshold for speaker verification
    separate_speaker: bool = False  # Enable speech separation for multi-speaker scenarios


class BaseSpeakHandler(BaseHandler, ABC):
    """Base class for speaker verification handlers."""

    name = "speak"
    config_cls = SpeakHandlerConfig

    def __init__(self, config: SpeakHandlerConfig):
        # Load reference speaker embedding in subclass
        self.threshold = config.threshold
        self.depends_folder = Path(config.depends_folder).expanduser()
        voice_path = self.depends_folder / "voice.json"
        assert voice_path.exists(), f"Voice configuration not found: {voice_path}"
        with open(voice_path, "r", encoding="utf-8") as f:
            self.voice_config = json.load(f).get(config.speaker, {})

    @abstractmethod
    def _verify_speaker(self, file_path: str | Path) -> float:
        """
        Verify if the audio matches the reference speaker.

        Args:
            file_path: Path to the audio file

        Returns:
            Similarity score (0.0 to 1.0)
        """
        pass

    async def process(self, msg: HandlerMessage) -> HandlerMessage:
        """
        Process an audio file for speaker verification.

        Args:
            msg: HandlerMessage with audio file path in media[0]

        Returns:
            Modified HandlerMessage with speaker verification result
        """
        if self.threshold == 0.0:
            return msg

        # Input is guaranteed to be a file path string
        file_path = msg.media[0]
        if isinstance(file_path, dict):
            file_path = file_path.get("data", "")

        try:
            path = Path(file_path)
            if not path.exists():
                msg.error = f"Audio file not found: {file_path}"
                return msg

            with CaptureOutput():
                score = self._verify_speaker(path)

            if score < self.threshold:
                msg.error = f"Speaker verification failed: {score:.2f}<{self.threshold}"
        except Exception as e:
            msg.error = f"Speaker verification error: {e}"

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

    def _verify_speaker(self, file_path: str | Path) -> float:
        """
        Verify speaker using WeSpeaker from audio file.

        Args:
            file_path: Path to the audio file

        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not self.ref_embs:
            logger.warning("Cannot verify speaker - no reference embedding available")
            return 0.0

        path = Path(file_path)
        output_file = get_media_dir() / "speaker.wav"
        audio_bytes = path.read_bytes()
        # Detect audio format from file extension or content
        suffix, converted = path.suffix.lower(), None
        if suffix == ".webm":
            converted = webm_to_wav(audio_bytes, output_file=output_file)
            assert converted, "Failed to convert webm to wav"
        elif suffix in [".pcm", ".raw"]:
            converted = pcm_to_wav(audio_bytes, output_file=output_file)
            assert converted, "Failed to convert pcm to wav"
        if converted and converted.exists():
            emb = self.speaker.extract_embedding(converted)
            converted.unlink()
        else:
            emb = self.speaker.extract_embedding(path)
        # Compute max score across all reference embeddings
        max_score = 0.0
        for ref_emb in self.ref_embs:
            score = self.speaker.compute_cosine_score(ref_emb.flatten(), emb.flatten())
            max_score = max(max_score, score)
        return max_score


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

    def _verify_speaker(self, file_path: str | Path) -> float:
        """
        Verify speaker using SpeechBrain from audio file with speech separation.

        Args:
            file_path: Path to the audio file

        Returns:
            Similarity score (0.0 to 1.0)
        """
        import torchaudio

        if not self.ref_audios:
            logger.warning("Cannot verify speaker - no reference audio available")
            return 0.0

        path = Path(file_path)
        speaker_file = get_media_dir() / "speaker.wav"
        separated_files = []
        audio_bytes = path.read_bytes()

        # Detect audio format and convert if needed
        suffix = path.suffix.lower()
        if suffix in [".webm"]:
            speaker_file = webm_to_wav(audio_bytes, output_file=speaker_file)
            assert speaker_file, "Failed to convert webm to wav"
        elif suffix in [".pcm", ".raw"]:
            speaker_file = pcm_to_wav(audio_bytes, output_file=speaker_file)
            assert speaker_file, "Failed to convert pcm to wav"
        else:
            # Assume it's already a WAV or compatible format
            speaker_file.write_bytes(audio_bytes)

        # Separate voices if enabled
        separated_files = []
        if self.separator:
            try:
                est_sources = self.separator.separate_file(path=str(speaker_file))
                # Save each separated source and verify against reference
                for i in range(est_sources.shape[2]):
                    sep_file = get_media_dir() / f"speech_{i}.wav"
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
        for idx, sep_file in enumerate(separated_files):
            for ref_audio_path in self.ref_audios:
                score, _ = self.verification.verify_files(ref_audio_path, str(sep_file))
                score = (float(score) + 1) / 2
                max_score = max(max_score, score)

        if speaker_file.exists():
            speaker_file.unlink()
        for sep_file in separated_files:
            if sep_file.exists():
                sep_file.unlink()
        return max_score
