"""Audio handlers for speech recognition."""

import base64
import io
import json
import wave
from pathlib import Path
from typing import TYPE_CHECKING
from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.handlers.base_handler import BaseHandler

if TYPE_CHECKING:
    from nanobot.config.schema import AudioHandlerConfig


class BaseAudioHandler(BaseHandler):
    """Base class for audio processing handlers."""

    @property
    def supported_msg_types(self) -> list[str]:
        """Audio handler can process 'audio' type messages."""
        return ["audio"]


class VoskAudioHandler(BaseAudioHandler):
    """Vosk-based speech recognition handler."""

    def __init__(self, model_path: str = "~/.nanobot/models/vosk-model-small-cn-0.22"):
        from vosk import Model

        model_path_expanded = Path(model_path).expanduser()
        if not model_path_expanded.exists():
            logger.warning(f"Vosk model not found at {model_path}. Please download it manually.")
            logger.warning("Download from: https://alphacephei.com/vosk/models")
            logger.warning("Using small model: vosk-model-small-cn-0.22")
            return ""
        logger.info(f"Loading Vosk model from {model_path}")
        self._model = Model(model_path=str(model_path_expanded))

    async def _process_audio(self, media_data: str) -> str:
        """
        Recognize speech from audio data using Vosk (offline CPU-based ASR).

        Args:
            media_data: Base64 encoded audio data (WAV format)

        Returns:
            Recognized text string
        """

        from vosk import KaldiRecognizer

        try:
            # Decode base64 audio data
            audio_bytes = base64.b64decode(media_data.split(",", 1)[1] if "," in media_data else media_data)

            # Read WAV file and extract PCM data
            wav_io = io.BytesIO(audio_bytes)
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

            # Recognize speech from audio
            transcribed_text = await self._process_audio(media_data)

            if transcribed_text:
                logger.info(f"Recognized speech from audio: '{transcribed_text}'")

                # Update message content with transcribed text
                msg.content = transcribed_text

                # Update metadata to indicate this is transcribed audio
                msg.metadata["transcribed_from_audio"] = True
                msg.metadata["original_msg_type"] = msg.metadata.get("msg_type", "audio")
            else:
                logger.warning("No speech recognized, skipping message")
                msg.content = "No speech recognized, skipping message"
        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            msg.content = f"Error processing audio: {e}"
        return msg


def load_audio_handler(config: "AudioHandlerConfig") -> BaseAudioHandler | None:
    """
    Load audio handler based on configuration.

    Args:
        config: AudioHandlerConfig instance

    Returns:
        Audio handler instance or None if disabled/invalid
    """
    if not config or not config.enabled:
        return None

    handler_type = config.handler_type

    if handler_type == "vosk":
        return VoskAudioHandler(model_path=config.model_path)
    elif handler_type == "custom":
        # Load custom handler from module path
        if config.custom_handler_path:
            import importlib
            from pathlib import Path

            handler_path = Path(config.custom_handler_path).expanduser()
            spec = importlib.util.spec_from_file_location("custom_handler", handler_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # Assume the module has a CustomHandler class
                if hasattr(module, "CustomHandler"):
                    return module.CustomHandler()
                else:
                    logger.error(f"Custom handler module does not have CustomHandler class")
        return None
    else:
        logger.warning(f"Unknown audio handler type: {handler_type}")
        return None
