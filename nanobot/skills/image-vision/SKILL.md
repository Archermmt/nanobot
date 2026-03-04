---
name: image-vision
description: Analyze images using the image_vision tool. Use when: (1) User asks to describe/analyze image content, (2) User requests OCR/text extraction, (3) User asks questions about visual content, (4) User provides image paths for interpretation. NEVER call LLM APIs directly - ALWAYS use the image_vision tool with an appropriate multimodal model based on current mode's price tier.
metadata: {"nanobot":{"emoji":"👁️"}}
---

# Image Vision Skill

Analyze images using the `image_vision` tool. Before using the tool, choose a multimodal model via `agent_mode` tool, make sure the multimodal model in same price tier with current model.

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
- `model_id` (string, optional): Vision model to use (auto-selected if omitted)

## Examples

**Example - Describe an image**:
```
<tool>image_vision</tool>
<parameter name="text">Describe this image</parameter>
<parameter model_id="text">openai/kimi-k2.5:cloud</parameter>
```

**Example - Extract text from image**:
```
<tool>image_vision</tool>
<parameter name="text">Get words in this image</parameter>
<parameter model_id="text">openai/kimi-k2.5:cloud</parameter>
```

**Example - Answer question about image**:
```
<tool>image_vision</tool>
<parameter name="text">Is there a cat in this image?</parameter>
<parameter model_id="text">openai/kimi-k2.5:cloud</parameter>
```

## Important Rules

1. **ALWAYS use image_vision tool** - Never attempt direct LLM API calls
2. **Select appropriate model** - Use multimodal model based on current mode's price tier
3. **Absolute paths only** - Convert all paths to absolute before calling
4. **One tool call** - Make a single image_vision call with all relevant images
