---
name: media
description: Master guide for all media operations including images, audio, and videos. Provides unified access to list, display, generate, and edit media files using the media tool with appropriate media_type parameter.
metadata: {"nanobot":{"emoji":"🎨"}}
---

# Media Skill - Master Guide

This is the master guide for all media-related operations in nanobot. It provides a unified interface for working with images, audio, and video files through the `media` tool.

## Overview

The media system supports three types of media:
- **Images** 🖼️ - Listing, display, generation, editing, and analysis
- **Audio** 🎵 - Listing, playback, and analysis
- **Videos** 🎬 - Listing, display, generation, and analysis

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
- **Analyze image content**: `mode="analyze"` (OCR, description, visual QA)

#### For Audio (`media_type="audio"`):
- **List available audio files**: `mode="list"`
- **Play audio to user**: `mode="display"`
- **Analyze audio content**: `mode="analyze"` (transcription, description)

#### For Videos (`media_type="video"`):
- **List available videos**: `mode="list"`
- **Show video to user**: `mode="display"`
- **Create video from text**: `mode="generate"`
- **Analyze video content**: `mode="analyze"` (description, action recognition)

## Important Rules

**Media Display Priority**: When users request to show/display media (images, videos, audio), **always** follow this priority order:
1. **First**: Use `list` mode to find existing media files that match the request
2. **Second**: Use `display` mode to show the found media file
3. **Last resort**: Only use `generate` mode if no suitable existing media is found

**Example workflow for "Show me a picture of sunset":**
```json
// Step 1: List existing images
{"name": "media", "arguments": {"media_type": "image", "mode": "list"}}

// Step 2: If matching file found (e.g., sunset.jpg)
{"name": "media", "arguments": {"media_type": "image", "mode": "display", "media_path": "/path/to/sunset.jpg"}}

// Step 3: ONLY if no matching file exists, then generate
{"name": "media", "arguments": {"media_type": "image", "mode": "generate", "prompt": "sunset", "media_path": "sunset_generated.png"}}
```

This prevents unnecessary generation when suitable media already exists.

1. **Always use the correct media_type**:
   - Never mix up media types (e.g., don't use `media_type="image"` for audio files)

2. **Use absolute paths**:
   - `display`, and `edit` modes, always convert paths to absolute paths
   - For `generate` mode, use relative filenames

3. **Read detailed skill documentation**:
   - For specific parameter details and advanced usage, read the individual skill files:
     - [Image Skill](./image/SKILL.md) - Complete guide for image operations
     - [Music Skill](./music/SKILL.md) - Complete guide for audio operations
     - [Video Skill](./video/SKILL.md) - Complete guide for video operations

4. **Supported formats**:
   - Images: PNG, JPG, JPEG, GIF, WEBP, BMP, SVG
   - Audio: MP3, WAV, OGG, AAC, FLAC, M4A, WMA
   - Videos: MP4, AVI, MOV, MKV, WEBM

5. **Analyze mode uses multimodal LLM**:
   - Analyze mode sends media files to the provider for AI-powered analysis
   - Supports custom prompts/questions for targeted analysis
   - Works with all media types (images, audio, videos)
   - Examples: "What objects are in this image?", "Transcribe this audio", "Describe the actions in this video"

## When to Read Detailed Documentation

Read the specific skill documentation when you need:
- Advanced parameters (resolution, duration, negative prompts, etc.)
- Specific format requirements
- Detailed examples for complex operations
- Mode-specific constraints and best practices

**Remember**: This master guide helps you choose the right tool and mode. For detailed implementation, always refer to the specific skill documentation.
