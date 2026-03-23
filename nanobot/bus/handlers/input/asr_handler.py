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
from nanobot.bus.handlers.input.input_handler import InputHandler
from nanobot.config.schema import ASRHandlerConfig
from nanobot.utils.log import CaptureOutput


class BaseASRHandler(InputHandler):
    """Base class for automatic speech recognition handlers."""

    @classmethod
    def msg_type(cls) -> str:
        return "audio"

    def can_handle(self, msg: InboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The inbound message to check

        Returns:
            True if the message type is supported, False otherwise
        """

        msg_type = msg.metadata.get("msg_type", "text")
        return msg_type == "audio" and not msg.content

    async def _process_audio(self, media_data: str, audio_format: str = "wav") -> str:
        """
        Recognize speech from audio data. To be implemented by subclasses.

        Args:
            media_data: Base64 encoded audio data or file path
            audio_format: Audio format of the input media data (default: "wav")

        Returns:
            Recognized text string
        """
        raise NotImplementedError("Subclasses must implement _process_audio method")

    async def handle(self, msg: InboundMessage) -> InboundMessage:
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
            media_data = msg.media[0]

            # If media is a dict with 'data' key, extract it
            if isinstance(media_data, dict):
                media_data = media_data.get("data", "")
            elif isinstance(media_data, str) and media_data.startswith("data:"):
                media_data = base64.b64decode(media_data.split(",", 1)[1])

            # Recognize speech from audio
            audio_format = msg.metadata.get("audio_format", "wav")
            transcribed_text = await self._process_audio(media_data, audio_format)

            if transcribed_text:
                logger.info(f"Recognized speech from audio: '{transcribed_text}'")
                msg.content = transcribed_text
                msg.media, keep_keys = [], ("source", "timestamp", "session_id", "need_tts")
                keep_meta = {k: v for k, v in msg.metadata.items() if k in keep_keys}
                msg.metadata = {**keep_meta, "_as_input": True}
            else:
                logger.warning("No speech recognized, skipping message")
                msg.content = ""
                msg.metadata = {"passby": True}
        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            msg.content = f"Error processing audio: {e}"
        return msg

    def _convert_to_wav(self, audio_bytes: bytes) -> io.BytesIO | None:
        """
        Convert non-WAV audio to WAV format using ffmpeg.

        Args:
            audio_bytes: Raw audio data bytes

        Returns:
            BytesIO object with WAV data, or None if conversion fails
        """
        try:
            # Create temporary input file
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
                tmp_in.write(audio_bytes)
                tmp_in_path = tmp_in.name

            # Create temporary output file for WAV
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
                tmp_out_path = tmp_out.name

            try:
                # Use ffmpeg to convert to WAV
                subprocess.run(
                    [
                        "ffmpeg",
                        "-i",
                        tmp_in_path,
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        "-f",
                        "wav",
                        "-y",
                        tmp_out_path,
                    ],
                    capture_output=True,
                    check=True,
                )

                # Read converted WAV file
                with open(tmp_out_path, "rb") as f:
                    converted_bytes = f.read()
                    wav_io = io.BytesIO(converted_bytes)

                logger.info("Successfully converted audio to WAV format")
                return wav_io

            finally:
                # Cleanup temporary files
                if os.path.exists(tmp_in_path):
                    os.unlink(tmp_in_path)
                if os.path.exists(tmp_out_path):
                    os.unlink(tmp_out_path)

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg conversion failed: {e.stderr.decode() if e.stderr else e}")
            return None
        except FileNotFoundError:
            logger.error("FFmpeg not found. Please install ffmpeg to convert non-WAV audio.")
            return None
        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
            return None


@BaseASRHandler.register()
class FunasrHandler(BaseASRHandler):
    """FunASR-based speech recognition handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "funasr"

    def __init__(self, config: ASRHandlerConfig):
        try:
            import psutil
            import torch
            import torchaudio
            from funasr import AutoModel
        except ImportError:
            logger.error(
                "Init FunasrHandler failed. Install with: pip install funasr psutil torch torchaudio"
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

    async def _process_audio(self, media_data: str, audio_format: str = "wav") -> str:
        """
        Recognize speech from audio data using FunASR.

        Args:
            media_data: Base64 encoded audio data (WAV or WebM format)
            audio_format: Audio format of the input media data (default: "wav")

        Returns:
            Recognized text string
        """
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
            if audio_format == "wav":
                # Detect audio format and convert to WAV if needed
                wav_io = io.BytesIO(audio_bytes)
                wav_io.seek(0)
                header = wav_io.read(4)
                wav_io.seek(0)
                if header != b"RIFF":
                    # Not a WAV file, use parent class method to convert
                    logger.info("Detected non-WAV format, converting to WAV...")
                    converted_wav = self._convert_to_wav(audio_bytes)
                    if converted_wav is None:
                        return ""
                    wav_io = converted_wav
                # Read WAV file and extract PCM data
                with wave.open(wav_io, "rb") as wf:
                    audio_data = wf.readframes(wf.getnframes())
            else:
                audio_data = audio_bytes
            # Use thread pool to avoid blocking event loop
            result = await asyncio.to_thread(
                self._model.generate,
                input=audio_data,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
            )
            # Extract text from result
            return result[0]["text"] if result else ""
        except ImportError:
            logger.error("FunASR not installed. Install with: pip install funasr")
            return ""
        except Exception as e:
            logger.error(f"Speech recognition error: {e}")
            return ""


@BaseASRHandler.register()
class VoskHandler(BaseASRHandler):
    """Vosk-based speech recognition handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "vosk"

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

    async def _process_audio(self, media_data: str, audio_format: str = "wav") -> str:
        """
        Recognize speech from audio data using Vosk (offline CPU-based ASR).

        Args:
            media_data: Base64 encoded audio data (WAV or WebM format)
            audio_format: Audio format of the input media data (default: "wav")

        Returns:
            Recognized text string
        """

        from vosk import KaldiRecognizer

        # Read base64 audio data
        if os.path.isfile(media_data):
            with open(media_data, "rb") as f:
                audio_bytes = f.read()
        else:
            audio_bytes = base64.b64decode(
                media_data.split(",", 1)[1] if "," in media_data else media_data
            )

        try:
            # Detect audio format and convert to WAV if needed
            wav_io = io.BytesIO(audio_bytes)

            # Check if it's a WAV file by reading the first 4 bytes
            wav_io.seek(0)
            header = wav_io.read(4)
            wav_io.seek(0)

            if header != b"RIFF":
                # Not a WAV file, use parent class method to convert
                logger.info("Detected non-WAV format, converting to WAV...")
                converted_wav = self._convert_to_wav(audio_bytes)
                if converted_wav is None:
                    return ""
                wav_io = converted_wav

            # Read WAV file and extract PCM data
            with wave.open(wav_io, "rb") as wf:
                sample_rate = wf.getframerate()

                # Read all frames
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
