---
name: image-vision
description: Analyze images using the image_vision tool. Use when: (1) User asks to describe/analyze image content, (2) User requests OCR/text extraction, (3) User asks questions about visual content, (4) User provides image paths for interpretation. NEVER call LLM APIs directly - ALWAYS use the image_vision tool with an appropriate multimodal model based on current mode's price tier.
metadata: {"nanobot":{"emoji":"👁️"}}
---

# Image Vision Skill

Analyze images using the `image_vision` tool.

## Features

- Describe and analyze image content
- Extract text from images (OCR)
- Answer questions about visual content
- Support multiple image formats: PNG, JPG, JPEG, GIF, WEBP, BMP

## Tools

This skill provides the following tool:

### `image_vision`

Analyze images using computer vision.

**Parameters**:
- `text` (string, required): Question or request about the image
- `images` (string[], required): Absolute paths to image files

## Examples

**Example - Describe an image at image.png**:
```
<tool>image_vision</tool>
<parameter name="text">Describe this image</parameter>
<parameter name="images">["image.png"]</parameter>
```

**Example - Extract text from image image.jpeg**:
```
<tool>image_vision</tool>
<parameter name="text">Get words in this image</parameter>
<parameter name="images">["image.jpeg"]</parameter>
```

**Example - How many birds in image image.png**:
```
<tool>image_vision</tool>
<parameter name="text">How many birds in image?</parameter>
<parameter name="images">["image.png"]</parameter>
```

## Important Rules

1. **ALWAYS use image_vision tool** - Never attempt direct LLM API calls
2. **Select appropriate model** - Use multimodal model based on current mode's price tier
3. **Absolute paths only** - Convert all paths to absolute before calling
4. **One tool call** - Make a single image_vision call with all relevant images
