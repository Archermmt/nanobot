---
name: video
description: Unified tool for analyzing and displaying videos (vision analysis, video display, video generation from text prompts, and editing videos with reference videos).
metadata: {"nanobot":{"emoji":"🎬"}}
---

# Video Tool

Unified tool for analyzing and displaying videos. Supports four modes: vision analysis using multimodal LLM models, displaying videos to users through the frontend, generating videos from text prompts, and editing videos based on reference videos.

## Features

- Generate videos from text descriptions using AI
- Support for multi-shot narrative with timestamp control
- Customizable resolution (720P, 1080P) and aspect ratios
- Optional audio integration
- Automatic background music generation
- Negative prompts to exclude unwanted elements
- Watermark option

## Tools

This skill provides the following tool:

### `video`

Generate videos from text prompts using DashScope Wanxiang API.

**Parameters**:
- `prompt` (string, required): Text prompt describing the desired video content, style, and composition. Supports Chinese and English. For wan2.7-t2v model: max 5000 characters. Can include multi-shot narratives with timestamps (e.g., "Shot 1 [0-3s] Wide shot: Rainy street. Shot 2 [3-6s] Medium shot: Person enters building.").
- `video_path` (string, required): File name where the generated video will be saved in the media directory (~/.nanobot/media/). Will automatically add .mp4 extension if not present. Example: "cat_running.mp4"
- `resolution` (string, optional): Output video resolution. Options: "720P", "1080P" (default). Note: Resolution directly affects cost.
- `ratio` (string, optional): Aspect ratio of the video. Options: "16:9" (default, landscape), "9:16" (portrait), "1:1" (square), "4:3" (standard), "3:4" (vertical).
- `duration` (integer, optional): Duration of the video in seconds. For wan2.7-t2v: integer between 2 and 15 (inclusive). Default is 5.
- `negative_prompt` (string, optional): Negative prompt describing what should NOT appear in the video. Max 500 characters. Example: "low resolution, poor quality, deformed limbs, blurry".
- `audio_url` (string, optional): URL of audio file to use for the video. Supports HTTP/HTTPS URLs or OSS temporary URLs. Formats: wav, mp3. Duration: 2-30 seconds. File size: max 15MB. If not provided, the model will auto-generate matching background music.
- `prompt_extend` (boolean, optional): Enable AI-powered prompt enhancement. When enabled, uses LLM to optimize the prompt. Improves results for short prompts but increases processing time. Default is true.
- `watermark` (boolean, optional): Add 'AI生成' watermark to bottom-right corner of the video. Default is false.
- `seed` (integer, optional): Random seed for reproducible results. Range: [0, 2147483647]. If not specified, a random seed is generated. Note: Same seed doesn't guarantee identical results.
- `ref_image` (string, required in edit mode):
  - In edit mode: Absolute path to the reference video file that will be modified according to the text prompt. Must exist locally.

## Examples

**Example for vision - Describe an video at video.mp4**:
```
<tool>video</tool>
<parameter name="mode">vision</parameter>
<parameter name="prompt">Describe this videos</parameter>
<parameter name="video_path">video.mp4</parameter>
```

**Example for vision - How many birds appears in video.mp4**:
```
<tool>video</tool>
<parameter name="mode">vision</parameter>
<parameter name="prompt">How many birds appears in video?</parameter>
<parameter name="video_path">video.mp4</parameter>
```

**Example for display - Display video at video.mp4 with title "The video"**:
```
<tool>video</tool>
<parameter name="mode">display</parameter>
<parameter name="prompt">The video</parameter>
<parameter name="video_path">video.mp4</parameter>
```

**Example for display - Display video at video.mp4**:
```
<tool>video</tool>
<parameter name="mode">display</parameter>
<parameter name="video_path">video.mp4</parameter>
```

**Example for generate - Create an video of a cute orange cat**:
```
<tool>video</tool>
<parameter name="mode">generate</parameter>
<parameter name="prompt">A sitting orange cat with happy expression</parameter>
<parameter name="video_path">sitting_orange_cat.mp4</parameter>
```

**Example for edit - Change the color of the cat in video.mp4 to yellow**:
```
<tool>video</tool>
<parameter name="mode">generate</parameter>
<parameter name="prompt">Change the color of the cat in video to yellow</parameter>
<parameter name="video_path">cat_edit_to_yellow.png</parameter>
<parameter name="ref_video">video.mp4</parameter>
```

## Important Rules

1. **ALWAYS use video tool** - Never attempt direct LLM API calls
2. **Absolute paths only** - Convert all paths to absolute before calling
3. **Display generated/edited video** - After calling video tool in generate or edit mode, always use the display mode to show the resulting video
