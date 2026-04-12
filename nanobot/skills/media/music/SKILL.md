---
name: music
description: Manage and play audio files using the media tool. Supports two modes: list for listing all available audio files in the media directory, and display for playing a specific audio file by sending it to the user.
metadata: {"nanobot":{"emoji":"🎵"}}
---

# Music Skill

Unified tool for managing and playing audio files using the `media` tool with `media_type="audio"`. Supports two modes: listing available audio files and playing audio files to users.

## Features

- List all available audio files in the media directory
- Play audio files by sending them to users through WebSocket channel
- Support multiple audio formats: MP3, WAV, OGG, AAC, FLAC, M4A, WMA
- Base64 encoding for audio processing and transmission

## Tool Parameters

The music skill uses the `media` tool. When using this tool, the `media_type` parameter **must** be set to `"audio"`.

### Required Parameters
- `media_type` (string): Must be `"audio"` for all audio operations.
- `mode` (string): The operation mode.
  - `list`: List all available audio files in the media directory.
  - `display`: Play an audio file by sending it as media.
- `media_path` (string):
  - In `display` mode: Path to the audio file to play.

## Usage Examples

### List Mode
List all available audio files:
```json
{"name": "media", "arguments": {"media_type": "audio", "mode": "list"}}
```

### Display Mode (Play)
Play an audio file:
```json
{"name": "media", "arguments": {"media_type": "audio", "mode": "display", "media_path": "/path/to/song.mp3"}}
```

## Important Rules

1. **ALWAYS use the `media` tool** with `media_type="audio"` for all audio operations. Never attempt direct LLM API calls.
2. **Music playback must ONLY use the `media` tool** - Do NOT call system music players or use the `exec` tool for playing music.
3. **Absolute paths only** - Convert all paths to absolute before calling the tool in `display` mode.
4. **Supported formats** - Only supported audio formats can be played: MP3, WAV, OGG, AAC, FLAC, M4A, WMA.
5. **Single Display Call Per Conversation**: During a single conversation turn, you can call the `display` mode AT MOST ONCE to send media content to the user
