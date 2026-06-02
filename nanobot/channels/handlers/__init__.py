"""Bus handlers for processing messages."""

from nanobot.channels.handlers.asr_handler import FunASRHandler, VoskASRHandler
from nanobot.channels.handlers.audio_encode_handler import OpusAudioEncodeHandler
from nanobot.channels.handlers.base_handler import BaseHandler
from nanobot.channels.handlers.speak_handler import BaseSpeakHandler, WeSpeakHandler
from nanobot.channels.handlers.tts_handler import EdgeTTSHandler
from nanobot.channels.handlers.vad_handler import SileroVADHandler

__all__ = [
    "BaseHandler",
    "BaseSpeakHandler",
    "WeSpeakHandler",
    "VoskASRHandler",
    "FunASRHandler",
    "EdgeTTSHandler",
    "SileroVADHandler",
    "OpusAudioEncodeHandler",
]
