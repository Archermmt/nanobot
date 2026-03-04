---
name: image-vision
description: |
  Analyze images using the image_vision tool. Use when: (1) User asks to describe/analyze image content, (2) User requests OCR/text extraction, (3) User asks questions about visual content, (4) User provides image paths for interpretation. NEVER call LLM APIs directly - ALWAYS use the image_vision tool with an appropriate multimodal model based on current mode's price tier.
---

# Image Vision Skill

Analyze images using the `image_vision` tool. This skill automatically selects the appropriate multimodal model based on your current mode's price tier.

## Quick Start

```python
# Describe an image
image_vision(text="Describe this image", images=["/path/to/image.png"])

# Extract text (OCR)
image_vision(text="Extract all text from this image", images=["/path/to/doc.png"])

# Answer questions
image_vision(text="How many cats are in this photo?", images=["/path/to/cats.jpg"], model_id="moonshot/kimi-k2.5:cloud")
```

## Model Selection Guide

The skill automatically selects a multimodal model based on your current mode's price tier, use `agent_mode` to find all available models

## Workflow

1. **Extract image paths** from user request
   - Convert relative paths to absolute paths
   - Expand `~` to home directory
   - Check media folder: `~/.nanobot/media/`

2. **Select appropriate model** based on current mode's price tier
   - multimodal mode: Use mode-appropriate model
   - common/coding mode: Use free/medium tier multimodal model

3. **Call image_vision tool** with:
   - `text`: User's question/request
   - `images`: List of absolute image paths
   - `model_id`: Selected multimodal model

4. **Return results** to user

## Supported Formats

PNG, JPG, JPEG, GIF, WEBP, BMP

## Parameters Reference

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| text | string | Yes | Question or request about the image |
| images | string[] | Yes | Absolute paths to image files |
| model_id | string | No | Vision model to use (auto-selected if omitted) |

## Examples

**User**: "Describe this image ~/Downloads/photo.png"

**Action**:
```python
image_vision(
    text="Describe this image",
    images=["/Users/archer/Downloads/photo.png"],
    model_id="openai/kimi-k2.5:cloud"  # free tier multimodal model
)
```

**User**: "Get words in this image /tmp/document.jpg"

**Action**:
```python
image_vision(
    text="Get words in this image",
    images=["/tmp/document.jpg"],
    model_id="openai/kimi-k2.5:cloud"
)
```

**User**: "Is there a cat in this image？"

**Action**:
```python
image_vision(
    text="Is there a cat in this image?",
    images=["/path/to/image.png"],
    model_id="openai/kimi-k2.5:cloud"
)
```

## Important Rules

1. **ALWAYS use image_vision tool** - Never attempt direct LLM API calls
2. **Select appropriate model** - Use multimodal model based on current mode's price tier
3. **Absolute paths only** - Convert all paths to absolute before calling
4. **One tool call** - Make a single image_vision call with all relevant images
