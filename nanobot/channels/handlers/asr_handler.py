"""ASR (Automatic Speech Recognition) handlers for speech recognition."""

import io
import json
import shutil
import wave
from pathlib import Path

from loguru import logger

from nanobot.channels.handlers.base_handler import BaseHandler, HandlerMessage
from nanobot.channels.handlers.utils.log import CaptureOutput
from nanobot.channels.handlers.utils.media import webm_to_wav
from nanobot.config.schema import Base


class ASRHandlerConfig(Base):
    """Configuration for ASR (Automatic Speech Recognition) handler."""

    enabled: bool = False
    handler_type: str = "fun_asr"
    model: str = "paraformer-zh"
    save_speech: bool = False  # Save speech audio and transcription to media dir


class BaseASRHandler(BaseHandler):
    """Base class for automatic speech recognition handlers."""

    name = "asr"
    config_cls = ASRHandlerConfig

    def __init__(self, config: ASRHandlerConfig):
        """Initialize the ASR handler with configuration.

        Args:
            config: ASR handler configuration
        """
        self._config = config
        self._save_speech = config.save_speech

    def _process_audio(self, file_path: str) -> str:
        """
        Recognize speech from audio file. To be implemented by subclasses.

        Args:
            file_path: Path to the audio file

        Returns:
            Recognized text
        """
        raise NotImplementedError("Subclasses must implement _process_audio method")

    async def process(self, msg: HandlerMessage) -> HandlerMessage:
        """
        Process an audio message by converting speech to text.

        Args:
            msg: HandlerMessage with audio media (file path in media[0])

        Returns:
            Modified HandlerMessage with transcribed text
        """
        if not msg.media:
            return msg

        try:
            # Get file path from media
            file_path = msg.media[0]
            if isinstance(file_path, dict):
                file_path = file_path.get("data", "")
            path = Path(file_path)
            if not path.exists():
                msg.error = f"Audio file not found: {file_path}"
                return msg

            # Perform ASR recognition directly on file path
            with CaptureOutput():
                text = self._process_audio(str(path))

            # Clear media and update message type
            msg.media = []
            if text:
                msg.content = text
            else:
                msg.content = "No speech recognized"
        except Exception as e:
            msg.error = f"Audio processing error: {e}"
        return msg


@BaseASRHandler.register()
class FunASRHandler(BaseASRHandler):
    """FunASR-based speech recognition handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "fun_asr"

    def __init__(self, config: ASRHandlerConfig):
        super().__init__(config)

        try:
            import psutil
            import torch
            import torchaudio
            from funasr import AutoModel
        except ImportError:
            logger.error(
                "Init FunASRHandler failed. Install with: pip install funasr psutil torch torchaudio"
            )
            return

        model = config.model
        # 内存检测，要求大于 2G
        min_mem_bytes = 2 * 1024 * 1024 * 1024
        total_mem = psutil.virtual_memory().total
        if total_mem < min_mem_bytes:
            logger.error(
                f"Insufficient memory (less than 2GB), only {total_mem / (1024 * 1024):.2f} MB available, FunASR may fail to start"
            )
        local_dir = None
        if Path(model).expanduser().is_dir():
            model = str(Path(model).expanduser())
            # bug of funasr, model path should start with models
            if model.startswith("models"):
                logger.debug(f"Load local asr model {model}")
            else:
                local_dir = Path("models")
                local_dir.mkdir(parents=True, exist_ok=True)
                src_model = Path(model).expanduser()
                dst_model = local_dir / src_model.name
                logger.debug(f"Local local asr {dst_model} from {src_model}")
                if src_model.is_dir() and not dst_model.exists():
                    shutil.copytree(src_model, dst_model)
                model = str(dst_model)
        else:
            logger.debug(f"Load remote asr model {model}")
        with CaptureOutput():
            self._model = AutoModel(
                model=model,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                hub="hf",
                disable_update=True,
            )
        if local_dir and local_dir.exists():
            shutil.rmtree(local_dir)

    def _process_audio(self, file_path: str) -> str:
        """
        Recognize speech from audio file using FunASR.

        Args:
            file_path: Path to the audio file

        Returns:
            Recognized text
        """
        assert self._model is not None, "FunASR model not initialized"
        # Convert webm to wav if needed
        path = Path(file_path)
        if path.suffix.lower() == ".webm":
            audio_bytes = webm_to_wav(input_file=path)
        else:
            audio_bytes = path.read_bytes()
        result = self._model.generate(
            input=audio_bytes, cache={}, language="auto", use_itn=True, batch_size_s=60
        )
        if result and len(result) > 0:
            text = result[0].get("text", "")
            # Save text if enabled
            if self._save_speech and text:
                text_file = path.with_suffix(".txt")
                text_file.write_text(text)
            logger.debug(f"FunASR transcription result: {text}")
            return text
        logger.warning("FunASR returned empty result")
        return ""


@BaseASRHandler.register()
class VoskASRHandler(BaseASRHandler):
    """Vosk-based speech recognition handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "vosk_asr"

    def __init__(self, config: ASRHandlerConfig):
        super().__init__(config)

        from vosk import Model

        model = config.model
        model_dir_expanded = Path(model).expanduser()
        if not model_dir_expanded.exists():
            logger.warning(f"Vosk model not found at {model}. Please download it manually.")
            logger.warning("Download from: https://alphacephei.com/vosk/models")
            logger.warning("Using small model: vosk-model-small-cn-0.22")
            return ""
        logger.info(f"Loading Vosk model from {model}")
        self._model = Model(model_path=str(model_dir_expanded))

    def _process_audio(self, file_path: str) -> str:
        """
        Recognize speech from audio file using Vosk (offline CPU-based ASR).

        Args:
            file_path: Path to the audio file

        Returns:
            Recognized text
        """
        from vosk import KaldiRecognizer

        path = Path(file_path)
        # Convert webm to wav if needed
        if path.suffix.lower() == ".webm":
            wav_io = webm_to_wav(input_file=path)
            audio_bytes = wav_io.read()
        else:
            audio_bytes = path.read_bytes()

        # Detect audio format and get sample rate
        wav_io = io.BytesIO(audio_bytes)
        with wave.open(wav_io, "rb") as wf:
            sample_rate = wf.getframerate()
            audio_data = wf.readframes(wf.getnframes())

        # Create recognizer
        recognizer = KaldiRecognizer(self._model, sample_rate)
        recognizer.SetWords(False)  # Don't include word timestamps

        # Feed audio data
        if recognizer.AcceptWaveform(audio_data):
            result = json.loads(recognizer.Result())
            text = result.get("text", "")
        else:
            # Get partial result
            result = json.loads(recognizer.PartialResult())
            text = result.get("partial", "")
        return text
