"""Video tools for generating videos from text prompts."""

import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
import requests
from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage
from nanobot.providers.providers_manager import ProvidersManager
from nanobot.utils.media import get_media_dir


class VideoTool(Tool):
    """
    Tool for analyzing and generating videos using Alibaba Cloud DashScope API.

    Supports four modes:
    - vision: Analyze videos using multimodal LLM models (description, visual QA)
    - display: Display videos to users through WebSocket channel
    - generate: Generate videos from text prompts
    - edit: Edit videos based on reference videos and text prompts
    """

    def __init__(
        self,
        provider: ProvidersManager | None = None,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        default_message_id: str | None = None,
    ):
        """Initialize the video tool with all required parameters."""
        self.provider = provider
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        self._default_message_id = default_message_id

    @property
    def name(self) -> str:
        return "video"

    @property
    def description(self) -> str:
        return (
            "Analyze or generate videos. Supports four modes:\n"
            "- vision: Analyze and describe videos using multimodal LLM models. "
            "Supports video description, visual analysis, and answering questions about video content.\n"
            "- display: Display videos to users by reading from disk and sending to frontend. "
            "Use this when you want to show a video to the user directly.\n"
            "- generate: Generate videos from text prompts using Alibaba Cloud DashScope Wanxiang API. "
            "Supports customizable resolution, aspect ratio, duration, and optional audio.\n"
            "- edit: Edit an existing video using text prompts. Requires a reference video (ref_video) "
            "that will be modified according to the text prompt. The ref_video must exist locally.\n"
            "Videos are encoded as base64 for processing or display."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["vision", "display", "generate", "edit"],
                    "description": (
                        "The operation mode: 'vision' for video analysis, 'display' for showing videos to users, "
                        "'generate' for creating videos from text prompts, 'edit' for editing an existing video with text prompts."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "[In vision mode] The user's request or question about the video. "
                        "Examples: 'Describe this video', 'What happens in this video?', 'Is there a cat in this video?'\n"
                        "[In display mode] Caption to display with the video. "
                        "This text will appear above the video in the message box.\n"
                        "[In generate/edit mode] Text prompt describing the desired video content, style, and composition. "
                        "Supports Chinese and English. For wan2.7-t2v model: max 5000 characters. "
                        "Example: 'A cute cat running in the moonlight'."
                    ),
                },
                "video_path": {
                    "type": "string",
                    "description": (
                        "[In vision/display/edit mode] Path to the video file to analyze or display. Should be an absolute path "
                        "to a local video file (e.g., '/Users/archer/Desktop/video.mp4'). "
                        "Supported formats: MP4, AVI, MOV, MKV, WEBM.\n"
                        "[In generate mode] File name where the generated video will be saved in the media directory."
                    ),
                },
                "resolution": {
                    "type": "string",
                    "enum": ["720P", "1080P"],
                    "description": (
                        "[Optional for generate mode] Output video resolution. 720P or 1080P (default). "
                        "Note: Resolution directly affects cost. Confirm pricing before calling."
                    ),
                },
                "ratio": {
                    "type": "string",
                    "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                    "description": (
                        "[Optional for generate mode] Aspect ratio of the generated video. Default is 16:9. "
                        "Available options: 16:9 (landscape), 9:16 (portrait), 1:1 (square), "
                        "4:3 (standard), 3:4 (vertical)."
                    ),
                },
                "duration": {
                    "type": "integer",
                    "description": (
                        "[Optional for generate mode] Duration of the generated video in seconds. "
                        "For wan2.7-t2v: integer between 2 and 15 (inclusive). Default is 5."
                    ),
                },
                "negative_prompt": {
                    "type": "string",
                    "description": (
                        "[Optional for generate/edit mode] Negative prompt describing what should NOT appear in the video. "
                        "Max 500 characters. Example: 'low resolution, poor quality, deformed limbs, blurry'."
                    ),
                },
                "audio_url": {
                    "type": "string",
                    "description": (
                        "[Optional for generate mode] URL of audio file to use for the video. Supports HTTP/HTTPS URLs or OSS temporary URLs. "
                        "Formats: wav, mp3. Duration: 2-30 seconds. File size: max 15MB. "
                        "If not provided, the model will auto-generate matching background music. "
                        "Example: 'https://example.com/audio.mp3'"
                    ),
                },
                "prompt_extend": {
                    "type": "boolean",
                    "description": (
                        "[Optional for generate mode] Enable AI-powered prompt enhancement. When enabled, uses LLM to optimize the prompt. "
                        "Improves results for short prompts but increases processing time. Default is true."
                    ),
                },
                "watermark": {
                    "type": "boolean",
                    "description": (
                        "[Optional for generate mode] Add 'AI生成' watermark to bottom-right corner of the video. Default is false."
                    ),
                },
                "seed": {
                    "type": "integer",
                    "description": (
                        "[Optional for generate mode] Random seed for reproducible results. Range: [0, 2147483647]. "
                        "If not specified, a random seed is generated. Note: Same seed doesn't guarantee identical results."
                    ),
                },
                "ref_video": {
                    "type": "string",
                    "description": (
                        "[Required for edit mode] Reference video path for video editing. "
                        "The model will modify this video according to the text prompt. "
                        "Must be an absolute path to a local video file that exists (e.g., '/Users/archer/Desktop/video.mp4'). "
                        "Supported formats: MP4, AVI, MOV, MKV, WEBM.\n"
                        "Example: Use ref_video to change style, add/remove objects, or modify appearance of an existing video."
                    ),
                },
            },
            "required": ["mode", "video_path"],
        }

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_message_id = message_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    def _get_mime_type(self, video_path: str) -> str:
        """Get MIME type based on file extension."""
        ext = Path(video_path).suffix.lower()
        mime_types = {
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
            ".mov": "video/quicktime",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm",
        }
        return mime_types.get(ext, "video/mp4")

    def _get_video_data(self, video_path: str) -> str:
        """
        Get video data as base64 encoded string with MIME type.

        Args:
            video_path: Absolute path to the video file.

        Returns:
            Data URL formatted string: "data:<mime_type>;base64,<encoded_video>"

        Raises:
            FileNotFoundError: If video file doesn't exist.
            ValueError: If file is not a valid video.
        """
        encoded_video = self._encode_video(video_path)
        mime_type = self._get_mime_type(video_path)
        return f"data:{mime_type};base64,{encoded_video}"

    def _encode_video(self, video_path: str) -> str:
        """
        Encode a video file to base64 string.

        Args:
            video_path: Absolute path to the video file.

        Returns:
            Base64 encoded video string.

        Raises:
            FileNotFoundError: If video file doesn't exist.
            ValueError: If file is not a valid video.
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Check file extension
        valid_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        if path.suffix.lower() not in valid_extensions:
            raise ValueError(
                f"Unsupported video format: {path.suffix}. "
                f"Supported formats: {', '.join(valid_extensions)}"
            )

        # Read and encode video
        with open(path, "rb") as video_file:
            encoded = base64.b64encode(video_file.read()).decode("utf-8")

        return encoded

    async def execute(
        self,
        mode: str = "generate",
        prompt: str = "",
        video_path: str = "",
        resolution: str = "1080P",
        ratio: str = "16:9",
        duration: int = 5,
        negative_prompt: str = "",
        audio_url: str = "",
        prompt_extend: bool = True,
        watermark: bool = False,
        seed: int | None = None,
        ref_video: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute video tool based on mode.

        Args:
            mode: Operation mode - 'vision' for analysis, 'display' for showing videos, 'generate' for creating videos, 'edit' for editing videos.
            prompt: [Vision mode] User's request/question about the video. [Display mode] Caption to display. [Generate/Edit mode] Video generation/editing prompt.
            video_path: Path to the video file (for vision/display) or save path (for generate).
            resolution: [Generate mode] Output video resolution.
            ratio: [Generate mode] Aspect ratio.
            duration: [Generate mode] Video duration in seconds.
            negative_prompt: [Generate/Edit mode] Negative prompt for undesired content.
            audio_url: [Generate mode] URL of audio file to use.
            prompt_extend: [Generate mode] Enable AI prompt enhancement.
            watermark: [Generate mode] Add watermark.
            seed: [Generate mode] Random seed for reproducibility.
            ref_video: [Edit mode] Reference video path for video editing.

        Returns:
            Analysis result (vision mode), status message (display mode), or generation result (generate/edit mode).
        """
        media_dir = get_media_dir()
        if mode == "vision":
            return await self._execute_vision(prompt=prompt, video_path=video_path, **kwargs)
        elif mode == "display":
            return await self._execute_display(prompt=prompt, video_path=video_path, **kwargs)
        elif mode == "generate":
            if not video_path:
                video_path = str(media_dir / "generated.mp4")
            return await self._dashscope_generate(
                prompt=prompt,
                video_path=video_path,
                resolution=resolution,
                ratio=ratio,
                duration=duration,
                negative_prompt=negative_prompt,
                audio_url=audio_url,
                prompt_extend=prompt_extend,
                watermark=watermark,
                seed=seed,
                **kwargs,
            )
        elif mode == "edit":
            if not ref_video or not os.path.exists(ref_video):
                return f"Error: Ref video {ref_video} path is invalid."
            if not video_path:
                video_path = str(media_dir / "generated.mp4")
            # For edit mode, we'll use the same generation API but with ref_video
            # Note: DashScope currently doesn't support video-to-video editing directly
            # This is a placeholder for future implementation
            return "Error: Video editing is not yet supported. Please use generate mode to create new videos."
        else:
            return (
                f"Error: Invalid mode '{mode}'. Must be 'vision', 'display', 'generate', or 'edit'."
            )

    async def _execute_vision(self, prompt: str, video_path: str, **kwargs: Any) -> str:
        """
        Execute video vision analysis.

        Args:
            prompt: User's request/question about the video.
            video_path: Path to the video file.

        Returns:
            Analysis result from the vision model.
        """
        if not self.provider:
            return "Error: Provider not configured for vision mode."

        if not video_path:
            return "Error: No video provided. Please provide a video path."

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        # Process video
        try:
            video_data = self._get_video_data(video_path)
            content.append({"type": "video_url", "video_url": {"url": video_data}})
        except FileNotFoundError as e:
            return f"Error: {str(e)}"
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error encoding video '{video_path}': {str(e)}"

        # Build messages for chat completion
        messages = [
            {
                "role": "system",
                "content": "You are a multimodal model capable of analyzing videos.",
            },
            {"role": "user", "content": content},
        ]
        try:
            response = await self.provider.chat(messages=messages, mode="multimodal")
            if response.content:
                return response.content
            return "Error: No response content from vision model."
        except Exception as e:
            return f"Error calling vision model: {str(e)}"

    async def _execute_display(self, prompt: str, video_path: str, **kwargs: Any) -> str:
        """
        Execute video display by sending video data to frontend.

        Args:
            video_path: Path to the video file to display.
            prompt: Optional caption text to display above the video.

        Returns:
            Status message indicating success or error.
        """
        if not self._send_callback:
            return "Error: Message sending not configured"

        try:
            # Prepare media data for the message
            media_data = {
                "data": self._get_video_data(video_path),
                "file_name": Path(video_path).name,
            }
            # Create outbound message with video as media
            msg = OutboundMessage(
                channel=self._default_channel,
                chat_id=self._default_chat_id,
                content=prompt or "Video display",
                media=[media_data],
                metadata={
                    "_progress": True,
                    "msg_type": "video",  # Indicate this is a video message
                    "file_type": self._get_mime_type(video_path),
                },
            )

            # Send the message through the callback
            await self._send_callback(msg)
            return f"Video displayed successfully: {Path(video_path).name}"

        except FileNotFoundError as e:
            return f"Error: {str(e)}"
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dashscope_generate(
        self,
        prompt: str,
        video_path: str,
        resolution: str = "1080P",
        ratio: str = "16:9",
        duration: int = 5,
        negative_prompt: str = "",
        audio_url: str = "",
        prompt_extend: bool = True,
        watermark: bool = False,
        seed: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute video generation using Alibaba Cloud DashScope Wanxiang API.

        Uses asynchronous task creation and polling mechanism.
        Task typically completes in 1-5 minutes.

        Args:
            prompt: Text prompt describing the desired video content.
            video_path: File name where the generated video will be saved.
            resolution: Output video resolution (720P or 1080P).
            ratio: Aspect ratio.
            duration: Video duration in seconds.
            negative_prompt: Negative prompt for undesired content.
            audio_url: URL of audio file.
            prompt_extend: Enable AI prompt enhancement.
            watermark: Add watermark.
            seed: Random seed.

        Returns:
            Status message with generation result or error details.
        """
        # Get API key from environment
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return "Error: DASHSCOPE_API_KEY not found. Please set it in environment variables at ~/.nanobot/workspace/.env."

        # Determine endpoint based on region
        region = os.getenv("DASHSCOPE_REGION", "beijing").lower()
        if region == "beijing":
            create_endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
        elif region == "singapore":
            create_endpoint = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
        else:
            return f"Error: Invalid region '{region}'. Must be 'beijing' or 'singapore'."

        # Get model name from environment or use default
        model_name = os.getenv("DASHSCOPE_VIDEO_GEN_MODEL", "wan2.7-t2v")

        # Build input object
        input_data = {"prompt": prompt}
        if audio_url:
            input_data["audio_url"] = audio_url

        # Build parameters object
        parameters = {
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "prompt_extend": prompt_extend,
            "watermark": watermark,
        }

        # Add optional parameters
        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt

        if seed is not None:
            parameters["seed"] = seed

        # Build request payload
        payload = {
            "model": model_name,
            "input": input_data,
            "parameters": parameters,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-DashScope-Async": "enable",  # Required for async calls
        }

        try:
            # Step 1: Create task
            logger.info(f"Creating video generation task with prompt: {prompt[:100]}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(create_endpoint, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            # Extract task_id
            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                return f"Error: No task_id in response. Response: {json.dumps(result, ensure_ascii=False)}"

            logger.info(f"Video generation task created: {task_id}")

            # Step 2: Poll for task completion
            # Determine query endpoint based on region
            if region == "beijing":
                query_endpoint = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
            else:
                query_endpoint = f"https://dashscope-intl.aliyuncs.com/api/v1/tasks/{task_id}"

            query_headers = {
                "Authorization": f"Bearer {api_key}",
            }

            # Poll every 10 seconds, timeout after 10 minutes
            max_wait_time = 600  # 10 minutes
            poll_interval = 10
            elapsed_time = 0

            while elapsed_time < max_wait_time:
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval

                async with httpx.AsyncClient(timeout=30.0) as client:
                    query_response = await client.get(query_endpoint, headers=query_headers)
                    query_response.raise_for_status()
                    task_result = query_response.json()

                print(f"[TMINFO] task_result pos 1 {task_result}", flush=True)
                task_status = task_result.get("output", {}).get("task_status", "")

                if task_status == "SUCCEEDED":
                    # Task completed successfully
                    video_url = task_result.get("output", {}).get("video_url", "")
                    if not video_url:
                        return f"Error: No video_url in response. Response: {json.dumps(task_result, ensure_ascii=False)}"

                    # Download and save video
                    media_dir = get_media_dir()
                    save_path = media_dir / video_path
                    save_path.parent.mkdir(parents=True, exist_ok=True)

                    logger.info(f"Downloading video from: {video_url}")
                    async with httpx.AsyncClient(timeout=120.0) as download_client:
                        video_response = await download_client.get(video_url)
                        video_response.raise_for_status()

                        with open(save_path, "wb") as f:
                            f.write(video_response.content)

                    logger.info(f"Video generated successfully: {save_path}")
                    return f"Video generated successfully, saved to {save_path}"

                elif task_status == "FAILED":
                    # Task failed
                    error_code = task_result.get("output", {}).get("code", "unknown")
                    error_message = task_result.get("output", {}).get("message", "Unknown error")
                    return f"Error: Video generation failed - [{error_code}] {error_message}"

                elif task_status in ["RUNNING", "PENDING"]:
                    # Still processing
                    logger.info(f"Task {task_id} status: {task_status}, elapsed: {elapsed_time}s")
                    continue

                else:
                    return f"Error: Unknown task status: {task_status}"

            # Timeout
            return f"Error: Video generation timed out after {max_wait_time} seconds. Task ID: {task_id}"

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if e.response else str(e)
            try:
                error_json = e.response.json()
                error_msg = error_json.get("message", error_json.get("error", error_detail))
            except Exception:
                error_msg = error_detail
            return f"Error: HTTP {e.response.status_code} - {error_msg}"
        except httpx.TimeoutException:
            return (
                "Error: Request timed out. Video generation may take 1-5 minutes, please try again."
            )
        except httpx.RequestError as e:
            return f"Error: Network request failed - {str(e)}"
        except Exception as e:
            return f"Error: Generation failed - {str(e)}"
