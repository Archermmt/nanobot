"""Music tools for listing and playing music files."""

from pathlib import Path
from typing import Any, Awaitable, Callable

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage
from nanobot.utils.media import get_media_dir


class MusicTool(Tool):
    """
    Tool for managing and playing music files.

    Supports two modes:
    - list: List all available music files in the media directory
    - play: Play a music file by sending it as media in an outbound message
    """

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        default_message_id: str | None = None,
    ):
        """Initialize the music tool with all required parameters."""
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        self._default_message_id = default_message_id

    @property
    def name(self) -> str:
        return "music"

    @property
    def description(self) -> str:
        return (
            "Manage and play music files. Supports two modes:\n"
            "- list: List all available music files in the media directory. "
            "Returns a list of music files with their names and paths.\n"
            "- play: Play a music file by sending it to the user. "
            "The music file will be sent as media attachment through the channel. "
            "Supported formats: MP3, WAV, OGG, AAC, FLAC, M4A."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["list", "play"],
                    "description": (
                        "The operation mode: 'list' to show available music files, "
                        "'play' to play a specific music file."
                    ),
                },
                "music_path": {
                    "type": "string",
                    "description": (
                        "[Required for play mode] Path to the music file to play. "
                        "Can be either an absolute path or a filename from the media directory. "
                        "Supported formats: MP3, WAV, OGG, AAC, FLAC, M4A. "
                        "Example: '/Users/archer/Music/song.mp3' or 'song.mp3'"
                    ),
                },
            },
            "required": ["mode"],
        }

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_message_id = message_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    async def execute(
        self,
        mode: str,
        music_path: str = "",
        **kwargs: Any,
    ) -> str:
        """
        Execute music tool based on mode.

        Args:
            mode: Operation mode - 'list' to show available music, 'play' to play a music file.
            music_path: Path to the music file (required for play mode).

        Returns:
            List of music files (list mode) or status message (play mode).
        """
        if mode == "list":
            return await self._execute_list(**kwargs)
        elif mode == "play":
            return await self._execute_play(music_path=music_path, **kwargs)
        else:
            return f"Error: Invalid mode '{mode}'. Must be 'list' or 'play'."

    async def _execute_list(self, **kwargs: Any) -> str:
        """
        List all available music files in the media directory.

        Returns:
            Formatted string listing all music files found.
        """

        music_dir = Path.home() / ".nanobot" / "depends" / "music"
        # Supported audio formats
        audio_extensions = {".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a", ".wma"}

        # Find all music files
        music_files = []
        for file_path in music_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
                music_files.append(file_path)

        # Also check subdirectories
        for subdir in music_dir.iterdir():
            if subdir.is_dir():
                for file_path in subdir.rglob("*"):
                    if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
                        music_files.append(file_path)

        if not music_files:
            return "No music files found in the media directory."

        # Sort by name
        music_files.sort(key=lambda x: x.name.lower())

        # Format output
        result = f"Found {len(music_files)} music file(s):\n\n"
        for idx, file_path in enumerate(music_files, 1):
            size_mb = file_path.stat().st_size / (1024 * 1024)
            result += f"{idx}. {file_path.name} ({size_mb:.2f} MB)\n"
            result += f"   Path: {file_path}\n\n"

        return result.strip()

    async def _execute_play(self, music_path: str, **kwargs: Any) -> str:
        """
        Play a music file by sending it as media.

        Args:
            music_path: Path to the music file to play.

        Returns:
            Status message indicating success or error.
        """
        if not self._send_callback:
            return "Error: Message sending not configured"

        if not music_path:
            return "Error: music_path is required for play mode"

        try:
            # Resolve the music file path
            file_path = Path(music_path)

            # If it's not an absolute path, look in media directory
            if not file_path.is_absolute():
                media_dir = get_media_dir()
                file_path = media_dir / music_path

            # Check if file exists
            if not file_path.exists():
                return f"Error: Music file not found: {music_path}"

            # Check file extension
            valid_extensions = {".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a", ".wma"}
            if file_path.suffix.lower() not in valid_extensions:
                return (
                    f"Error: Unsupported audio format: {file_path.suffix}. "
                    f"Supported formats: {', '.join(valid_extensions)}"
                )
            mime_type = self._get_mime_type(str(file_path))
            with open(str(file_path), "rb") as f:
                audio_bytes = f.read()
            msg = OutboundMessage(
                channel=self._default_channel,
                chat_id=self._default_chat_id,
                content="",
                media=[audio_bytes],
                metadata={"msg_type": "audio", "audio_format": mime_type},
            )
            await self._send_callback(msg)
            return f"Playing: {file_path.name}"

        except Exception as e:
            return f"Error: {str(e)}"

    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type based on file extension."""
        ext = Path(file_path).suffix.lower()
        mime_types = {
            ".mp3": "audio/mp3",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
            ".wma": "audio/x-ms-wma",
        }
        return mime_types.get(ext, "audio/mp3")
