"""VAD (Voice Activity Detection) handlers for voice activity detection."""

import time
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path

import numpy as np
from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.handlers.input.input_handler import InputHandler
from nanobot.config.schema import VADHandlerConfig


class BaseVADHandler(InputHandler, ABC):
    """Base class for voice activity detection handlers."""

    def __init__(self, config: VADHandlerConfig):
        # ASR audio cache for accumulating audio during speech
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
        self._asr_audio = []

    @classmethod
    def msg_type(cls) -> str:
        return "audio_clip"

    def can_handle(self, msg: InboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The inbound message to check

        Returns:
            True if the message type is audio
        """
        msg_type = msg.metadata.get("msg_type", "text")
        return msg_type == "audio_clip"

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

    async def handle(self, msg: InboundMessage) -> InboundMessage:
        """
        Process an audio message for voice activity detection.

        Args:
            msg: InboundMessage with audio media

        Returns:
            Modified InboundMessage with VAD metadata
        """
        if not msg.content:
            return msg

        self._asr_audio.append(msg.content)
        if self.is_vad(msg.content):
            # Voice detected, cache the audio
            print("[TMINFO] should add msg!!")
            # Don't pass this message further, wait for silence
            msg.content = ""
            msg.metadata["passby"] = True
        else:
            if not self._client_have_voice:
                self._asr_audio = self._asr_audio[-10:]
            msg.content = ""
            msg.metadata["passby"] = True
        return msg


@BaseVADHandler.register()
class SileroVADHandler(BaseVADHandler):
    """Silero-based voice activity detection handler."""

    @classmethod
    def handler_type(cls) -> str:
        return "silero"

    def __init__(self, config: VADHandlerConfig):
        try:
            import onnxruntime
            import opuslib_next
        except ImportError:
            logger.error(
                "Init SileroVADHandler failed. Install with: pip install onnxruntime opuslib_next"
            )
            return
        super().__init__(config)
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
        self._vad_opus_decoder = opuslib_next.Decoder(16000, 1)
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
            pcm_frame = self._vad_opus_decoder.decode(opus_packet, 960)
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
                print(f"[TMINFO] speech_prob {speech_prob} for bytes {chunk}")

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
                print("[TMINFO] client_have_voice" + str(client_have_voice))

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

            print("[TMINFO] client_have_voice " + str(client_have_voice))
            return client_have_voice

        except opuslib_next.OpusError as e:
            logger.info(f"Opus decoding error: {e}")
            return False
        except Exception as e:
            import traceback

            traceback.print_exc()
            logger.error(f"Error processing audio packet: {e}")
            return False
