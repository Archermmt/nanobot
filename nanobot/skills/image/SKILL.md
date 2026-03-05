---
name: image
description: Unified tool for analyzing and displaying images (vision analysis and image display).
metadata: {"nanobot":{"emoji":"🖼️"}}
---

# Image Tool

Unified tool for analyzing and displaying images. Supports two modes: vision analysis using multimodal LLM models and displaying images to users through the frontend.

## Features

- Analyze images using multimodal LLM models (OCR, description, visual QA)
- Display images to users by sending them to the frontend
- Support multiple image formats: PNG, JPG, JPEG, GIF, WEBP, BMP
- Base64 encoding for image processing and transmission

## Tools

This skill provides the following tool:

### `image`

Unified tool for image analysis and display.

**Parameters**:
- `mode` (string, required): The operation mode - `vision` for image analysis, `display` for showing images to users
- `image_path` (string, required): Absolute path to the image file (e.g., "/Users/archer/Desktop/photo.png")
- `text` (string, optional):
  - In vision mode: User's request or question about the image (e.g., "Describe this image", "Extract text from this image")
  - In display mode: Caption to display with the image (appears above the image in the message box)

## Examples

**Example for vision - Describe an image at image.png**:
```
<tool>image</tool>
<parameter name="mode">vision</parameter>
<parameter name="text">Describe this image</parameter>
<parameter name="image_path">image.png</parameter>
```

**Example for vision - Extract text from image image.jpeg**:
```
<tool>image</tool>
<parameter name="mode">vision</parameter>
<parameter name="text">Get words in this image</parameter>
<parameter name="image_path">image.jpeg</parameter>
```

**Example for vision - How many birds in image image.png**:
```
<tool>image</tool>
<parameter name="mode">vision</parameter>
<parameter name="text">How many birds in image?</parameter>
<parameter name="image_path">image.png</parameter>
```

**Example for display - Display image at image.png with title "The image"**:
```
<tool>image</tool>
<parameter name="mode">display</parameter>
<parameter name="text">The image</parameter>
<parameter name="image_path">image.png</parameter>
```

**Example for display - Display image at image.png**:
```
<tool>image</tool>
<parameter name="mode">display</parameter>
<parameter name="image_path">image.png</parameter>
```

## Important Rules

1. **ALWAYS use image tool** - Never attempt direct LLM API calls
2. **Absolute paths only** - Convert all paths to absolute before calling
