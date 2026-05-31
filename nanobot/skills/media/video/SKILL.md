---
name: video
description: Unified tool for analyzing and displaying videos. Supports three modes?: display for showing videos to users, generate for creating videos from text prompts, and edit for modifying existing videos based on reference videos.
metadata: {"nanobot":{"emoji":"🎬"}}
---

# Video Skill

Unified tool for analyzing and displaying videos using the `media` tool with `media_type="video"`. Supports three modes?: display, video generation from text prompts, and editing videos with reference videos.

## Features

- Analyze videos using multimodal LLM models (description, visual QA)
- Display videos to users by sending them to the frontend
- Generate videos from text prompts using AI models
- Edit videos based on reference videos and text prompts
- Support multiple video formats: MP4, AVI, MOV, MKV, WEBM
- Base64 encoding for video processing and transmission

## Tool Parameters

The video skill uses the `media` tool. When using this tool, the `media_type` parameter **must** be set to `"video"`.

### Required Parameters
- `media_type` (string): Must be `"video"` for all video operations.
- `mode` (string): The operation mode.
  - `list`: List all available video files in the media directory.
    - `display`: Show a video to the user.
  - `generate`: Create a video from a text prompt.
  - `edit`: Modify an existing video based on a text prompt and a reference video.
- `media_path` (string):
  - In `display`/`edit` mode: Absolute path to the video file.
  - In `generate` mode: File name where the generated video will be saved.

### Optional Parameters
- `prompt` (string):
  - In `display` mode: Caption to display with the video.
  - In `generate` mode: Text prompt describing the desired video content (max 5000 characters). Can include multi-shot narratives with timestamps (e.g., "Shot 1 [0-3s] Wide shot: Rainy street. Shot 2 [3-6s] Medium shot: Person enters building.").
  - In `edit` mode: Description of how to modify the reference video (e.g., "Change the color of the car to red").
- `ref_media` (string):
  - In `edit` mode: Absolute path to the reference video file that will be modified. Must exist locally.
  - In `generate` mode: URL or path of audio file to use as background music for the video. Supports HTTP/HTTPS URLs or local file paths. Formats: wav, mp3. Duration: 2-30 seconds. File size: max 15MB.
- `resolution` (string): [Generate mode] Output video resolution. Options: "720P", "1080P" (default). Note: Resolution directly affects cost.
- `ratio` (string): [Generate mode] Aspect ratio of the video. Options: "16:9" (default, landscape), "9:16" (portrait), "1:1" (square), "4:3" (standard), "3:4" (vertical).
- `duration` (integer): [Generate mode] Duration of the video in seconds. For wan2.7-t2v: integer between 2 and 15 (inclusive). Default is 5.
- `negative_prompt` (string): [Generate mode] Negative prompt describing what should NOT appear in the video. Max 500 characters. Example: "low resolution, poor quality, deformed limbs, blurry".
- `prompt_extend` (boolean): [Generate mode] Enable AI-powered prompt enhancement. When enabled, uses LLM to optimize the prompt. Improves results for short prompts but increases processing time. Default is true.
- `watermark` (boolean): [Generate mode] Add 'AI生成' watermark to bottom-right corner of the video. Default is false.
- `seed` (integer): [Generate mode] Random seed for reproducible results. Range: [0, 2147483647]. If not specified, a random seed is generated. Note: Same seed doesn't guarantee identical results.

## Usage Examples

### List Mode
List all available videos:
```json
{"name": "media", "arguments": {"media_type": "video", "mode": "list"}}
```

### Display Mode
Display a video:
```json
{"name": "media", "arguments": {"media_type": "video", "mode": "display", "media_path": "/path/to/video.mp4"}}
```

Display a video with caption:
```json
{"name": "media", "arguments": {"media_type": "video", "mode": "display", "prompt": "The video", "media_path": "/path/to/video.mp4"}}
```

### Generate Mode
Create a video of a cute orange cat:
```json
{"name": "media", "arguments": {"media_type": "video", "mode": "generate", "prompt": "A sitting orange cat with happy expression", "media_path": "sitting_orange_cat.mp4"}}
```

Create a landscape video:
```json
{"name": "media", "arguments": {"media_type": "video", "mode": "generate", "prompt": "A beautiful sunset over mountains in cinematic style", "media_path": "sunset_cinematic.mp4", "resolution": "1080P", "ratio": "16:9", "duration": 10}}
```

Create a video with background music:
```json
{"name": "media", "arguments": {"media_type": "video", "mode": "generate", "prompt": "A dancing robot in a futuristic city", "media_path": "dancing_robot.mp4", "ref_media": "background_music.mp3"}}
```

### Edit Mode
Note: Video editing is currently not supported. Please use generate mode to create new videos.

## Important Rules

1. **ALWAYS use the `media` tool** with `media_type="video"` for all video operations. Never attempt direct LLM API calls.
2. **Absolute paths only** - Convert all paths to absolute before calling the tool in `display` or `edit` modes.
3. **Keep text unchanged in generate mode** - Do not change the `prompt` when generating a video.
4. **Display generated/edited videos** - After calling the `media` tool in `generate` or `edit` mode, always call the `media` tool in `display` mode to display the video.
5. **Single Display Call Per Conversation**: During a single conversation turn, you can call the `display` mode AT MOST ONCE to send media content to the user
6. **Display Only First Video from List**: When using `mode="list"` and multiple videos are available, display ONLY the first video. Do not display multiple videos in a single conversation turn
