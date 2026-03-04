---
name: display-image
description: |
  Display image to frontend, do not use this in cli mode.
---

# Display Image Skill

## Overview

This skill provides a tool to display images directly in the message box through WebSocket channel. The tool reads image files, encodes them as base64, and sends them to the frontend for display.

## Tool: display_image

Display an image to the user by reading it from disk and sending it to the frontend for display in the message box.

### Parameters

- `image_path` (string, required): Path to the image file to display. Can be an absolute or relative path. Supported formats: PNG, JPG, JPEG, GIF, WEBP, BMP.
- `caption` (string, optional): Optional caption to display with the image. This text will appear above the image in the message box.

### Usage Example

```python
# Display an image with a caption
await display_image(image_path="/path/to/image.png", caption="Here is the image you requested")

# Display an image without a caption
await display_image(image_path="/path/to/image.jpg")
```

### Implementation

The tool is implemented in `nanobot/agent/tools/image.py` as the `DisplayImageTool` class.

### Frontend Support

The frontend automatically detects and displays images sent through the `media` field with `msg_type: "image"` or image file types. Images are displayed with click-to-expand functionality.

## How It Works

1. The tool reads the image file from disk
2. Encodes the image as base64
3. Creates an `OutboundMessage` with the image as media
4. Sends the message through the WebSocket channel
5. The frontend receives the message and displays the image

## Related Skills

- `image-vision`: Analyze and describe images using multimodal LLM models
- `memory`: Two-layer memory system with grep-based recall
