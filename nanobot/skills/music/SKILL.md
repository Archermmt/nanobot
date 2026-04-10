---
name: music
description: Manage and play music files. Supports two modes, list for list all available music files in the media directory; and play for play a specific music file by sending it to the user.
metadata: {"nanobot":{"emoji":"🖼️"}}
---

## Parameters
- **mode**: Operation mode (required). Must be "list" or "play".
- **music_path**: Path to the music file (required for play mode).

## Usage Examples
1. List available music:
```
{"name": "music", "arguments": {"mode": "list"}}
```

2. Play a music file:
```
{"name": "music", "arguments": {"mode": "play", "music_path": "song.mp3"}}
```

## Notes
- Music files must be in the media directory (~/.nanobot/media).
- Supported formats: MP3, WAV, OGG, AAC, FLAC, M4A.
