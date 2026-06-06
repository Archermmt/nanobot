---
name: image
description: Unified tool for listing, displaying, generating, editing, and analyzing images. Supports five modes: list for showing available images, display for showing images to users, generate for creating images from text prompts, edit for modifying existing images based on reference images, and analyze for AI-powered image analysis using multimodal LLM.
metadata: {"nanobot":{"emoji":"🖼️"}}
---

# Image Skill

Unified tool for listing, displaying, generating, editing, and analyzing images using the `media` tool with `media_type="image"`. Supports five modes: list, display, image generation from text prompts, editing images with reference images, and AI-powered image analysis.

## Features

- List all available image files in the media directory
- Display images to users by sending them to the frontend
- Generate images from text prompts using AI models
- Edit images based on reference images and text prompts
- Analyze images using multimodal LLM (OCR, description, visual QA)
- Support multiple image formats: PNG, JPG, JPEG, GIF, WEBP, BMP, SVG
- Base64 encoding for image processing and transmission

## Tool Parameters

The image skill uses the `media` tool. When using this tool, the `media_type` parameter **must** be set to `"image"`.

### Required Parameters
- `media_type` (string): Must be `"image"` for all image operations.
- `mode` (string): The operation mode.
  - `list`: List all available image files in the media directory.
  - `display`: Show an image to the user.
  - `generate`: Create an image from a text prompt.
  - `edit`: Modify an existing image based on a text prompt and a reference image.
  - `analyze`: Analyze image content using multimodal LLM (OCR, object detection, visual QA).
- `media_path` (string):
  - In `display`/`edit` mode: Absolute path to the image file.
  - In `generate` mode: File name where the generated image will be saved.

### Optional Parameters
- `prompt` (string):
  - In `display` mode: Caption to display with the image.
  - In `generate` mode: Text prompt describing the desired image content (max 800 characters).
  - In `edit` mode: Description of how to modify the reference image (e.g., "Add a hat to the cat").
  - In `analyze` mode: Analysis question or instruction (e.g., "What objects are in this image?", "Read the text in this image", "Describe the scene").
- `ref_media` (string):
  - In `edit` mode: Absolute path to the reference image file that will be modified. Must exist locally.
  - In `analyze` mode: Optional absolute path to the image file if not using `media_path`.
- `size` (string): [Generate mode] Output resolution, e.g., "1024*1024". Default is "1024*1024".
- `negative_prompt` (string): [Generate mode] Negative prompt describing what should NOT appear.
- `count` (integer): [Generate mode] Number of images to generate (1-6). Default is 1.
- `prompt_extend` (boolean): [Generate mode] Enable AI-powered prompt enhancement. Default is true.
- `watermark` (boolean): [Generate mode] Add watermark. Default is false.

## Usage Examples

### List Mode
List all available images:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "list"}}
```

### Display Mode
Display an image:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "display", "media_path": "/path/to/image.png"}}
```

### Generate Mode
Create an image of a cute orange cat:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "generate", "prompt": "A sitting orange cat with happy expression", "media_path": "sitting_orange_cat.png"}}
```

Create a landscape painting:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "generate", "prompt": "A beautiful sunset over mountains in oil painting style", "media_path": "sunset_painting_style.png"}}
```

### Edit Mode
Change the color of the cat in `cat.png` to yellow:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "edit", "prompt": "Change the color of the cat in image to yellow", "media_path": "cat_edit_to_yellow.png", "ref_media": "/path/to/cat.png"}}
```

Put a hat on the cat in `cat.png`:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "edit", "prompt": "Put a hat to the head of cat in the image", "media_path": "cat_edit_with_hat.png", "ref_media": "/path/to/cat.png"}}
```

### Analyze Mode
Analyze what's in an image:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "analyze", "media_path": "/path/to/image.jpg", "prompt": "What objects are in this image?"}}
```

Perform OCR on an image:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "analyze", "media_path": "/path/to/document.jpg", "prompt": "Read all the text in this image"}}
```

Describe a scene:
```json
{"name": "media", "arguments": {"media_type": "image", "mode": "analyze", "media_path": "/path/to/scene.jpg", "prompt": "Describe the scene in detail, including colors, objects, and atmosphere"}}
```

## Important Rules

1. **ALWAYS use the `media` tool** with `media_type="image"` for all image operations. Never attempt direct LLM API calls.
2. **Absolute paths only** - Convert all paths to absolute before calling the tool in `display` or `edit` modes.
3. **Keep text unchanged in generate mode** - Do not change the `prompt` when generating an image.
