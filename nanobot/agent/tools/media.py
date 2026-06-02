"""Unified media tool for handling images, videos, and audio files."""

from __future__ import annotations

import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from nanobot.providers.video_generation import get_video_gen_provider
from nanobot.security.workspace_access import current_tool_workspace
from nanobot.security.workspace_policy import WorkspaceBoundaryError, resolve_allowed_path
from nanobot.utils.artifacts import ArtifactError
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
    media_provider: str = "dashscope"
    image_model: str | None = None
    video_model: str | None = None


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
            provider = self.image_provider_configs.get(self.config.media_provider)
            cls = get_image_gen_provider(self.config.media_provider)
        elif media_type == "video":
            provider = self.image_provider_configs.get(self.config.media_provider)
            cls = get_video_gen_provider(self.config.media_provider)  # TODO: Fix this
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

    def store_artifacts(
        self,
        media_type: str,
        data_url: str,
        *,
        prompt: str = "",
        model: str = "",
        source_images: list[str] | None = None,
        provider: str = "openrouter",
        created_at: datetime | None = None,
        media_path: str | None = None,
    ) -> dict[str, Any]:
        """Store generated media artifacts.

        Args:
            media_type: Type of media (image, video, etc.)
            data_url: Data URL containing the media content
            prompt: Generation prompt
            model: Model used for generation
            source_images: List of source/reference images
            provider: Provider used for generation
            created_at: Creation timestamp
            media_path: Path to save the media file. If not provided, auto-generates path.

        Returns:
            Metadata dictionary with id, path, mime, and other info
        """
        from nanobot.utils.artifacts import (
            ArtifactError,
            decode_image_data_url,
            decode_video_data_url,
        )

        now = created_at or datetime.now().astimezone()
        art_path = Path(media_path)
        art_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = art_path.with_suffix(".json")
        # Create metadata
        metadata: dict[str, Any] = {
            "id": art_path.stem,
            "path": str(media_path),
            "prompt": prompt,
            "model": model,
            "provider": provider,
            "source_images": list(source_images or []),
            "created_at": now.isoformat(),
        }

        if media_type == "image":
            from nanobot.utils.artifacts import _MIME_EXTENSIONS

            raw, mime = decode_image_data_url(data_url)
            ext = _MIME_EXTENSIONS.get(mime)
            if ext is None:
                raise ArtifactError(f"unsupported image MIME type: {mime}")
        elif media_type == "video":
            # For video, we need to decode the data URL and save it first
            from nanobot.utils.artifacts import _VIDEO_MIME_EXTENSIONS

            raw, mime = decode_video_data_url(data_url)
            ext = _VIDEO_MIME_EXTENSIONS.get(mime)
            if ext is None:
                raise ArtifactError(f"unsupported video MIME type: {mime}")
        else:
            raise ValueError(f"Unsupported media type: {media_type}")
        # Write the media data
        art_path.write_bytes(raw)
        metadata["mime"] = mime
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metadata

    async def execute(
        self,
        media_type: str,
        mode: str,
        prompt: str = "",
        media_path: str = "",
        size: str | None = None,
        negative_prompt: str = "",
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

        # If media_path is not absolute, prepend media_dir
        if media_path and not Path(media_path).is_absolute():
            media_path = str(media_dir / media_path)

        if media_type == "image":
            return await self._execute_image(
                mode=mode,
                prompt=prompt,
                size=size or self.config.default_image_size,
                ref_media=ref_media,
                media_path=media_path,
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

        artifacts = [
            {
                "type": media_type,
                "path": str(media_path_obj),
                "mime": mimetypes.guess_type(str(media_path_obj))[0] or "application/octet-stream",
            }
        ]

        return json.dumps(
            {
                "artifacts": artifacts,
                "next_step": (
                    f"You MUST immediately call the message tool now. "
                    f"Pass the artifact path in the media parameter to deliver the {media_type} to the user. "
                    "Do not reply with text alone — the user expects the actual media to be displayed."
                ),
            },
            ensure_ascii=False,
        )

    def _generate_result(self, media_type: str, artifacts: list[dict[str, Any]]) -> str:
        """Generate structured result for media artifacts."""
        return json.dumps(
            {
                "artifacts": artifacts,
                "next_step": (
                    f"Use these artifact paths as reference_{media_type}s for follow-up edits. "
                    "Call the message tool with the artifact paths in the media parameter "
                    f"to deliver the {media_type}s to the user. Keep raw paths internal unless the "
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
        ref_media: str | None = None,
        media_path: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute image operations."""
        if mode == "generate":
            return await self._execute_image_generate(
                prompt=prompt,
                reference_images=None,
                aspect_ratio=None,
                image_size=size,
                media_path=media_path,
                **kwargs,
            )
        elif mode == "edit":
            if not ref_media:
                return "Error: ref_media is required for image editing."
            try:
                resolved_ref = self._resolve_reference_image(ref_media)
            except ImageGenerationError as e:
                return f"Error: {e}"

            return await self._execute_image_generate(
                prompt=prompt,
                reference_images=[resolved_ref],
                aspect_ratio=None,
                image_size=size,
                media_path=media_path,
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
        media_path: str = "",
        **kwargs: Any,
    ) -> str:
        client = self._provider_client("image")
        if client is None:
            return f"Error: unsupported media provider '{self.config.media_provider}'"
        try:
            response = await client.generate(
                prompt=prompt,
                model=self.config.image_model,
                reference_images=reference_images,
                aspect_ratio=aspect_ratio,
                image_size=image_size or self.config.default_image_size,
            )
            artifact = self.store_artifacts(
                "image",
                response.images[0],
                prompt=prompt,
                model=self.config.image_model or "",
                source_images=reference_images,
                provider=self.config.media_provider,
                media_path=media_path if media_path else None,
            )
            return self._generate_result("image", [artifact])
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
            return await self._execute_video_generate(
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

    async def _execute_video_generate(
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
        """Execute video generation using configured video provider."""
        client = self._provider_client("video")
        if client is None:
            return f"Error: unsupported media provider '{self.config.media_provider}'"

        try:
            model = self.config.video_model or os.getenv("DASHSCOPE_VIDEO_GEN_MODEL", "wan2.7-t2v")
            response = await client.generate(
                prompt=prompt,
                model=model,
                resolution=resolution,
                ratio=ratio,
                duration=duration,
                negative_prompt=negative_prompt,
                ref_media=ref_media,
                prompt_extend=prompt_extend,
                watermark=watermark,
                seed=seed,
            )

            artifact = self.store_artifacts(
                "video",
                response.video_data_url,
                prompt=prompt,
                model=model,
                provider=self.config.media_provider,
                media_path=str(video_path),
            )
            return self._generate_result("video", [artifact])
        except (ArtifactError, ValueError, TimeoutError, OSError) as exc:
            return f"Error: {exc}"
        except Exception as e:
            return f"Error: Generation failed - {str(e)}"
