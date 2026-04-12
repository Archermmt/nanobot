---
name: media
description: Master guide for all media operations including images, audio, videos, and HTML. Provides unified access to analyze, display, generate, edit media files, and render HTML content using the media tool with appropriate media_type parameter.
metadata: {"nanobot":{"emoji":"🎨"}}
---

# Media Skill - Master Guide

This is the master guide for all media-related operations in nanobot. It provides a unified interface for working with images, audio, and video files through the `media` tool.

## Overview

The media system supports five types of media:
- **Images** 🖼️ - Analysis, display, generation, and editing
- **Audio** 🎵 - Listing and playback
- **Videos** 🎬 - Analysis, display, generation, and editing
- **HTML** 🌐 - Listing and rendering HTML content
- **3D Mesh** 🧊 - Listing and displaying 3D mesh models

All media operations use the same `media` tool but with different `media_type` parameters:
- `"image"` for image operations
- `"audio"` for audio operations
- `"video"` for video operations
- `"html"` for HTML content rendering
- `"mesh"` for 3D mesh model display

## Quick Decision Guide

When you need to work with media, follow this decision tree:

### 1. What type of media?
- **Image** → Use `media_type="image"`, see [Image Skill](../image/SKILL.md)
- **Audio** → Use `media_type="audio"`, see [Music Skill](../music/SKILL.md)
- **Video** → Use `media_type="video"`, see [Video Skill](../video/SKILL.md)
- **HTML** → Use `media_type="html"`, see details below
- **3D Mesh** → Use `media_type="mesh"`, see details below

### 2. What operation?

#### For Images (`media_type="image"`):
- **List available images**: `mode="list"`
- **Analyze/describe an image**: `mode="vision"`
- **Show image to user**: `mode="display"`
- **Create image from text**: `mode="generate"`
- **Modify existing image**: `mode="edit"`

#### For Audio (`media_type="audio"`):
- **List available audio files**: `mode="list"`
- **Play audio to user**: `mode="display"`

#### For Videos (`media_type="video"`):
- **List available videos**: `mode="list"`
- **Analyze/describe a video**: `mode="vision"`
- **Show video to user**: `mode="display"`
- **Create video from text**: `mode="generate"`
- **Modify existing video**: `mode="edit"` (currently not supported)

#### For HTML (`media_type="html"`):
- **List available HTML files**: `mode="list"`
- **Render HTML content**: `mode="display"`

#### For 3D Mesh (`media_type="mesh"`):
- **List available mesh files**: `mode="list"`
- **Display 3D mesh model**: `mode="display"` (supports STL, 3MF, OBJ, FBX, GLTF, GLB formats with textures)

## Common Workflow Patterns

### Pattern 1: List and Select
```json
// Step 1: List available media files
{"name": "media", "arguments": {"media_type": "image", "mode": "list"}}

// Step 2: After user selects a file, display or analyze it
{"name": "media", "arguments": {"media_type": "image", "mode": "display", "media_path": "/path/to/selected.png"}}
```

### Pattern 2: Generate and Display
```json
// Step 1: Generate media
{"name": "media", "arguments": {"media_type": "image", "mode": "generate", "prompt": "A beautiful sunset", "media_path": "sunset.png"}}

// Step 2: Always display the generated media
{"name": "media", "arguments": {"media_type": "image", "mode": "display", "media_path": "/absolute/path/to/sunset.png"}}
```

### Pattern 3: Analyze Media
```json
// Analyze image/video content
{"name": "media", "arguments": {"media_type": "image", "mode": "vision", "prompt": "Describe what you see", "media_path": "/path/to/image.png"}}
```

## Important Rules

1. **Always use the correct media_type**:
   - Never mix up media types (e.g., don't use `media_type="image"` for audio files)

2. **Use absolute paths**:
   - For `vision`, `display`, and `edit` modes, always convert paths to absolute paths
   - For `generate` mode, use relative filenames

3. **Display after generation**:
   - After generating images or videos, ALWAYS call `display` mode to show the result to the user

4. **Read detailed skill documentation**:
   - For specific parameter details and advanced usage, read the individual skill files:
     - [Image Skill](../image/SKILL.md) - Complete guide for image operations
     - [Music Skill](../music/SKILL.md) - Complete guide for audio operations
     - [Video Skill](../video/SKILL.md) - Complete guide for video operations

5. **Supported formats**:
   - Images: PNG, JPG, JPEG, GIF, WEBP, BMP, SVG
   - Audio: MP3, WAV, OGG, AAC, FLAC, M4A, WMA
   - Videos: MP4, AVI, MOV, MKV, WEBM
   - HTML: HTML, HTM
   - 3D Mesh: STL, 3MF, OBJ, FBX, GLTF, GLB (with texture support via companion directories)

## Examples by Use Case

### "Show me a picture of X"
→ Use image generate + display
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "generate", "prompt": "X", "media_path": "x_image.png"}}
{"name": "media", "arguments": {"media_type": "image", "mode": "display", "media_path": "/absolute/path/x_image.png"}}
```

### "What's in this image?"
→ Use image vision
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "vision", "prompt": "Describe this image", "media_path": "/path/to/image.png"}}
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

### "Show me an HTML page"
→ List available HTML files, then display selected
```json
{"name": "media", "arguments": {"media_type": "html", "mode": "list"}}
// After selection:
{"name": "media", "arguments": {"media_type": "html", "mode": "display", "media_path": "/path/to/page.html"}}
```

### "Show me a 3D model"
→ List available mesh files, then display selected
```json
{"name": "media", "arguments": {"media_type": "mesh", "mode": "list"}}
// After selection:
{"name": "media", "arguments": {"media_type": "mesh", "mode": "display", "media_path": "/path/to/model.stl"}}
```

**Note**: For mesh files with textures, place texture images in a directory named `{filename}_textures/` next to the mesh file.

## When to Read Detailed Documentation

Read the specific skill documentation when you need:
- Advanced parameters (resolution, duration, negative prompts, etc.)
- Specific format requirements
- Detailed examples for complex operations
- Mode-specific constraints and best practices

**Remember**: This master guide helps you choose the right tool and mode. For detailed implementation, always refer to the specific skill documentation.

## Important Rules

1. **Single Display Call Per Conversation**: During a single conversation turn, you can call the `display` mode AT MOST ONCE to send media content to the user
