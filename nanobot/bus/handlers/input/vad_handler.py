"""VAD (Voice Activity Detection) handlers for voice activity detection."""

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.handlers.input.input_handler import InputHandler
from nanobot.config.schema import VADHandlerConfig


class BaseVADHandler(InputHandler, ABC):
    """Base class for voice activity detection handlers."""

    @classmethod
    def msg_type(cls) -> str:
        return "audio"

    def can_handle(self, msg: InboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The inbound message to check

        Returns:
            True if the message type is audio
        """
        msg_type = msg.metadata.get("msg_type", "text")
        return msg_type == "audio" and not msg.content

    @abstractmethod
    def is_vad(self, conn: Any, opus_packet: bytes) -> bool:
        """
        Detect voice activity in an Opus packet.

        Args:
            conn: Connection object with state attributes
            opus_packet: Opus encoded audio packet

        Returns:
            True if voice activity detected, False otherwise
        """
        pass

    @abstractmethod
    def _init_connection_state(self, conn: Any) -> None:
        """Initialize connection-specific VAD state."""
        pass

    @abstractmethod
    def release_conn_resources(self, conn: Any) -> None:
        """Release VAD resources when connection closes."""
        pass

    async def handle(self, msg: InboundMessage) -> InboundMessage:
        """
        Process an audio message for voice activity detection.

        Args:
            msg: InboundMessage with audio media

        Returns:
            Modified InboundMessage with VAD metadata
        """
        if not msg.media:
            return msg

        try:
            # Mark message as processed by VAD
            msg.metadata["vad_processed"] = True
            logger.debug("VAD processing completed")
        except Exception as e:
            logger.error(f"VAD processing error: {e}")
            msg.metadata["vad_error"] = str(e)

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

        model_path = Path(config.model).expanduser() / "silero_vad.onnx"

        if not model_path.exists():
            logger.warning(f"Silero VAD model not found at {model_path}")
            raise FileNotFoundError(f"Model not found: {model_path}")

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1

        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"], sess_options=opts
        )

        self.vad_threshold = float(config.get("threshold", 0.5))
        self.vad_threshold_low = float(config.get("threshold_low", 0.2))
        self.silence_threshold_ms = int(config.get("min_silence_duration_ms", 1000))
        self.frame_window_threshold = 3

    def _init_connection_state(self, conn: Any) -> None:
        """Initialize connection-specific VAD state."""

        import opuslib_next

        if not hasattr(conn, "_vad_opus_decoder"):
            conn._vad_opus_decoder = opuslib_next.Decoder(16000, 1)
        if not hasattr(conn, "_vad_state"):
            conn._vad_state = np.zeros((2, 1, 128), dtype=np.float32)
        if not hasattr(conn, "_vad_context"):
            conn._vad_context = np.zeros((1, 64), dtype=np.float32)
        if not hasattr(conn, "client_audio_buffer"):
            conn.client_audio_buffer = bytearray()
        if not hasattr(conn, "client_voice_window"):
            conn.client_voice_window = []
        if not hasattr(conn, "last_is_voice"):
            conn.last_is_voice = False
        if not hasattr(conn, "client_have_voice"):
            conn.client_have_voice = False
        if not hasattr(conn, "client_voice_stop"):
            conn.client_voice_stop = False
        if not hasattr(conn, "last_activity_time"):
            conn.last_activity_time = 0

    def release_conn_resources(self, conn: Any) -> None:
        """Release connection VAD resources when connection closes."""
        for attr in (
            "_vad_opus_decoder",
            "_vad_state",
            "_vad_context",
            "client_audio_buffer",
            "client_voice_window",
            "last_is_voice",
            "client_have_voice",
            "client_voice_stop",
            "last_activity_time",
        ):
            if hasattr(conn, attr):
                try:
                    delattr(conn, attr)
                except Exception:
                    pass

    def is_vad(self, conn: Any, opus_packet: bytes) -> bool:
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

        if getattr(conn, "client_listen_mode", "auto") == "manual":
            return True

        try:
            self._init_connection_state(conn)

            # Decode Opus packet to PCM
            pcm_frame = conn._vad_opus_decoder.decode(opus_packet, 960)
            conn.client_audio_buffer.extend(pcm_frame)

            client_have_voice = False

            # Process audio in 512-sample chunks
            while len(conn.client_audio_buffer) >= 512 * 2:
                chunk = conn.client_audio_buffer[: 512 * 2]
                conn.client_audio_buffer = conn.client_audio_buffer[512 * 2 :]

                # Convert int16 to float32
                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                # Prepare input for Silero model
                audio_input = np.concatenate(
                    [conn._vad_context, audio_float32.reshape(1, -1)], axis=1
                ).astype(np.float32)

                # Run inference
                ort_inputs = {
                    "input": audio_input,
                    "state": conn._vad_state,
                    "sr": np.array(16000, dtype=np.int64),
                }
                out, state = self.session.run(None, ort_inputs)

                # Update state
                conn._vad_state = state
                conn._vad_context = audio_input[:, -64:]
                speech_prob = out.item()

                # Dual threshold decision
                if speech_prob >= self.vad_threshold:
                    is_voice = True
                elif speech_prob <= self.vad_threshold_low:
                    is_voice = False
                else:
                    is_voice = conn.last_is_voice

                # Maintain previous state if above low threshold
                conn.last_is_voice = is_voice

                # Update sliding window
                conn.client_voice_window.append(is_voice)
                client_have_voice = (
                    conn.client_voice_window.count(True) >= self.frame_window_threshold
                )

                # Detect silence after voice
                if conn.client_have_voice and not client_have_voice:
                    stop_duration = time.time() * 1000 - conn.last_activity_time
                    if stop_duration >= self.silence_threshold_ms:
                        conn.client_voice_stop = True

                # Update voice state
                if client_have_voice:
                    conn.client_have_voice = True
                    conn.last_activity_time = time.time() * 1000

                # Keep window bounded
                if len(conn.client_voice_window) > 10:
                    conn.client_voice_window = conn.client_voice_window[-10:]

            return client_have_voice

        except opuslib_next.OpusError as e:
            logger.info(f"Opus decoding error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error processing audio packet: {e}")
            return False
