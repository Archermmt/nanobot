"""Media tools for handling images, videos, and audio files."""

import asyncio
import base64
import json
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
import requests
from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage
from nanobot.providers.providers_manager import ProvidersManager
from nanobot.utils.media import get_media_dir


class MediaTool(Tool):
    """
    Unified tool for handling different types of media: images, videos, and audio.

    Supports three media types with various modes:
    - image: Analyze (vision), display, generate, or edit images
    - video: Analyze (vision), display, or generate videos
    - audio: List available music files or play audio files
    """

    def __init__(
        self,
        provider: ProvidersManager | None = None,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        default_message_id: str | None = None,
    ):
        """Initialize the media tool with all required parameters."""
        self.provider = provider
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        self._default_message_id = default_message_id

    @property
    def name(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return (
            "Unified tool for handling different types of media (images, videos, audio). "
            "Supports three media types:\n"
            "- image: List, analyze (vision), display, generate, or edit images\n"
            "  * list: List all available image files in the media directory\n"
            "  * vision: Analyze images using multimodal LLM models (OCR, description, visual QA)\n"
            "  * display: Display images to users through WebSocket channel\n"
            "  * generate: Generate images from text prompts using Alibaba Cloud Qwen-Image API\n"
            "  * edit: Edit an existing image using text prompts\n"
            "- video: List, analyze (vision), display, or generate videos\n"
            "  * list: List all available video files in the media directory\n"
            "  * vision: Analyze videos using multimodal LLM models\n"
            "  * display: Display videos to users through WebSocket channel\n"
            "  * generate: Generate videos from text prompts using Alibaba Cloud DashScope Wanxiang API\n"
            "- audio: List or display audio files\n"
            "  * list: List all available audio files in the media directory\n"
            "  * display: Play an audio file by sending it as media\n"
            "The media_type parameter determines which type of media to process."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "media_type": {
                    "type": "string",
                    "enum": ["image", "video", "audio"],
                    "description": (
                        "The type of media to process: 'image' for image operations, "
                        "'video' for video operations, 'audio' for audio/music operations."
                    ),
                },
                "mode": {
                    "type": "string",
                    "description": (
                        "The operation mode. For image: 'list', 'vision', 'display', 'generate', 'edit'. "
                        "For video: 'list', 'vision', 'display', 'generate'. "
                        "For audio: 'list', 'display'."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "[Image/Video vision mode] User's request/question about the media. "
                        "[Image/Video display mode] Caption to display. "
                        "[Image/Video generate mode] Text prompt describing desired content. "
                        "[Audio play mode] Not used."
                    ),
                },
                "media_path": {
                    "type": "string",
                    "description": (
                        "[Image/Video vision/display mode] Path to the media file. "
                        "[Image/Video generate mode] File name where generated media will be saved. "
                        "[Audio display mode] Path to the audio file to display."
                    ),
                },
                # Image generation parameters
                "size": {
                    "type": "string",
                    "description": (
                        "[Optional for image generate mode] Output image resolution in format 'width*height'. "
                        "Default is 1024*1024. Examples: '1024*1024', '1664*928'."
                    ),
                },
                "negative_prompt": {
                    "type": "string",
                    "description": (
                        "[Optional for image/video generate mode] Negative prompt describing what should NOT appear. "
                        "Max 500 characters."
                    ),
                },
                "n": {
                    "type": "integer",
                    "description": (
                        "[Optional for image generate mode] Number of images to generate (1-6). Default is 1."
                    ),
                },
                "prompt_extend": {
                    "type": "boolean",
                    "description": (
                        "[Optional for image/video generate mode] Enable AI-powered prompt enhancement. Default is true."
                    ),
                },
                "watermark": {
                    "type": "boolean",
                    "description": (
                        "[Optional for image/video generate mode] Add watermark. Default is false."
                    ),
                },
                "ref_media": {
                    "type": "string",
                    "description": (
                        "[For image/video edit mode] Reference media path for editing. "
                        "Must be an absolute path to a local media file that exists.\n"
                        "[For video generate mode] URL or path of audio file to use as background music for the video. "
                        "Supports HTTP/HTTPS URLs or local file paths. Formats: wav, mp3."
                    ),
                },
                # Video generation parameters
                "resolution": {
                    "type": "string",
                    "enum": ["720P", "1080P"],
                    "description": (
                        "[Optional for video generate mode] Output video resolution. Default is 1080P."
                    ),
                },
                "ratio": {
                    "type": "string",
                    "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                    "description": (
                        "[Optional for video generate mode] Aspect ratio. Default is 16:9."
                    ),
                },
                "duration": {
                    "type": "integer",
                    "description": (
                        "[Optional for video generate mode] Duration in seconds (2-15). Default is 5."
                    ),
                },
                "seed": {
                    "type": "integer",
                    "description": (
                        "[Optional for video generate mode] Random seed for reproducible results."
                    ),
                },
            },
            "required": ["media_type", "mode"],
        }

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_message_id = message_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    async def execute(
        self,
        media_type: str,
        mode: str,
        prompt: str = "",
        media_path: str = "",
        size: str = "1024*1024",
        negative_prompt: str = "",
        n: int = 1,
        prompt_extend: bool = True,
        watermark: bool = False,
        ref_media: str | None = None,
        resolution: str = "1080P",
        ratio: str = "16:9",
        duration: int = 5,
        seed: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute media tool based on media_type and mode.

        Args:
            media_type: Type of media - 'image', 'video', or 'audio'.
            mode: Operation mode depending on media_type.
            prompt: Text prompt or caption depending on mode.
            media_path: Path to media file or save location.
            size: [Image generate] Output resolution.
            negative_prompt: [Image/Video generate] Negative prompt.
            n: [Image generate] Number of images.
            prompt_extend: [Image/Video generate] Enable prompt enhancement.
            watermark: [Image/Video generate] Add watermark.
            ref_media: [Image/Video edit] Reference media path for editing. [Video generate] Audio URL or path for background music.
            resolution: [Video generate] Video resolution.
            ratio: [Video generate] Aspect ratio.
            duration: [Video generate] Duration in seconds.
            seed: [Video generate] Random seed.
            ref_video: [Video edit] Reference video path.

        Returns:
            Result message based on operation.
        """
        if mode == "list":
            return await self._execute_list(media_type=media_type)
        if mode == "display":
            return await self._execute_display(media_path=media_path, media_type=media_type)
        # Calculate media_dir based on media_type
        media_dir = get_media_dir() / media_type
        if media_type == "image":
            return await self._execute_image(
                mode=mode,
                image_path=media_path,
                prompt=prompt,
                media_dir=media_dir,
                size=size,
                negative_prompt=negative_prompt,
                n=n,
                prompt_extend=prompt_extend,
                watermark=watermark,
                ref_media=ref_media,
                **kwargs,
            )
        elif media_type == "video":
            return await self._execute_video(
                mode=mode,
                prompt=prompt,
                video_path=media_path,
                media_dir=media_dir,
                resolution=resolution,
                ratio=ratio,
                duration=duration,
                negative_prompt=negative_prompt,
                prompt_extend=prompt_extend,
                watermark=watermark,
                seed=seed,
                ref_media=ref_media,
                **kwargs,
            )
        elif media_type == "audio":
            return await self._execute_audio(
                mode=mode,
                music_path=media_path,
                media_dir=media_dir,
                **kwargs,
            )
        else:
            return (
                f"Error: Invalid media_type '{media_type}'. Must be 'image', 'video', or 'audio'."
            )

    async def _execute_list(self, media_type: str) -> str:
        """List all available media files based on media type."""
        # Define media type configurations
        extensions = {
            "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"},
            "video": {".mp4", ".avi", ".mov", ".mkv", ".webm"},
            "audio": {".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a", ".wma"},
        }
        if media_type not in extensions:
            return (
                f"Error: Invalid media_type '{media_type}'. Must be 'image', 'video', or 'audio'."
            )

        # Check if directory exists
        media_dir = get_media_dir() / media_type
        if not media_dir.exists():
            return f"No {media_type} files found. Directory does not exist: {media_dir}"

        # Find all media files recursively
        media_files: list[Path] = []

        def _list_files(directory: Path) -> None:
            """Recursively list media files in directory."""
            for item in directory.iterdir():
                if item.is_file() and item.suffix.lower() in extensions[media_type]:
                    media_files.append(item)
                elif item.is_dir():
                    self._list_files(item)

        _list_files(media_dir)

        if not media_files:
            return f"No {media_type} files found in the media directory."

        # Sort by name
        media_files.sort(key=lambda x: x.name.lower())

        # Format output
        result = f"Found {len(media_files)} {media_type} file(s):\n\n"
        for idx, file_path in enumerate(media_files, 1):
            size = file_path.stat().st_size / 1024 * 1024
            result += f"{idx}. {file_path.name} ({size:.2f} MB)\n"
            result += f"   Path: {file_path}\n\n"

        return result.strip()

    def _get_media_path(self, media_path: str, media_type: str) -> Path:
        """Get the absolute path for a media file."""
        path = Path(media_path)
        if not path.is_absolute():
            path = get_media_dir() / media_type / path
        return path

    async def _execute_display(self, media_path: str, media_type: str) -> str:
        """Execute media display."""
        if not self._send_callback:
            return "Error: Message sending not configured"
        media_path = self._get_media_path(media_path, media_type)
        if not media_path.exists():
            return f"Error: Media file not found: {media_path}"
        media_path = str(media_path)
        try:
            media_data = {"data": self._get_media_data(media_path), "file_name": media_path}
            msg = OutboundMessage(
                channel=self._default_channel,
                chat_id=self._default_chat_id,
                content=f"Display {media_type}: {media_path}",
                media=[media_data],
                metadata={"msg_type": media_type, "file_type": self._get_mime_type(media_type)},
            )
            await self._send_callback(msg)
            return ""
        except FileNotFoundError as e:
            return f"Error: {str(e)}"
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _execute_image(
        self,
        mode: str,
        image_path: str,
        prompt: str = "",
        media_dir: Path | None = None,
        size: str = "1024*1024",
        negative_prompt: str = "",
        n: int = 1,
        prompt_extend: bool = True,
        watermark: bool = False,
        ref_media: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute image operations."""

        image_path = self._get_media_path(image_path or "generated.png", "image")
        if mode == "vision":
            return await self._execute_image_vision(prompt=prompt, image_path=image_path, **kwargs)
        elif mode == "generate":
            return await self._execute_image_generate(
                prompt=prompt,
                image_path=image_path,
                size=size,
                negative_prompt=negative_prompt,
                n=n,
                prompt_extend=prompt_extend,
                watermark=watermark,
                **kwargs,
            )
        elif mode == "edit":
            if not ref_media or not os.path.exists(ref_media):
                return f"Error: Ref media {ref_media} path is invalid."
            return await self._execute_image_generate(
                prompt=prompt,
                image_path=image_path,
                size=size,
                negative_prompt=negative_prompt,
                n=n,
                prompt_extend=prompt_extend,
                watermark=watermark,
                ref_image=ref_media,
                **kwargs,
            )
        else:
            return f"Error: Invalid mode '{mode}' for image. Must be 'list', 'vision', 'display', 'generate', or 'edit'."

    async def _execute_image_vision(self, prompt: str, image_path: Path) -> str:
        """Execute image vision analysis."""
        if not image_path.exists():
            return "Error: No image provided. Please provide at least one image path."

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        try:
            image_data = self._get_media_data(str(image_path))
            content.append({"type": "image_url", "image_url": {"url": image_data}})
        except FileNotFoundError as e:
            return f"Error: {str(e)}"
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error encoding image '{image_path}': {str(e)}"

        messages = [
            {"role": "system", "content": "Your are a multimodal model"},
            {"role": "user", "content": content},
        ]
        try:
            response = await self.provider.chat(messages=messages, mode="multimodal")
            if response.content:
                return response.content
            return "Error: No response content from vision model."
        except Exception as e:
            return f"Error calling vision model: {str(e)}"

    async def _execute_image_generate(
        self,
        prompt: str,
        image_path: Path,
        size: str = "1024*1024",
        negative_prompt: str = "",
        n: int = 1,
        prompt_extend: bool = True,
        watermark: bool = False,
        ref_image: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute image generation."""
        if not prompt:
            return "Error: Text prompt is required for image generation."

        provider = os.getenv("IMAGE_GEN_PROVIDER", "dashscope")
        image_paths, error = [], ""
        gen_kwargs = {
            "prompt": prompt,
            "image_path": str(image_path),
            "size": size,
            "negative_prompt": negative_prompt,
            "n": n,
            "prompt_extend": prompt_extend,
            "watermark": watermark,
            "ref_image": ref_image,
        }
        if provider == "dashscope":
            image_paths, error = await self._dashscope_image_generate(**gen_kwargs, **kwargs)
        elif provider == "modelscope":
            image_paths, error = await self._modelscope_image_generate(**gen_kwargs, **kwargs)
        else:
            raise ValueError(f"Invalid IMAGE_GEN_PROVIDER: {provider}")

        if error:
            return "Failed generate image: " + str(error)
        return f"Generated image by {provider} successfully, saved to {image_paths[0]}"

    async def _execute_video(
        self,
        mode: str,
        prompt: str = "",
        video_path: str = "",
        media_dir: Path | None = None,
        resolution: str = "1080P",
        ratio: str = "16:9",
        duration: int = 5,
        negative_prompt: str = "",
        prompt_extend: bool = True,
        watermark: bool = False,
        seed: int | None = None,
        ref_media: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute video operations."""

        video_path = self._get_media_path(video_path or "generated.mp4", "video")
        if mode == "vision":
            return await self._execute_video_vision(prompt=prompt, video_path=video_path, **kwargs)
        elif mode == "generate":
            if not video_path.exists():
                video_path = media_dir / "generated.mp4"
            return await self._dashscope_video_generate(
                prompt=prompt,
                video_path=video_path,
                resolution=resolution,
                ratio=ratio,
                duration=duration,
                negative_prompt=negative_prompt,
                ref_media=ref_media,
                prompt_extend=prompt_extend,
                watermark=watermark,
                seed=seed,
                **kwargs,
            )
        elif mode == "edit":
            if not ref_media or not os.path.exists(ref_media):
                return f"Error: Ref media {ref_media} path is invalid."
            return "Error: Video editing is not yet supported. Please use generate mode to create new videos."
        else:
            return f"Error: Invalid mode '{mode}' for video. Must be 'list', 'vision', 'display', 'generate', or 'edit'."

    async def _execute_video_vision(self, prompt: str, video_path: str, **kwargs: Any) -> str:
        """Execute video vision analysis."""
        if not self.provider:
            return "Error: Provider not configured for vision mode."

        if not video_path:
            return "Error: No video provided. Please provide a video path."

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        try:
            video_data = self._get_media_data(video_path)
            content.append({"type": "video_url", "video_url": {"url": video_data}})
        except FileNotFoundError as e:
            return f"Error: {str(e)}"
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error encoding video '{video_path}': {str(e)}"

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

    async def _execute_audio(
        self, mode: str, music_path: str = "", media_dir: Path | None = None, **kwargs: Any
    ) -> str:
        """Execute audio operations."""
        return f"Error: Invalid mode '{mode}' for audio. Must be 'list' or 'display'."

    def _encode_media(self, media_path: str) -> str:
        """Encode a media file (image/video/audio) to base64 string."""
        path = Path(media_path)
        if not path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")

        # All supported media extensions
        valid_extensions = {
            # Image formats
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".bmp",
            ".svg",
            # Video formats
            ".mp4",
            ".avi",
            ".mov",
            ".mkv",
            ".webm",
            # Audio formats
            ".mp3",
            ".wav",
            ".ogg",
            ".aac",
            ".flac",
            ".m4a",
            ".wma",
        }

        if path.suffix.lower() not in valid_extensions:
            raise ValueError(
                f"Unsupported media format: {path.suffix}. "
                f"Supported formats: {', '.join(sorted(valid_extensions))}"
            )

        with open(path, "rb") as media_file:
            encoded = base64.b64encode(media_file.read()).decode("utf-8")

        return encoded

    def _get_media_data(self, media_path: str) -> str:
        """Get media data as base64 encoded string with MIME type."""
        encoded_media = self._encode_media(media_path)
        mime_type = self._get_mime_type(media_path)
        return f"data:{mime_type};base64,{encoded_media}"

    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type based on file extension (generic)."""
        ext = Path(file_path).suffix.lower()

        # Image types
        image_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".svg": "image/svg+xml",
        }

        # Video types
        video_types = {
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
            ".mov": "video/quicktime",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm",
        }

        # Audio types
        audio_types = {
            ".mp3": "audio/mp3",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
            ".wma": "audio/x-ms-wma",
        }

        all_types = {**image_types, **video_types, **audio_types}
        return all_types.get(ext, "application/octet-stream")

    # Image generation methods
    async def _dashscope_image_generate(
        self,
        prompt: str,
        image_path: str,
        size: str = "1024*1024",
        negative_prompt: str = "",
        n: int = 1,
        prompt_extend: bool = True,
        watermark: bool = False,
        ref_image: str | None = None,
        **kwargs: Any,
    ) -> tuple[list[str], str]:
        """Execute image generation using Alibaba Cloud Qwen-Image API."""
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            error = "Error: DASHSCOPE_API_KEY not found. Please set it in environment variables at ~/.nanobot/workspace/.env. "
            return [], error

        region = os.getenv("DASHSCOPE_REGION", "beijing").lower()
        if region == "beijing":
            endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        elif region == "singapore":
            endpoint = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        else:
            return (
                [],
                f"Error: Invalid region '{region}'. Must be 'beijing' or 'singapore'.",
            )

        if ref_image:
            model_name = os.getenv("DASHSCOPE_IMAGE_EDIT_MODEL", "qwen-image-max")
        else:
            model_name = os.getenv("DASHSCOPE_IMAGE_GEN_MODEL", "qwen-image-max")

        content_items = []
        if ref_image:
            content_items.append({"image": self._get_media_data(ref_image)})
        content_items.append({"text": prompt})

        payload = {
            "model": model_name,
            "input": {"messages": [{"role": "user", "content": content_items}]},
            "parameters": {
                "size": size,
                "prompt_extend": prompt_extend,
                "watermark": watermark,
            },
        }

        if negative_prompt:
            payload["parameters"]["negative_prompt"] = negative_prompt

        if n > 1:
            payload["parameters"]["n"] = min(n, 6)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            output = result.get("output", {})
            choices = output.get("choices", [])

            if not choices:
                error = (
                    f"Error: No image generated. Response: {json.dumps(result, ensure_ascii=False)}"
                )
                return [], error

            image_urls = []
            for choice in choices:
                message = choice.get("message", {})
                content = message.get("content", [])
                for item in content:
                    if "image" in item:
                        image_urls.append(item["image"])

            if not image_urls:
                error = f"Error: No image URL in response. Response: {json.dumps(result, ensure_ascii=False)}"
                return [], error

            saved_paths = []
            for idx, img_url in enumerate(image_urls):
                async with httpx.AsyncClient(timeout=30.0) as download_client:
                    img_response = await download_client.get(img_url)
                    img_response.raise_for_status()

                    if len(image_urls) > 1:
                        path_obj = Path("~/.nanobot/media") / image_path
                        save_path = path_obj.parent / f"{path_obj.stem}_{idx + 1}{path_obj.suffix}"
                    else:
                        save_path = Path("~/.nanobot/media") / image_path

                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(img_response.content)

                    saved_paths.append(str(save_path))

            usage = result.get("usage", {})
            width = usage.get("width", "unknown")
            height = usage.get("height", "unknown")

            if len(saved_paths) == 1:
                logger.info(f"Image generated successfully: {saved_paths[0]} ({width}x{height})")
                return saved_paths, ""

            msg = (
                f"Generated {len(saved_paths)} images successfully:\n"
                + "\n".join(f"- {path}" for path in saved_paths)
                + f"\nResolution: {width}x{height}"
            )
            return [], msg

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if e.response else str(e)
            try:
                error_json = e.response.json()
                error_msg = error_json.get("message", error_json.get("error", error_detail))
            except Exception:
                error_msg = error_detail
            return [], f"Error: HTTP {e.response.status_code} - {error_msg}"
        except httpx.TimeoutException:
            return [], (
                "Error: Request timed out. The generation may take 10-30 seconds, please try again."
            )
        except httpx.RequestError as e:
            return [], f"Error: Network request failed - {str(e)}"
        except Exception as e:
            return [], f"Error: Generation failed - {str(e)}"

    async def _modelscope_image_generate(
        self,
        prompt: str,
        image_path: str,
        size: str = "1024*1024",
        negative_prompt: str = "",
        n: int = 1,
        prompt_extend: bool = True,
        watermark: bool = False,
        ref_image: str | None = None,
        **kwargs: Any,
    ) -> tuple[list[str], str]:
        """Execute image generation using ModelScope API."""
        from PIL import Image

        base_url = "https://api-inference.modelscope.cn/"
        api_key = os.getenv("MODELSCOPE_API_KEY")
        if not api_key:
            error = "Error: MODELSCOPE_API_KEY not found. Please set it in environment variables at ~/.nanobot/workspace/.env"
            return [], error

        common_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        if ref_image:
            model_name = os.getenv("MODELSCOPE_IMAGE_EDIT_MODEL", "Qwen/Qwen-Image-2512")
        else:
            model_name = os.getenv("MODELSCOPE_IMAGE_GEN_MODEL", "Qwen/Qwen-Image-2512")

        payload = {"model": model_name, "prompt": prompt}
        if ref_image:
            payload["image_url"] = [self._get_media_data(ref_image)]

        response = requests.post(
            f"{base_url}v1/images/generations",
            headers={**common_headers, "X-ModelScope-Async-Mode": "true"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

        response.raise_for_status()
        task_id = response.json()["task_id"]

        while True:
            result = requests.get(
                f"{base_url}v1/tasks/{task_id}",
                headers={
                    **common_headers,
                    "X-ModelScope-Task-Type": "image_generation",
                },
            )
            result.raise_for_status()
            data = result.json()
            if data["task_status"] == "SUCCEED":
                image = Image.open(BytesIO(requests.get(data["output_images"][0]).content))
                image.save(image_path)
                return [image_path], ""
            if data["task_status"] == "FAILED":
                return [], "Image Generation Failed."
            time.sleep(5)

    # Video generation method
    async def _dashscope_video_generate(
        self,
        prompt: str,
        video_path: Path,
        resolution: str = "1080P",
        ratio: str = "16:9",
        duration: int = 5,
        negative_prompt: str = "",
        ref_media: str | None = None,
        prompt_extend: bool = True,
        watermark: bool = False,
        seed: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute video generation using Alibaba Cloud DashScope Wanxiang API."""
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return "Error: DASHSCOPE_API_KEY not found. Please set it in environment variables at ~/.nanobot/workspace/.env."

        region = os.getenv("DASHSCOPE_REGION", "beijing").lower()
        if region == "beijing":
            create_endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
        elif region == "singapore":
            create_endpoint = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
        else:
            return f"Error: Invalid region '{region}'. Must be 'beijing' or 'singapore'."

        model_name = os.getenv("DASHSCOPE_VIDEO_GEN_MODEL", "wan2.7-t2v")

        input_data = {"prompt": prompt}
        if ref_media:
            input_data["audio_url"] = ref_media

        parameters = {
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "prompt_extend": prompt_extend,
            "watermark": watermark,
        }

        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt

        if seed is not None:
            parameters["seed"] = seed

        payload = {
            "model": model_name,
            "input": input_data,
            "parameters": parameters,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-DashScope-Async": "enable",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(create_endpoint, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                return f"Error: No task_id in response. Response: {json.dumps(result, ensure_ascii=False)}"
            logger.debug(f"Video generation task({duration} s) created: {task_id}")

            if region == "beijing":
                query_endpoint = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
            else:
                query_endpoint = f"https://dashscope-intl.aliyuncs.com/api/v1/tasks/{task_id}"

            query_headers = {
                "Authorization": f"Bearer {api_key}",
            }

            max_wait_time = 600
            poll_interval = 10
            elapsed_time = 0

            while elapsed_time < max_wait_time:
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval

                async with httpx.AsyncClient(timeout=30.0) as client:
                    query_response = await client.get(query_endpoint, headers=query_headers)
                    query_response.raise_for_status()
                    task_result = query_response.json()

                task_status = task_result.get("output", {}).get("task_status", "")
                if task_status == "SUCCEEDED":
                    video_url = task_result.get("output", {}).get("video_url", "")
                    if not video_url:
                        return f"Error: No video_url in response. Response: {json.dumps(task_result, ensure_ascii=False)}"

                    save_path = str(video_path)
                    async with httpx.AsyncClient(timeout=120.0) as download_client:
                        video_response = await download_client.get(video_url)
                        video_response.raise_for_status()
                        with open(save_path, "wb") as f:
                            f.write(video_response.content)

                    logger.info(f"Video generated successfully: {save_path}, duration {duration} s")
                    return f"Video generated successfully, saved to {save_path}"

                elif task_status == "FAILED":
                    error_code = task_result.get("output", {}).get("code", "unknown")
                    error_message = task_result.get("output", {}).get("message", "Unknown error")
                    return f"Error: Video generation failed - [{error_code}] {error_message}"

                elif task_status in ["RUNNING", "PENDING"]:
                    info = f"Task {task_id} status: {task_status}, elapsed: {elapsed_time}s"
                    logger.debug(info)
                    msg = OutboundMessage(
                        channel=self._default_channel,
                        chat_id=self._default_chat_id,
                        content=info,
                        metadata={"msg_type": "text", "_tool_hint": "media", "_progress": True},
                    )
                    await self._send_callback(msg)
                    continue

                else:
                    return f"Error: Unknown task status: {task_status}"

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
