"""Image tools for analyzing and displaying images."""

import base64
from pathlib import Path
from typing import Any, Awaitable, Callable

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage
from nanobot.providers.providers_manager import ProvidersManager


class ImageVisionTool(Tool):
    """
    Tool for analyzing and describing images using multimodal LLM models.

    Supports image analysis, text extraction (OCR), and visual question answering.
    """

    def __init__(self, provider: ProvidersManager):
        """Initialize the agent mode tool with workspace and provider."""
        self.provider = provider

    @property
    def name(self) -> str:
        return "image_vision"

    @property
    def description(self) -> str:
        return (
            "Analyze and describe images using multimodal LLM models. "
            "Supports image description, text extraction (OCR), visual analysis, "
            "and answering questions about image content. "
            "Images are encoded as base64 and sent to the vision model for processing."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "The user's request or question about the image. "
                        "Examples: 'Describe this image', 'Extract text from this image', "
                        "'What objects are in this picture?', 'Is there a cat in this photo?'"
                    ),
                },
                "images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of image paths to analyze. Each path should be an absolute path "
                        "to a local image file (e.g., '/Users/archer/Desktop/photo.png'). "
                        "Supported formats: PNG, JPG, JPEG, GIF, WEBP."
                    ),
                },
            },
            "required": ["text", "images"],
        }

    def _encode_image(self, image_path: str) -> str:
        """
        Encode an image file to base64 string.

        Args:
            image_path: Absolute path to the image file.

        Returns:
            Base64 encoded image string.

        Raises:
            FileNotFoundError: If image file doesn't exist.
            ValueError: If file is not a valid image.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        # Check file extension
        valid_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        if path.suffix.lower() not in valid_extensions:
            raise ValueError(
                f"Unsupported image format: {path.suffix}. " f"Supported formats: {', '.join(valid_extensions)}"
            )

        # Read and encode image
        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("utf-8")

        return encoded

    def _get_mime_type(self, image_path: str) -> str:
        """Get MIME type based on file extension."""
        ext = Path(image_path).suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        return mime_types.get(ext, "image/png")

    async def execute(self, text: str, images: list[str], **kwargs: Any) -> str:
        """
        Execute image vision analysis.

        Args:
            text: User's request/question about the image.
            images: List of image file paths.

        Returns:
            Analysis result from the vision model.
        """
        if not images:
            return "Error: No images provided. Please provide at least one image path."

        content: list[dict[str, Any]] = [{"type": "text", "text": text}]

        # Process each image
        for image_path in images:
            try:
                encoded_image = self._encode_image(image_path)
                mime_type = self._get_mime_type(image_path)

                # Add image to content in OpenAI format
                # Reference: https://platform.moonshot.cn/docs/guide/use-kimi-vision-model
                content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded_image}"}})
            except FileNotFoundError as e:
                return f"Error: {str(e)}"
            except ValueError as e:
                return f"Error: {str(e)}"
            except Exception as e:
                return f"Error encoding image '{image_path}': {str(e)}"

        # Build messages for chat completion
        messages = [{"role": "system", "content": "Your are a multimodal model"}, {"role": "user", "content": content}]
        try:
            response = await self.provider.chat(messages=messages, mode="multimodal")
            if response.content:
                return response.content
            return "Error: No response content from vision model."
        except Exception as e:
            return f"Error calling vision model: {str(e)}"


class DisplayImageTool(Tool):
    """
    Tool for displaying images to users through WebSocket channel.

    This tool reads image files, encodes them as base64, and sends them to the frontend
    for display in the message box.
    """

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
    ):
        """Initialize the display image tool with send callback and default context."""
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    @property
    def name(self) -> str:
        return "display_image"

    @property
    def description(self) -> str:
        return (
            "Display an image to the user by reading it from disk and sending it to the frontend. "
            "This tool reads the image file, encodes it as base64, and sends it via WebSocket "
            "for display in the message box. "
            "Use this when you want to show an image to the user directly."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": (
                        "Path to the image file to display. "
                        "Can be an absolute or relative path. "
                        "Supported formats: PNG, JPG, JPEG, GIF, WEBP, BMP."
                    ),
                },
                "caption": {
                    "type": "string",
                    "description": (
                        "Optional caption to display with the image. "
                        "This text will appear above the image in the message box."
                    ),
                },
            },
            "required": ["image_path"],
        }

    def _encode_image(self, image_path: str) -> tuple[str, str]:
        """
        Encode an image file to base64 string and get MIME type.

        Args:
            image_path: Path to the image file.

        Returns:
            Tuple of (base64 encoded string, MIME type).

        Raises:
            FileNotFoundError: If image file doesn't exist.
            ValueError: If file is not a valid image.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        # Check file extension
        valid_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        if path.suffix.lower() not in valid_extensions:
            raise ValueError(
                f"Unsupported image format: {path.suffix}. " f"Supported formats: {', '.join(valid_extensions)}"
            )

        # Read and encode image
        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("utf-8")

        # Get MIME type
        ext = path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        mime_type = mime_types.get(ext, "image/png")

        return encoded, mime_type

    async def execute(
        self,
        image_path: str,
        caption: str = "",
        **kwargs: Any,
    ) -> str:
        """
        Execute image display by sending image data to frontend.

        Args:
            image_path: Path to the image file to display.
            caption: Optional caption text to display above the image.

        Returns:
            Status message indicating success or error.
        """
        if not self._send_callback:
            return "Error: Message sending not configured"

        try:
            # Encode image to base64
            encoded_image, mime_type = self._encode_image(image_path)

            # Prepare media data for the message
            media_data = {
                "data": f"data:{mime_type};base64,{encoded_image}",
                "file_name": Path(image_path).name,
            }

            # Create outbound message with image as media
            msg = OutboundMessage(
                channel=self._default_channel,
                chat_id=self._default_chat_id,
                content=caption or "Image display",
                media=[media_data],
                metadata={
                    "msg_type": "image",  # Indicate this is an image message
                    "file_type": mime_type,
                },
            )

            # Send the message through the callback
            await self._send_callback(msg)

            return f"Image displayed successfully: {Path(image_path).name}"

        except FileNotFoundError as e:
            return f"Error: {str(e)}"
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error displaying image: {str(e)}"
