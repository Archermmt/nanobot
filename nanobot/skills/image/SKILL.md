---
name: image
description: Unified tool for analyzing and displaying images (vision analysis, image display, and image editing with reference images).
metadata: {"nanobot":{"emoji":"🖼️"}}
---

# Image Tool

Unified tool for analyzing and displaying images. Supports four modes: vision analysis using multimodal LLM models, displaying images to users through the frontend, generating images from text prompts, and editing images based on reference images.

## Features

- Analyze images using multimodal LLM models (OCR, description, visual QA)
- Display images to users by sending them to the frontend
- Generate images from text prompts using AI models
- Support multiple image formats: PNG, JPG, JPEG, GIF, WEBP, BMP
- Base64 encoding for image processing and transmission

## Tools

This skill provides the following tool:

### `image`

Unified tool for image analysis, display, and generation.

**Parameters**:
- `mode` (string, required): The operation mode - `vision` for image analysis, `display` for showing images to users, `generate` for creating images from text prompts, `edit` for modifying images based on reference images
- `image_path` (string, required):
  - In vision/display/edit mode: Absolute path to the image file (e.g., "/Users/archer/Desktop/photo.png")
  - In generate mode: File name where the generated image will be saved. This parameter should contain few words which generalize the `text`
- `text` (string, optional):
  - In vision mode: User's request or question about the image (e.g., "Describe this image", "Extract text from this image")
  - In display mode: Caption to display with the image (appears above the image in the message box)
  - In generate mode: Text prompt describing the desired image content, style, and composition (supports Chinese and English, max 800 characters)
  - In edit mode: Description of how to modify the reference image (e.g., "Add a hat to the cat", "Change the background to beach")
- `ref_image` (string, optional):
  - Only used in generate mode for image-to-image generation
  - When you need to modify an existing image or create variations based on a reference, provide the absolute path to the reference image file
  - The model will generate a new image that maintains similar style, composition, or content from the reference image
  - Example: Use this when you want to change the style of an existing image, add/remove objects, or create similar images
  - Supported formats: PNG, JPG, JPEG, GIF, WEBP

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

**Example for generate - Create an image of a cute orange cat**:
```
<tool>image</tool>
<parameter name="mode">generate</parameter>
<parameter name="text">A sitting orange cat with happy expression</parameter>
<parameter name="image_path">sitting_orange_cat.png</parameter>
```

**Example for generate - Create a landscape painting**:
```
<tool>image</tool>
<parameter name="mode">generate</parameter>
<parameter name="text">A beautiful sunset over mountains in oil painting style</parameter>
<parameter name="image_path">sunset_painting_style.png</parameter>
```

**Example for edit - Change the color of the cat in cat.png to yellow**:
```
<tool>image</tool>
<parameter name="mode">generate</parameter>
<parameter name="text">Change the color of the cat in image to yellow</parameter>
<parameter name="image_path">cat_edit_to_yellow.png</parameter>
<parameter name="ref_image">cat.png</parameter>
```

**Example for edit - Put a hat to the head of cat in cat.png**:
```
<tool>image</tool>
<parameter name="mode">generate</parameter>
<parameter name="text">Put a hat to the head of cat in th image</parameter>
<parameter name="image_path">cat_edit_with_hat.png</parameter>
<parameter name="ref_image">cat.png</parameter>
```

## Important Rules

1. **ALWAYS use image tool** - Never attempt direct LLM API calls
2. **Absolute paths only** - Convert all paths to absolute before calling
3. **Keep text unchanged in generate mode** - Do not change the text when generating image
