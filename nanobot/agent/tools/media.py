"""Unified media tool for handling images, videos, and audio files."""

from __future__ import annotations

import json
import mimetypes
import os
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from pydantic import Field

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import ContextAware, RequestContext
from nanobot.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.bus.events import OutboundMessage
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
    vis_analyze: bool = True


@tool_parameters(
    tool_parameters_schema(
        media_type=StringSchema(
            "Type of media to process: 'image', 'video', 'audio', 'html', or 'mesh'.",
            enum=["image", "video", "audio", "html", "mesh"],
        ),
        mode=StringSchema(
            "Operation mode. For image: 'list', 'display', 'generate', 'edit', 'analyze'. "
            "For video: 'list', 'display', 'generate', 'analyze'. "
            "For audio/html/mesh: 'list', 'display', 'analyze'.",
        ),
        prompt=StringSchema(
            "[Image/Video display/generate/analyze] Text prompt, caption, generation instruction, or analysis question.",
        ),
        media_path=StringSchema(
            "[Image/Video display/analyze] Path to the media file. "
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
class MediaTool(Tool, ContextAware):
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
            provider=ctx.provider,
            send_callback=ctx.bus.publish_outbound if ctx.bus else None,
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: MediaToolConfig,
        image_provider_configs: dict[str, ProviderConfig] | None = None,
        provider: Any | None = None,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.image_provider_configs = image_provider_configs or {}
        self.provider = provider
        self._send_callback = send_callback
        self._default_channel: ContextVar[str] = ContextVar("media_default_channel", default="")
        self._default_chat_id: ContextVar[str] = ContextVar("media_default_chat_id", default="")
        self._default_message_id: ContextVar[str | None] = ContextVar(
            "media_default_message_id",
            default=None,
        )
        self._default_metadata: ContextVar[dict[str, Any]] = ContextVar(
            "media_default_metadata",
            default={},
        )

    def set_context(self, ctx: RequestContext) -> None:
        """Set the current message context."""
        self._default_channel.set(ctx.channel)
        self._default_chat_id.set(ctx.chat_id)
        self._default_message_id.set(ctx.message_id)
        self._default_metadata.set(dict(ctx.metadata or {}))

    @property
    def name(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return (
            "Unified tool for handling different types of media (images, videos, audio, html, mesh). "
            "Supports five media types:\n"
            "- image: List, display, generate, edit, or analyze images\n"
            "  * list: List all available image files in the media directory\n"
            "  * display: Display images to users through WebSocket channel\n"
            "  * generate: Generate images from text prompts using configured image provider\n"
            "  * edit: Edit an existing image using text prompts\n"
            "  * analyze: Analyze images using multimodal LLM (OCR, description, visual QA)\n"
            "- video: List, display, generate, or analyze videos\n"
            "  * list: List all available video files in the media directory\n"
            "  * display: Display videos to users through WebSocket channel\n"
            "  * generate: Generate videos from text prompts using configured video provider\n"
            "  * analyze: Analyze videos using multimodal LLM\n"
            "- audio: List, display, or analyze audio files\n"
            "  * list: List all available audio files in the media directory\n"
            "  * display: Play an audio file by sending it as media\n"
            "  * analyze: Analyze audio content using multimodal LLM\n"
            "- html: List, display, or analyze HTML content\n"
            "  * list: List all available HTML files\n"
            "  * display: Render HTML content\n"
            "  * analyze: Analyze HTML content structure and meaning\n"
            "- mesh: List, display, or analyze 3D mesh files\n"
            "  * list: List all available mesh files\n"
            "  * display: Display 3D mesh models\n"
            "  * analyze: Analyze 3D mesh properties and structure\n"
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
        media_path: str = "",
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

        # If media_path is not provided, generate a temporary path
        if not media_path:
            import time

            timestamp = int(time.time() * 1000)  # millisecond timestamp
            art_path = get_media_dir(media_type) / f"{timestamp}{ext}"
        else:
            art_path = Path(media_path)

        art_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = art_path.with_suffix(".json")
        # Create metadata
        metadata: dict[str, Any] = {
            "id": art_path.stem,
            "path": str(art_path),
            "prompt": prompt,
            "model": model,
            "provider": provider,
            "source_images": list(source_images or []),
            "created_at": now.isoformat(),
        }

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
        if mode == "analyze":
            return await self._execute_analyze(
                media_type=media_type, media_path=media_path, prompt=prompt
            )
        if media_path:
            media_path = str(self._get_media_path(media_path, media_type))
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
                media_path=media_path,
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

        media_dir = get_media_dir(media_type)
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

    async def _execute_display(self, media_path: str, media_type: str) -> str:
        """Execute media display."""
        try:
            media_path = self._get_media_path(media_path, media_type, check_exist=True)
        except FileNotFoundError as e:
            return f"Error: {e}"

        if media_type in {"image", "video", "audio"}:
            content = f"Displayed {media_type}: {media_path}"
            if await self._send_media(media_path, content=content):
                return
            return f"Error displaying media {media_type}: {media_path}"

        try:
            return Path(media_path).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return f"Error reading file content: {str(e)}"

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
        if mode == "edit":
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
                media_path=media_path,
            )
            content = f"Generated image: {artifact['path']}"
            if await self._send_media(str(artifact["path"]), content=content):
                return
            return f"Error sending media image: {artifact['path']}"
        except (ArtifactError, ImageGenerationError, OSError) as exc:
            return f"Error: {exc}"

    async def _execute_video(
        self,
        mode: str,
        prompt: str = "",
        media_path: str = "",
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
        if mode == "generate":
            return await self._execute_video_generate(
                prompt=prompt,
                media_path=media_path,
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
        return f"Error: Invalid mode '{mode}' for video. Must be 'list', 'display', 'generate', or 'edit'."

    async def _execute_video_generate(
        self,
        prompt: str,
        media_path: str = "",
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
                media_path=media_path,
            )
            content = f"Generated video: {artifact['path']}"
            if await self._send_media(str(artifact["path"]), content=content):
                return
            return f"Error sending media video: {artifact['path']}"
        except (ArtifactError, ValueError, TimeoutError, OSError) as exc:
            return f"Error: {exc}"
        except Exception as e:
            return f"Error: Generation failed - {str(e)}"

    async def _execute_analyze(self, media_type: str, media_path: str, prompt: str = "") -> str:
        """Execute media analysis using multimodal LLM.

        This is a generic analyze function that works for all media types.
        It encodes the media file and sends it to the provider for analysis.

        Args:
            media_type: Type of media (image, video, audio, html, mesh)
            media_path: Path to the media file to analyze
            prompt: Analysis question or instruction

        Returns:
            Analysis result from the multimodal LLM
        """
        if self.provider is None:
            return (
                "Error: Provider not configured for analyze mode. "
                "The tool needs access to a multimodal LLM provider."
            )

        # Validate media path
        try:
            media_path = self._get_media_path(media_path, media_type, check_exist=True)
        except FileNotFoundError as e:
            return f"Error: {e}"

        # Encode media file to base64 data URL
        try:
            media_data = self._encode_media_to_data_url(media_path, media_type)
        except Exception as e:
            return f"Error encoding media file: {str(e)}"

        # Determine content type based on media type
        content_type_map = {
            "image": "image_url",
            "video": "video_url",
            "audio": "audio_url",
            "html": "text",
            "mesh": "text",
        }

        content_type = content_type_map.get(media_type)
        if content_type is None:
            return f"Error: Unsupported media type for analysis: {media_type}"

        # Build message content
        content: list[dict[str, Any]] = []

        # Add prompt/question
        if prompt:
            content.append({"type": "text", "text": prompt})
        else:
            content.append(
                {
                    "type": "text",
                    "text": f"Please analyze this {media_type} file and provide a detailed description.",
                }
            )

        # Add media content
        if content_type == "text":
            # For HTML and mesh, read as text
            try:
                text_content = Path(media_path).read_text(encoding="utf-8", errors="ignore")
                content.append({"type": "text", "text": text_content[:10000]})  # Limit size
            except Exception as e:
                return f"Error reading text content: {str(e)}"
        else:
            # For image, video, audio, use data URL
            content.append({"type": content_type, content_type: {"url": media_data}})

        # Build messages for multimodal chat
        messages = [
            {
                "role": "system",
                "content": f"You are a multimodal AI assistant capable of analyzing {media_type} files.",
            },
            {"role": "user", "content": content},
        ]

        # Call provider's chat method with multimodal mode
        response = await self.provider.chat(messages=messages)
        if response and response.content:
            if self.config.vis_analyze and media_type in {"image", "video"}:
                if await self._send_media(media_path, content=response.content):
                    return
            return response.content
        return f"Error: No analysis result for {media_path}."

    def _encode_media_to_data_url(self, media_path: str, media_type: str) -> str:
        """Encode media file to base64 data URL.

        Args:
            media_path: Path to the media file
            media_type: Type of media (image, video, audio)

        Returns:
            Base64 encoded data URL string
        """
        import base64

        path = Path(media_path)
        if not path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")

        # Get MIME type
        mime_type = mimetypes.guess_type(str(path))[0]
        if mime_type is None:
            # Default MIME types based on media_type
            default_mimes = {
                "image": "image/png",
                "video": "video/mp4",
                "audio": "audio/mpeg",
            }
            mime_type = default_mimes.get(media_type, "application/octet-stream")

        # Read and encode file
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        return f"data:{mime_type};base64,{encoded}"

    def _get_media_path(self, media_path: str, media_type: str, check_exist: bool = False) -> str:
        """Get the absolute path for a media file.

        Args:
            media_path: Media file path (relative or absolute)
            media_type: Media type (image/video/audio)
            check_exist: If True, check if file exists and raise error if not

        Returns:
            Absolute path as string
        """
        path = Path(media_path)
        if not path.is_absolute():
            path = get_media_dir(media_type) / path

        if check_exist and not path.exists():
            raise FileNotFoundError(f"Media file not found: {path}")

        return str(path)

    async def _send_media(self, media_path: str, content: str = "") -> bool:
        """Send a media attachment to the current output channel."""
        if not self._send_callback:
            return False
        channel = self._default_channel.get()
        chat_id = self._default_chat_id.get()
        if not channel or not chat_id:
            return False

        metadata = dict(self._default_metadata.get())
        if message_id := self._default_message_id.get():
            metadata["message_id"] = message_id
        metadata["_record_channel_delivery"] = True
        try:
            await self._send_callback(
                OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=content,
                    media=[media_path],
                    metadata=metadata,
                )
            )
        except Exception:
            return False
        return True
