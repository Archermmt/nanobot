"""VAD (Voice Activity Detection) handlers for voice activity detection."""

import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path
from typing import List

import numpy as np
from loguru import logger

from nanobot.channels.handlers.base_handler import BaseHandler, HandlerMessage
from nanobot.config.schema import Base


class VADHandlerConfig(Base):
    """Configuration for VAD (Voice Activity Detection) handler."""

    enabled: bool = False
    handler_type: str = "silero_vad"
    audio_format: str = "opus"  # opus or pcm
    model: str = "~/.nanobot/models/silero_vad"  # Path to Silero VAD model directory
    threshold: float = 0.5  # High threshold for voice detection
    threshold_low: float = 0.2  # Low threshold for voice detection
    min_silence_duration_ms: int = 1000  # Silence duration in ms to consider speech ended


class BaseVADHandler(BaseHandler, ABC):
    """Base class for voice activity detection handlers."""

    name = "vad"
    config_cls = VADHandlerConfig

    def __init__(self, config: VADHandlerConfig):
        try:
            import opuslib_next
        except ImportError:
            logger.error("Init SileroVADHandler failed. Install with: pip install opuslib_next")
            return
        # ASR audio cache for accumulating audio during speech
        self.audio_format = config.audio_format
        self.vad_threshold = config.threshold
        self.vad_threshold_low = config.threshold_low
        self.silence_threshold_ms = config.min_silence_duration_ms
        self.frame_window_threshold = 3
        # components
        self._client_audio_buffer = bytearray()
        self._client_voice_window = deque(maxlen=5)
        self._client_have_voice = False
        self._last_activity_time = 0.0
        self._client_voice_stop = False
        self._last_is_voice = False
        self._asr_audio, self._waiting_id = [], ""
        # decoder
        self._opus_decoder = opuslib_next.Decoder(16000, 1)

    @abstractmethod
    def is_vad(self, opus_packet: bytes) -> bool:
        """
        Detect voice activity in an Opus packet.

        Args:
            opus_packet: Opus encoded audio packet

        Returns:
            True if voice activity detected, False otherwise
        """
        pass

    async def process(self, msg: HandlerMessage) -> HandlerMessage:
        """
        Process a message for voice activity detection.

        Args:
            msg: HandlerMessage with audio media

        Returns:
            Modified HandlerMessage with VAD metadata
        """

        def _ignore_msg(msg):
            msg.content, msg.media = "", []
            msg.metadata["ret_type"] = "ignore"
            return msg

        if msg.content == "/vad_reset":
            self._reset_audio()
            return _ignore_msg(msg)

        if not msg.content or self._waiting_id:
            return _ignore_msg(msg)

        self._asr_audio.append(msg.content)
        audio_have_voice = self.is_vad(msg.content)
        if not audio_have_voice and not self._client_have_voice:
            self._asr_audio = self._asr_audio[-10:]
            return _ignore_msg(msg)

        if len(self._asr_audio) > 15 and not audio_have_voice and self._client_voice_stop:
            pcm_data = self._asr_audio.copy()
            if self.audio_format == "opus":
                pcm_data = self.decode_opus(pcm_data)
            msg.content, msg.media = "", [{"data": b"".join(pcm_data)}]
            self._waiting_id = str(uuid.uuid4())[:8]
            msg.metadata.update(
                {"msg_type": "audio", "file_type": "audio/pcm", "vad_id": self._waiting_id}
            )
            self._reset_audio()
            return msg
        return _ignore_msg(msg)

    def _reset_audio(self):
        """Reset the audio state."""
        self._asr_audio = []
        self._client_audio_buffer.clear()
        self._client_voice_window.clear()
        self._client_have_voice = False
        self._client_voice_stop = False
        self._last_is_voice = False

    def decode_opus(self, opus_data: List[bytes]) -> List[bytes]:
        """将Opus音频数据解码为PCM数据"""
        import opuslib_next

        try:
            pcm_data = []
            buffer_size = 960  # 每次处理960个采样点 (60ms at 16kHz)

            for i, opus_packet in enumerate(opus_data):
                try:
                    if not opus_packet or len(opus_packet) == 0:
                        continue

                    pcm_frame = self._opus_decoder.decode(opus_packet, buffer_size)
                    if pcm_frame and len(pcm_frame) > 0:
                        pcm_data.append(pcm_frame)

                except opuslib_next.OpusError as e:
                    logger.warning(f"Opus解码错误，跳过数据包 {i}: {e}")
                except Exception as e:
                    logger.error(f"音频处理错误，数据包 {i}: {e}")

            return pcm_data

        except Exception as e:
            logger.error(f"音频解码过程发生错误: {e}")
            return []


@BaseVADHandler.register()
class SileroVADHandler(BaseVADHandler):
    """Silero-based voice activity detection handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "silero_vad"

    def __init__(self, config: VADHandlerConfig):
        super().__init__(config)
        try:
            import onnxruntime
        except ImportError:
            logger.error("Init SileroVADHandler failed. Install with: pip install onnxruntime")
            return
        model_path = Path(config.model).expanduser()

        if not model_path.exists():
            logger.warning(f"Silero VAD model not found at {model_path}")
            raise FileNotFoundError(f"Model not found: {model_path}")

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"], sess_options=opts
        )
        self._vad_state = np.zeros((2, 1, 128), dtype=np.float32)
        self._vad_context = np.zeros((1, 64), dtype=np.float32)

    def is_vad(self, opus_packet: bytes) -> bool:
        """
        Detect voice activity using Silero VAD model.

        Args:
            conn: Connection object with state attributes
            opus_packet: Opus encoded audio packet

        Returns:
            True if voice activity detected, False otherwise
        """
        # Manual mode: always return True, cache all audio
        import opuslib_next

        try:
            # Decode Opus packet to PCM
            pcm_frame = self._opus_decoder.decode(opus_packet, 960)
            self._client_audio_buffer.extend(pcm_frame)

            client_have_voice = False

            # Process audio in 512-sample chunks
            while len(self._client_audio_buffer) >= 512 * 2:
                chunk = self._client_audio_buffer[: 512 * 2]
                self._client_audio_buffer = self._client_audio_buffer[512 * 2 :]

                # Convert int16 to float32
                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                # Prepare input for Silero model
                audio_input = np.concatenate(
                    [self._vad_context, audio_float32.reshape(1, -1)], axis=1
                ).astype(np.float32)

                # Run inference
                ort_inputs = {
                    "input": audio_input,
                    "state": self._vad_state,
                    "sr": np.array(16000, dtype=np.int64),
                }
                out, state = self.session.run(None, ort_inputs)

                # Update state
                self._vad_state = state
                self._vad_context = audio_input[:, -64:]
                speech_prob = out.item()

                # Dual threshold decision
                if speech_prob >= self.vad_threshold:
                    is_voice = True
                elif speech_prob <= self.vad_threshold_low:
                    is_voice = False
                else:
                    is_voice = self._last_is_voice

                # Maintain previous state if above low threshold
                self._last_is_voice = is_voice

                # Update sliding window
                self._client_voice_window.append(is_voice)
                client_have_voice = (
                    self._client_voice_window.count(True) >= self.frame_window_threshold
                )
                # Detect silence after voice
                if self._client_have_voice and not client_have_voice:
                    stop_duration = time.time() * 1000 - self._last_activity_time
                    if stop_duration >= self.silence_threshold_ms:
                        self._client_voice_stop = True

                # Update voice state
                if client_have_voice:
                    self._client_have_voice = True
                    self._last_activity_time = time.time() * 1000

                # Keep window bounded
                if len(self._client_voice_window) > 10:
                    self._client_voice_window = self._client_voice_window[-10:]
            return client_have_voice

        except opuslib_next.OpusError as e:
            logger.info(f"Opus decoding error: {e}")
            return False
        except Exception as e:
            import traceback

            traceback.print_exc()
            logger.error(f"Error processing audio packet: {e}")
            return False
