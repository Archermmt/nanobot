---
name: display-image
description: |
  Display images to the frontend using the display_image tool. Use when: (1) User requests to see an image, (2) You need to show visual content, (3) User asks to display a specific image file. Do not use in CLI mode - only works with WebSocket channel.
---

# Display Image Skill

Display images to the frontend using the `display_image` tool. This skill reads image files from disk and sends them to the WebSocket channel for display.

## Quick Start

```python
# Display an image with a caption
display_image(image_path="/path/to/image.png", caption="Here is the image you requested")

# Display an image without a caption
display_image(image_path="/path/to/image.jpg")
```

## Workflow

1. **Extract image paths** from user request
   - Convert relative paths to absolute paths
   - Expand `~` to home directory
   - Check media folder: `~/.nanobot/media/`

2. **Call display_image tool** with:
   - `image_path`: Absolute path to image file
   - `caption`: Optional caption to display above the image

3. **Frontend displays** the image automatically

## Supported Formats

PNG, JPG, JPEG, GIF, WEBP, BMP

## Parameters Reference

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| image_path | string | Yes | Absolute path to the image file |
| caption | string | No | Optional caption to display with the image |

## Examples

**User**: "Show me the screenshot I saved at ~/Downloads/screen.png"

**Action**:
```python
display_image(
    image_path="/Users/archer/Downloads/screen.png",
    caption="Screenshot you requested"
)
```

**User**: "Display the logo from ./assets/logo.svg"

**Action**:
```python
display_image(
    image_path="/path/to/project/assets/logo.svg"
)
```

**User**: "Can you show me the chart we generated?"

**Action**:
```python
display_image(
    image_path="/path/to/project/output/chart.png",
    caption="Generated chart"
)
```

## Important Rules

1. **ALWAYS use display_image tool** - Never attempt to send raw image data
2. **Absolute paths only** - Convert all paths to absolute before calling
3. **WebSocket channel required** - This tool only works when WebSocket channel is active
4. **Do not use in CLI mode** - The frontend is required to display images
- `memory`: Two-layer memory system with grep-based recall
