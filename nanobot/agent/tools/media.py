"""Unified media tool for handling images, videos, and audio files."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import Field

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config.paths import get_media_dir
from nanobot.config.schema import Base
from nanobot.providers.image_generation import ImageGenerationError, get_image_gen_provider
from nanobot.security.workspace_access import current_tool_workspace
from nanobot.security.workspace_policy import WorkspaceBoundaryError, resolve_allowed_path
from nanobot.utils.artifacts import (
    ArtifactError,
    store_generated_image_artifact,
    store_generated_video_artifact,
)
from nanobot.utils.helpers import detect_image_mime

if TYPE_CHECKING:
    from nanobot.config.schema import ProviderConfig


class MediaToolConfig(Base):
    """Media tool configuration."""

    enabled: bool = False
    max_images_per_turn: int = Field(default=4, ge=1, le=8)
    default_image_size: str = "1024*1024"
    default_video_resolution: str = "1080P"
    default_video_ratio: str = "16:9"
    default_video_duration: int = Field(default=5, ge=2, le=15)
    image_provider: str = "dashscope"
    video_provider: str = "dashscope"


@tool_parameters(
    tool_parameters_schema(
        media_type=StringSchema(
            "Type of media to process: 'image', 'video', 'audio', 'html', or 'mesh'.",
            enum=["image", "video", "audio", "html", "mesh"],
        ),
        mode=StringSchema(
            "Operation mode. For image: 'list', 'display', 'generate', 'edit'. "
            "For video: 'list', 'display', 'generate'. "
            "For audio/html/mesh: 'list', 'display'.",
        ),
        prompt=StringSchema(
            "[Image/Video display/generate] Text prompt, caption, or generation instruction.",
        ),
        media_path=StringSchema(
            "[Image/Video display] Path to the media file. "
            "[Image/Video generate] File name where generated media will be saved.",
        ),
        size=StringSchema(
            "[Optional for image generate] Output image resolution in format 'width*height'. Default is 1024*1024.",
        ),
        negative_prompt=StringSchema(
            "[Optional for image/video generate] Negative prompt describing what should NOT appear. Max 500 characters.",
        ),
        count=IntegerSchema(
            description="[Optional for image generate] Number of images to generate (1-6). Default is 1.",
            minimum=1,
            maximum=6,
        ),
        prompt_extend=BooleanSchema(
            description="[Optional for image/video generate] Enable AI-powered prompt enhancement. Default is true.",
        ),
        watermark=BooleanSchema(
            description="[Optional for image/video generate] Add watermark. Default is false.",
        ),
        ref_media=StringSchema(
            "[For image edit] Reference image path for editing. "
            "[For video generate] URL or path of audio file to use as background music.",
        ),
        resolution=StringSchema(
            "[Optional for video generate] Output video resolution. Default is 1080P.",
            enum=["720P", "1080P"],
        ),
        ratio=StringSchema(
            "[Optional for video generate] Aspect ratio. Default is 16:9.",
            enum=["16:9", "9:16", "1:1", "4:3", "3:4"],
        ),
        duration=IntegerSchema(
            description="[Optional for video generate] Duration in seconds (2-15). Default is 5.",
            minimum=2,
            maximum=15,
        ),
        seed=IntegerSchema(
            description="[Optional for video generate] Random seed for reproducible results.",
        ),
        required=["media_type", "mode"],
    )
)
class MediaTool(Tool):
    """Unified tool for handling different types of media (images, videos, audio, html, mesh)."""

    config_key = "media"

    @classmethod
    def config_cls(cls):
        return MediaToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return ctx.config.media.enabled

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        return cls(
            workspace=ctx.workspace,
            config=ctx.config.media,
            image_provider_configs=ctx.image_generation_provider_configs,
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: MediaToolConfig,
        image_provider_configs: dict[str, ProviderConfig] | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.image_provider_configs = image_provider_configs or {}

    @property
    def name(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return (
            "Unified tool for handling different types of media (images, videos, audio, html, mesh). "
            "Supports five media types:\n"
            "- image: List, display, generate, or edit images\n"
            "  * list: List all available image files in the media directory\n"
            "  * display: Display images to users through WebSocket channel\n"
            "  * generate: Generate images from text prompts using configured image provider\n"
            "  * edit: Edit an existing image using text prompts\n"
            "- video: List, display, or generate videos\n"
            "  * list: List all available video files in the media directory\n"
            "  * display: Display videos to users through WebSocket channel\n"
            "  * generate: Generate videos from text prompts using configured video provider\n"
            "- audio: List or display audio files\n"
            "  * list: List all available audio files in the media directory\n"
            "  * display: Play an audio file by sending it as media\n"
            "The media_type parameter determines which type of media to process."
        )

    def _provider_client(self, media_type: str) -> Any:
        if media_type == "image":
            provider = self.image_provider_configs.get(self.config.image_provider)
            cls = get_image_gen_provider(self.config.image_provider)
        else:
            provider = None
            cls = None
        if cls is None:
            return None
        kwargs = {
            "api_key": provider.api_key if provider else None,
            "api_base": provider.api_base if provider else None,
            "extra_headers": provider.extra_headers if provider else None,
            "extra_body": provider.extra_body if provider else None,
        }
        return cls(**kwargs)

    def _resolve_reference_image(self, value: str) -> str:
        access = current_tool_workspace(self.workspace, restrict_to_workspace=True)
        workspace = access.project_path or self.workspace
        try:
            resolved = resolve_allowed_path(
                value,
                workspace=workspace,
                allowed_root=access.allowed_root,
                extra_allowed_roots=[get_media_dir()] if access.allowed_root is not None else None,
                strict=True,
            )
        except (WorkspaceBoundaryError, OSError):
            raise ImageGenerationError(f"Reference image not found or not accessible: {value}")

        if not resolved.is_file():
            raise ImageGenerationError(f"Reference image is not a file: {value}")
        raw = resolved.read_bytes()
        if detect_image_mime(raw) is None:
            raise ImageGenerationError(f"Unsupported reference image format: {value}")
        return str(resolved)

    def _resolve_reference_images(self, values: list[str] | None) -> list[str]:
        if not values:
            return []
        return [self._resolve_reference_image(value) for value in values if value]

    async def execute(
        self,
        media_type: str,
        mode: str,
        prompt: str = "",
        media_path: str = "",
        size: str | None = None,
        negative_prompt: str = "",
        count: int | None = None,
        prompt_extend: bool = True,
        watermark: bool = False,
        ref_media: str | None = None,
        resolution: str | None = None,
        ratio: str | None = None,
        duration: int | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute media tool based on media_type and mode."""
        if mode == "list":
            return await self._execute_list(media_type=media_type)
        if mode == "display":
            return await self._execute_display(media_path=media_path, media_type=media_type)

        # Calculate media_dir based on media_type
        media_dir = get_media_dir() / media_type
        media_dir.mkdir(parents=True, exist_ok=True)

        if media_type == "image":
            return await self._execute_image(
                mode=mode,
                prompt=prompt,
                size=size or self.config.default_image_size,
                count=count,
                ref_media=ref_media,
                **kwargs,
            )
        elif media_type == "video":
            return await self._execute_video(
                mode=mode,
                prompt=prompt,
                video_path=media_path,
                media_dir=media_dir,
                resolution=resolution or self.config.default_video_resolution,
                ratio=ratio or self.config.default_video_ratio,
                duration=duration or self.config.default_video_duration,
                negative_prompt=negative_prompt,
                prompt_extend=prompt_extend,
                watermark=watermark,
                seed=seed,
                ref_media=ref_media,
                **kwargs,
            )
        else:
            return f"Error: Invalid media_type '{media_type}'. Must be 'image', 'video', 'audio', 'html', or 'mesh'."

    async def _execute_list(self, media_type: str) -> str:
        """List all available media files based on media type."""
        extensions = {
            "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"},
            "video": {".mp4", ".avi", ".mov", ".mkv", ".webm"},
            "audio": {".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a", ".wma"},
            "html": {".html", ".htm"},
            "mesh": {".stl", ".3mf", ".obj", ".fbx", ".gltf", ".glb"},
        }
        if media_type not in extensions:
            return f"Error: Invalid media_type '{media_type}'. Must be 'image', 'video', 'audio', 'html', or 'mesh'."

        media_dir = get_media_dir() / media_type
        if not media_dir.exists():
            return f"No {media_type} files found. Directory does not exist: {media_dir}"

        media_files: list[Path] = []

        def _list_files(directory: Path) -> None:
            """Recursively list media files in directory."""
            for item in directory.iterdir():
                if item.is_file() and item.suffix.lower() in extensions[media_type]:
                    media_files.append(item)
                elif item.is_dir():
                    _list_files(item)

        _list_files(media_dir)

        if not media_files:
            return f"No {media_type} files found in the media directory."

        media_files.sort(key=lambda x: x.name.lower())

        result = f"Found {len(media_files)} {media_type} file(s):\n\n"
        for idx, file_path in enumerate(media_files, 1):
            size_mb = file_path.stat().st_size / (1024 * 1024)
            result += f"{idx}. {file_path.name} ({size_mb:.2f} MB)\n"
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
        media_path_obj = self._get_media_path(media_path, media_type)
        if not media_path_obj.exists():
            return f"Error: Media file not found: {media_path_obj}"

        # Return artifact result similar to generated_image_tool_result
        artifacts = [
            {
                "type": media_type,
                "path": str(media_path_obj),
                "mime_type": mimetypes.guess_type(str(media_path_obj))[0]
                or "application/octet-stream",
            }
        ]

        result = self._generate_result(media_type, artifacts)
        print(f"[TMINFO] get result {result}", flush=True)
        return result

    def _generate_result(self, media_type: str, artifacts: list[dict[str, Any]]) -> str:
        """Generate structured result for media artifacts."""
        return json.dumps(
            {
                "artifacts": artifacts,
                "next_step": (
                    f"Use this {media_type} artifact path in the message tool's media parameter "
                    f"to deliver the {media_type} to the user. Keep raw paths internal unless the "
                    "user asks for debug details."
                ),
            },
            ensure_ascii=False,
        )

    async def _execute_image(
        self,
        mode: str,
        prompt: str = "",
        size: str = "1024*1024",
        count: int | None = None,
        ref_media: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute image operations."""
        if mode == "generate":
            return await self._execute_image_generate(
                prompt=prompt,
                reference_images=None,
                aspect_ratio=None,
                image_size=size,
                count=count,
                **kwargs,
            )
        elif mode == "edit":
            if not ref_media:
                return "Error: ref_media is required for image editing."
            access = current_tool_workspace(self.workspace, restrict_to_workspace=True)
            workspace = access.project_path or self.workspace
            try:
                resolved = resolve_allowed_path(
                    ref_media,
                    workspace=workspace,
                    allowed_root=access.allowed_root,
                    extra_allowed_roots=[get_media_dir()]
                    if access.allowed_root is not None
                    else None,
                    strict=True,
                )
            except (WorkspaceBoundaryError, OSError):
                return f"Error: Reference image not found or not accessible: {ref_media}"

            if not resolved.is_file():
                return f"Error: Reference image is not a file: {ref_media}"
            raw = resolved.read_bytes()
            if detect_image_mime(raw) is None:
                return f"Error: Unsupported reference image format: {ref_media}"

            return await self._execute_image_generate(
                prompt=prompt,
                reference_images=[str(resolved)],
                aspect_ratio=None,
                image_size=size,
                count=count,
                **kwargs,
            )
        else:
            return f"Error: Invalid mode '{mode}' for image. Must be 'list', 'display', 'generate', or 'edit'."

    async def _execute_image_generate(
        self,
        prompt: str,
        reference_images: list[str] | None = None,
        aspect_ratio: str | None = None,
        image_size: str | None = None,
        count: int | None = None,
        **kwargs: Any,
    ) -> str:
        client = self._provider_client("image")
        if client is None:
            return f"Error: unsupported image generation provider '{self.config.image_provider}'"

        requested = count or 1
        if requested > self.config.max_images_per_turn:
            return (
                "Error: count exceeds tools.media.maxImagesPerTurn "
                f"({self.config.max_images_per_turn})"
            )

        try:
            refs = self._resolve_reference_images(reference_images)
            artifacts: list[dict[str, Any]] = []
            while len(artifacts) < requested:
                response = await client.generate(
                    prompt=prompt,
                    model=self.config.model,
                    reference_images=refs,
                    aspect_ratio=aspect_ratio or self.config.default_aspect_ratio,
                    image_size=image_size or self.config.default_image_size,
                )
                for image_data_url in response.images:
                    artifact = store_generated_image_artifact(
                        image_data_url,
                        prompt=prompt,
                        model=self.config.model,
                        source_images=refs,
                        save_dir=self.config.save_dir,
                        provider=self.config.provider,
                    )
                    artifacts.append(artifact)
                    if len(artifacts) >= requested:
                        break
            return self._generate_result("image", artifacts)
        except (ArtifactError, ImageGenerationError, OSError) as exc:
            return f"Error: {exc}"

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
        video_path_obj = self._get_media_path(video_path or "generated.mp4", "video")

        if mode == "generate":
            if not video_path_obj.exists():
                video_path_obj = media_dir / "generated.mp4" if media_dir else video_path_obj
            return await self._dashscope_video_generate(
                prompt=prompt,
                video_path=video_path_obj,
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
            return "Error: Video editing is not yet supported. Please use generate mode to create new videos."
        else:
            return f"Error: Invalid mode '{mode}' for video. Must be 'list', 'display', 'generate', or 'edit'."

    def _get_media_data(self, media_path: str) -> str:
        """Get media data as base64 encoded string with MIME type."""
        path = Path(media_path)
        if not path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")

        mime_type = mimetypes.guess_type(media_path)[0] or "application/octet-stream"
        if mime_type.startswith("text"):
            with open(path, "r") as media_file:
                data = media_file.read()
            return data

        with open(path, "rb") as media_file:
            encoded = base64.b64encode(media_file.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

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

                    # Store video as artifact and return structured result
                    try:
                        model_name = os.getenv("DASHSCOPE_VIDEO_GEN_MODEL", "wan2.7-t2v")
                        artifact = store_generated_video_artifact(
                            video_path,
                            prompt=prompt,
                            model=model_name,
                            provider="dashscope",
                        )
                        return self._generate_result("video", [artifact])
                    except ArtifactError as exc:
                        return f"Error: {exc}"

                elif task_status == "FAILED":
                    error_code = task_result.get("output", {}).get("code", "unknown")
                    error_message = task_result.get("output", {}).get("message", "Unknown error")
                    return f"Error: Video generation failed - [{error_code}] {error_message}"

                elif task_status in ["RUNNING", "PENDING"]:
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
