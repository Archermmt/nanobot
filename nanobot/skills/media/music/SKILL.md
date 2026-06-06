---
name: music
description: Manage, play, and analyze audio files using the media tool. Supports three modes: list for listing all available audio files in the media directory, display for playing a specific audio file by sending it to the user, and analyze for AI-powered audio analysis using multimodal LLM (transcription, description).
metadata: {"nanobot":{"emoji":"🎵"}}
---

# Music Skill

Unified tool for managing, playing, and analyzing audio files using the `media` tool with `media_type="audio"`. Supports three modes: listing available audio files, playing audio files to users, and AI-powered audio analysis.

## Features

- List all available audio files in the media directory
- Play audio files by sending them to users through WebSocket channel
- Analyze audio content using multimodal LLM (transcription, description)
- Support multiple audio formats: MP3, WAV, OGG, AAC, FLAC, M4A, WMA
- Base64 encoding for audio processing and transmission

## Tool Parameters

The music skill uses the `media` tool. When using this tool, the `media_type` parameter **must** be set to `"audio"`.

### Required Parameters
- `media_type` (string): Must be `"audio"` for all audio operations.
- `mode` (string): The operation mode.
  - `list`: List all available audio files in the media directory.
  - `display`: Play an audio file by sending it as media.
  - `analyze`: Analyze audio content using multimodal LLM (transcription, sound recognition).
- `media_path` (string):
  - In `display` mode: Path to the audio file to play.
  - In `analyze` mode: Path to the audio file to analyze.

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

### Analyze Mode
Transcribe speech in an audio file:
```json
{"name": "media", "arguments": {"media_type": "audio", "mode": "analyze", "media_path": "/path/to/speech.mp3", "prompt": "Transcribe what is being said in this audio"}}
```

Describe the sounds in an audio file:
```json
{"name": "media", "arguments": {"media_type": "audio", "mode": "analyze", "media_path": "/path/to/ambient.mp3", "prompt": "What sounds are present in this audio? Describe the environment."}}
```

Identify music elements:
```json
{"name": "media", "arguments": {"media_type": "audio", "mode": "analyze", "media_path": "/path/to/music.mp3", "prompt": "What instruments and musical elements are in this audio?"}}
```

## Important Rules

1. **ALWAYS use the `media` tool** with `media_type="audio"` for all audio operations. Never attempt direct LLM API calls.
2. **Music playback must ONLY use the `media` tool** - Do NOT call system music players or use the `exec` tool for playing music.
3. **Absolute paths only** - Convert all paths to absolute before calling the tool in `display` mode.
4. **Supported formats** - Only supported audio formats can be played: MP3, WAV, OGG, AAC, FLAC, M4A, WMA.
