"""Text to TTS handler for converting text messages to audio messages."""

import os
import uuid

from botpy import Type as BotType

from nanobot.bus.events import OutboundMessage
from nanobot.bus.handlers.output.output_handler import OutputHandler
from nanobot.config.schema import TextHandlerConfig


class BaseTextHandler(OutputHandler):
    """Base class for text message handlers."""

    @classmethod
    def register(cls, handler_type: str):
        """
        Decorator to register a subclass with a specific handler type.

        Args:
            handler_type: The handler type to register (e.g., "edge_tts", "azure_tts")

        Usage:
            @BaseTextHandler.register("edge_tts")
            class EdgeTTSHanlder(BaseTextHandler):
                pass
        """

        def decorator(subclass: BotType["BaseTextHandler"]) -> BotType["BaseTextHandler"]:
            OutputHandler._registry[f"text.{handler_type}"] = subclass
            return subclass

        return decorator

    @classmethod
    def get_registered_type(cls, handler_type: str) -> BotType["BaseTextHandler"] | None:
        """
        Get a registered handler class by handler type.

        Args:
            handler_type: The handler type to look up

        Returns:
            The registered handler class, or None if not found
        """
        return OutputHandler.get_registered_type("text", handler_type)


@BaseTextHandler.register("edge_tts")
class EdgeTTSHandler(BaseTextHandler):
    """Handler that converts text messages to speech using TTS."""

    def __init__(self, config: TextHandlerConfig | None = None):
        """
        Initialize the TTS handler.

        Args:
            config: TextHandlerConfig containing TTS settings
        """
        if config is None:
            from nanobot.config.schema import TextHandlerConfig

            config = TextHandlerConfig()

        self.delete_audio_file = config.delete_audio_file
        self.output_file = config.output_dir
        self.audio_file_type = config.format

        # Edge TTS specific config
        if config.private_voice:
            self.voice = config.private_voice
        else:
            self.voice = config.voice

        # Ensure output directory exists
        if not os.path.exists(self.output_file):
            os.makedirs(self.output_file)

    def can_handle(self, msg: OutboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The outbound message to check

        Returns:
            True if the message is text type and should be converted to speech
        """
        msg_type = msg.metadata.get("msg_type", "text")
        # Only handle text messages that need TTS conversion
        return msg_type == "text" and msg.metadata.get("need_tts", False)

    async def handle(self, msg: OutboundMessage) -> OutboundMessage:
        """
        Process a text message and convert it to speech.

        Args:
            msg: The outbound message to process

        Returns:
            The processed message with audio data added
        """
        if not msg.content:
            return msg

        try:
            # Generate TTS audio from text
            audio_data = await self._to_tts_stream(msg.content)

            if audio_data:
                # Add audio data to message
                msg.media.append(audio_data)
                # Update message type to indicate it now contains audio
                msg.metadata["msg_type"] = "audio"
                msg.metadata["tts_processed"] = True

        except Exception as e:
            # If TTS fails, keep original text message
            msg.metadata["tts_error"] = str(e)

        return msg

    def _generate_filename(self, extension: str = ".wav") -> str:
        """Generate a unique filename for TTS audio file."""
        return os.path.join(
            self.output_file,
            f"tts-{uuid.uuid4().hex}{extension}",
        )

    async def _to_tts_stream(self, text: str) -> str | None:
        """
        Convert text to speech audio stream.

        This method references the implementation from:
        /Users/tongmeng/Desktop/codes/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/base.py::to_tts_stream

        Args:
            text: Text content to convert to speech

        Returns:
            Path to generated audio file or None if failed
        """
        # Clean markdown formatting from text
        text = self._clean_markdown(text)

        max_repeat_time = 5
        tmp_file = None

        if self.delete_audio_file:
            # Don't save file, directly convert to audio data
            while max_repeat_time > 0:
                try:
                    audio_bytes = await self._text_to_speak(text, None)
                    if audio_bytes:
                        # Save temporarily to return path
                        tmp_file = self._generate_filename()
                        with open(tmp_file, "wb") as f:
                            f.write(audio_bytes)
                        break
                    else:
                        max_repeat_time -= 1
                except Exception as e:
                    max_repeat_time -= 1

            # Clean up if we're supposed to delete files
            if self.delete_audio_file and tmp_file and os.path.exists(tmp_file):
                os.remove(tmp_file)
                return None
            return tmp_file
        else:
            # Save to file
            tmp_file = self._generate_filename()
            try:
                while not os.path.exists(tmp_file) and max_repeat_time > 0:
                    try:
                        await self._text_to_speak(text, tmp_file)
                    except Exception as e:
                        # Delete file if creation failed
                        if os.path.exists(tmp_file):
                            os.remove(tmp_file)
                        max_repeat_time -= 1

                if max_repeat_time > 0 and os.path.exists(tmp_file):
                    return tmp_file
                else:
                    return None
            except Exception:
                return None

    async def _text_to_speak(self, text: str, output_file: str | None) -> bytes | None:
        """
        Convert text to speech audio using Edge TTS.

        Args:
            text: Text to convert
            output_file: Optional file path to save audio (None for in-memory)

        Returns:
            Audio bytes if output_file is None, otherwise None (audio saved to file)
        """
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, voice=self.voice)

            if output_file:
                # Ensure directory exists and create empty file
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "wb") as f:
                    pass

                # Stream audio data to file
                with open(output_file, "ab") as f:  # Append mode to avoid overwriting
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":  # Only process audio chunks
                            f.write(chunk["data"])
                return None
            else:
                # Return audio binary data
                audio_bytes = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes += chunk["data"]
                return audio_bytes

        except ImportError:
            error_msg = "edge-tts not installed. Install with: pip install edge-tts"
            raise ImportError(error_msg)
        except Exception as e:
            error_msg = f"Edge TTS request failed: {e}"
            raise Exception(error_msg)

    def _clean_markdown(self, text: str) -> str:
        """
        Clean markdown formatting from text.

        References: MarkdownCleaner.clean_markdown from xiaozhi TTS base

        Args:
            text: Text with potential markdown formatting

        Returns:
            Cleaned text without markdown
        """
        import re

        # Remove common markdown patterns
        # Bold: **text** or __text__
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)

        # Italic: *text* or _text_
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)

        # Code: `code`
        text = re.sub(r"`(.+?)`", r"\1", text)

        # Links: [text](url)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)

        # Headers: # text
        text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)

        return text
