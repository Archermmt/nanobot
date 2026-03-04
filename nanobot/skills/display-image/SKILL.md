---
name: display-image
description: Display images to the frontend using the display_image tool. Use when: (1) User requests to see an image, (2) You need to show visual content, (3) User asks to display a specific image file. Do not use in CLI mode - only works with WebSocket channel.
metadata: {"nanobot":{"emoji":"🖼️"}}
---

# Display Image Skill

Display images to the frontend using the `display_image` tool. This skill reads image files from disk and sends them to the WebSocket channel for display.

## Features

- Display images to the frontend
- Support optional captions
- Support multiple image formats: PNG, JPG, JPEG, GIF, WEBP, BMP
- Automatic image loading from absolute paths

## Tools

This skill provides the following tool:

### `display_image`

Display an image to the frontend.

**Parameters**:
- `image_path` (string, required): Absolute path to the image file
- `caption` (string, optional): Optional caption to display with the image

## Examples

**Example - Display image with caption**:
```
<tool>display_image</tool>
<parameter name="image_path">/Users/archer/Downloads/screen.png
```

**Example - Display image without caption**:
```
<tool>display_image</tool>
<parameter name="image_path">/path/to/project/assets/logo.svg
```

**Example - Display chart with caption**:
```
<tool>display_image</tool>
<parameter name="image_path">/path/to/project/output/chart.png
```

## Usage

When users want to display images:

- "Show me this image" → Call `display_image` with `image_path: "/path/to/image.png"`
- "Display the screenshot" → Call `display_image` with `image_path: "..."`, optional `caption`
- "Can you show me the chart" → Call `display_image` with `image_path: "..."`, `caption: "..."`

Always use absolute paths for images. Convert relative paths and expand `~` to home directory before calling.

## Important Rules

1. **ALWAYS use display_image tool** - Never attempt to send raw image data
2. **Absolute paths only** - Convert all paths to absolute before calling
3. **WebSocket channel required** - This tool only works when WebSocket channel is active
4. **Do not use in CLI mode** - The frontend is required to display images
