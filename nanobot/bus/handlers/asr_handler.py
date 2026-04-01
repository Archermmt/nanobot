"""ASR (Automatic Speech Recognition) handlers for speech recognition."""

import asyncio
import base64
import io
import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path

from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.handlers.base_handler import BaseHandler
from nanobot.config.schema import ASRHandlerConfig
from nanobot.utils.log import CaptureOutput
from nanobot.utils.media import webm_to_wav
from nanobot.utils.message import RetType


class BaseASRHandler(BaseHandler):
    """Base class for automatic speech recognition handlers."""

    def can_handle_input(self, msg: InboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The inbound message to check

        Returns:
            True if the message type is supported, False otherwise
        """

        msg_type = msg.metadata.get("msg_type", "text")
        return msg_type == "audio" and not msg.content and msg.media

    async def _process_audio(self, audio_bytes: bytes, audio_format: str = "audio/wav") -> str:
        """
        Recognize speech from audio data. To be implemented by subclasses.

        Args:
            audio_bytes: Base64 encoded audio data
            audio_format: Audio format of the input media data (default: "audio/wav")

        Returns:
            Recognized text string
        """
        raise NotImplementedError("Subclasses must implement _process_audio method")

    async def handle_input(self, msg: InboundMessage) -> InboundMessage:
        """
        Process an audio message by converting speech to text.

        Args:
            msg: InboundMessage with audio media

        Returns:
            Modified InboundMessage with transcribed text
        """
        if not msg.media:
            return msg

        try:
            # Process first media item (assuming single audio file)
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

            # Recognize speech from audio
            msg.media = []
            msg.metadata.update({"msg_type": "text"})
            transcribed_text = await self._process_audio(audio_bytes, audio_format)
            if transcribed_text:
                logger.debug(f"Recognized speech: '{transcribed_text}'")
                msg.content = transcribed_text
                msg.metadata.update({"_as_input": True})
            else:
                msg.content = "No speech recognized"
                logger.debug(msg.content)
                msg.metadata.update({"need_tts": False})
                if "vad_id" in msg.metadata:
                    msg.metadata.update({"ret_type": RetType.IGNORE})
                else:
                    msg.metadata.update(
                        {
                            "ret_type": RetType.PASSBY,
                            "_hide_message": False,
                            "_warning_msg": "no_speech",
                        }
                    )
        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            msg.content = f"Error processing audio: {e}"
            msg.metadata.update(
                {"ret_type": RetType.PASSBY, "_hide_message": False, "_warning_msg": "no_speech"}
            )
        return msg


@BaseASRHandler.register()
class FunASRHandler(BaseASRHandler):
    """FunASR-based speech recognition handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "fun_asr"

    def __init__(self, config: ASRHandlerConfig):
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
                f"可用内存不足 2G，当前仅有 {total_mem / (1024 * 1024):.2f} MB，可能无法启动 FunASR"
            )

        if os.path.isdir(model):
            model_dir_expanded = Path(model).expanduser()

            if not model_dir_expanded.exists():
                logger.warning(f"FunASR model not found at {model}. Please download it manually.")
                return
            model = str(model_dir_expanded)
        logger.info(f"Loading FunASR model {model}")
        with CaptureOutput():
            self._model = AutoModel(
                model=model,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                hub="hf",
                disable_update=True,
            )

    async def _process_audio(self, audio_bytes: bytes, audio_format: str = "audio/wav") -> str:
        """
        Recognize speech from audio data using FunASR.

        Args:
            audio_bytes: Base64 encoded audio data
            audio_format: Audio format of the input media data (default: "wav")

        Returns:
            Recognized text string
        """

        try:
            if audio_format == "audio/webm":
                audio_bytes = webm_to_wav(audio_bytes)
            result = await asyncio.to_thread(
                self._model.generate,
                input=audio_bytes,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
            )
            return result[0]["text"] if result else ""
        except ImportError:
            logger.error("FunASR not installed. Install with: pip install funasr")
            return ""
        except Exception as e:
            logger.error(f"Speech recognition error: {e}")
            return ""


@BaseASRHandler.register()
class VoskASRHandler(BaseASRHandler):
    """Vosk-based speech recognition handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "vosk_asr"

    def __init__(self, config: ASRHandlerConfig):
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

    async def _process_audio(self, audio_bytes: bytes, audio_format: str = "wav") -> str:
        """
        Recognize speech from audio data using Vosk (offline CPU-based ASR).

        Args:
            audio_bytes: Base64 encoded audio data
            audio_format: Audio format of the input media data (default: "wav")

        Returns:
            Recognized text string
        """

        from vosk import KaldiRecognizer

        try:
            if audio_format == "audio/webm":
                audio_bytes = webm_to_wav(audio_bytes)
            # Detect audio format and convert to WAV if needed
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
            logger.info(f"Speech recognized: '{text}'")
            return text

        except ImportError:
            logger.error("Vosk not installed. Install with: pip install vosk")
            return ""
        except Exception as e:
            logger.error(f"Speech recognition error: {e}")
            return ""
