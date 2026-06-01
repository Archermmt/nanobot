---
name: media
description: Master guide for all media operations including images, audio, and videos. Provides unified access to list, display, generate, and edit media files using the media tool with appropriate media_type parameter.
metadata: {"nanobot":{"emoji":"🎨"}}
---

# Media Skill - Master Guide

This is the master guide for all media-related operations in nanobot. It provides a unified interface for working with images, audio, and video files through the `media` tool.

## Overview

The media system supports three types of media:
- **Images** 🖼️ - Listing, display, generation, and editing
- **Audio** 🎵 - Listing and playback
- **Videos** 🎬 - Listing, display, generation, and editing

All media operations use the same `media` tool but with different `media_type` parameters:
- `"image"` for image operations
- `"audio"` for audio operations
- `"video"` for video operations

## Quick Decision Guide

When you need to work with media, follow this decision tree:

### 1. What type of media?
- **Image** → Use `media_type="image"`, see [Image Skill](./image/SKILL.md)
- **Audio** → Use `media_type="audio"`, see [Music Skill](./music/SKILL.md)
- **Video** → Use `media_type="video"`, see [Video Skill](./video/SKILL.md)

### 2. What operation?

#### For Images (`media_type="image"`):
- **List available images**: `mode="list"`
- **Show image to user**: `mode="display"`
- **Create image from text**: `mode="generate"`
- **Modify existing image**: `mode="edit"`

#### For Audio (`media_type="audio"`):
- **List available audio files**: `mode="list"`
- **Play audio to user**: `mode="display"`

#### For Videos (`media_type="video"`):
- **List available videos**: `mode="list"`
- **Show video to user**: `mode="display"`
- **Create video from text**: `mode="generate"`
- **Modify existing video**: `mode="edit"` (currently not supported)

## Common Workflow Patterns

### Pattern 1: List and Select
```json
// Step 1: List available media files
{"name": "media", "arguments": {"media_type": "image", "mode": "list"}}

// Step 2: After user selects a file, display it
{"name": "media", "arguments": {"media_type": "image", "mode": "display", "media_path": "/path/to/selected.png"}}
```

### Pattern 2: Generate and Display
```json
// Step 1: Generate media
{"name": "media", "arguments": {"media_type": "image", "mode": "generate", "prompt": "A beautiful sunset", "media_path": "sunset.png"}}

// Step 2: Always display the generated media
{"name": "media", "arguments": {"media_type": "image", "mode": "display", "media_path": "/absolute/path/to/sunset.png"}}
```

## Important Rules

1. **Always use the correct media_type**:
   - Never mix up media types (e.g., don't use `media_type="image"` for audio files)

2. **Use absolute paths**:
   - `display`, and `edit` modes, always convert paths to absolute paths
   - For `generate` mode, use relative filenames

3. **Display after generation**:
   - After generating images or videos, ALWAYS call `display` mode to show the result to the user

4. **Read detailed skill documentation**:
   - For specific parameter details and advanced usage, read the individual skill files:
     - [Image Skill](./image/SKILL.md) - Complete guide for image operations
     - [Music Skill](./music/SKILL.md) - Complete guide for audio operations
     - [Video Skill](./video/SKILL.md) - Complete guide for video operations

5. **Supported formats**:
   - Images: PNG, JPG, JPEG, GIF, WEBP, BMP, SVG
   - Audio: MP3, WAV, OGG, AAC, FLAC, M4A, WMA
   - Videos: MP4, AVI, MOV, MKV, WEBM

## Examples by Use Case

### "Show me a picture of X"
→ Use image generate + display
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "generate", "prompt": "X", "media_path": "x_image.png"}}
{"name": "media", "arguments": {"media_type": "image", "mode": "display", "media_path": "/absolute/path/x_image.png"}}
```

### "Play some music"
→ First list available audio, then display selected
```json
{"name": "media", "arguments": {"media_type": "audio", "mode": "list"}}
// After selection:
{"name": "media", "arguments": {"media_type": "audio", "mode": "display", "media_path": "/path/to/song.mp3"}}
```

### "Create a video of X"
→ Use video generate + display
```json
{"name": "media", "arguments": {"media_type": "video", "mode": "generate", "prompt": "X", "media_path": "x_video.mp4"}}
{"name": "media", "arguments": {"media_type": "video", "mode": "display", "media_path": "/absolute/path/x_video.mp4"}}
```

## When to Read Detailed Documentation

Read the specific skill documentation when you need:
- Advanced parameters (resolution, duration, negative prompts, etc.)
- Specific format requirements
- Detailed examples for complex operations
- Mode-specific constraints and best practices

**Remember**: This master guide helps you choose the right tool and mode. For detailed implementation, always refer to the specific skill documentation.

## Important Rules

1. **Single Display Call Per Conversation**: During a single conversation turn, you can call the `display` mode AT MOST ONCE to send media content to the user

2. **Display Only First Item from List**: When using `mode="list"` and multiple media files are available (images, videos, or audio), display or play ONLY the first item. Do not display or play multiple media files in a single conversation turn
