"""Image tools for analyzing and displaying images."""

import base64
from pathlib import Path
from typing import Any, Awaitable, Callable

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage
from nanobot.providers.providers_manager import ProvidersManager


class ImageTool(Tool):
    """
    Tool for analyzing and displaying images.

    Supports two modes:
    - vision: Analyze images using multimodal LLM models (OCR, description, visual QA)
    - display: Display images to users through WebSocket channel
    """

    def __init__(
        self,
        provider: ProvidersManager,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
    ):
        """Initialize the image tool with all required parameters."""
        self.provider = provider
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id

    @property
    def name(self) -> str:
        return "image"

    @property
    def description(self) -> str:
        return (
            "Analyze or display images. Supports two modes:\n"
            "- vision: Analyze and describe images using multimodal LLM models. "
            "Supports image description, text extraction (OCR), visual analysis, "
            "and answering questions about image content.\n"
            "- display: Display images to users by reading from disk and sending to frontend. "
            "Use this when you want to show an image to the user directly.\n"
            "Images are encoded as base64 for processing or display."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["vision", "display"],
                    "description": (
                        "The operation mode: 'vision' for image analysis, 'display' for showing images to users."
                    ),
                },
                "text": {
                    "type": "string",
                    "description": (
                        "[In vision mode] The user's request or question about the image. "
                        "Examples: 'Describe this image', 'Extract text from this image', "
                        "'What objects are in this picture?', 'Is there a cat in this photo?'"
                        "[In display mode] Caption to display with the image. "
                        "This text will appear above the image in the message box."
                    ),
                },
                "image_path": {
                    "type": "string",
                    "description": (
                        "Path to the image file to analyze. Should be an absolute path "
                        "to a local image file (e.g., '/Users/archer/Desktop/photo.png'). "
                        "Supported formats: PNG, JPG, JPEG, GIF, WEBP."
                    ),
                },
            },
            "required": ["mode", "image_path"],
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

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    async def execute(self, mode: str, text: str = "", image_path: str = "", **kwargs: Any) -> str:
        """
        Execute image tool based on mode.

        Args:
            mode: Operation mode - 'vision' for analysis, 'display' for showing images.
            text: [Vision mode] User's request/question about the image. [Display mode] Caption to display with the image.]
            image_path: Path to the image file to display.

        Returns:
            Analysis result (vision mode) or status message (display mode).
        """
        if mode == "vision":
            return await self._execute_vision(text=text, image_path=image_path, **kwargs)
        elif mode == "display":
            return await self._execute_display(text=text, image_path=image_path, **kwargs)
        else:
            return f"Error: Invalid mode '{mode}'. Must be 'vision' or 'display'."

    async def _execute_vision(self, text: str, image_path: str, **kwargs: Any) -> str:
        """
        Execute image vision analysis.

        Args:
            text: User's request/question about the image.
            images: List of image file paths.

        Returns:
            Analysis result from the vision model.
        """
        if not image_path:
            return "Error: No image provided. Please provide at least one image path."

        content: list[dict[str, Any]] = [{"type": "text", "text": text}]

        # Process image
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

    async def _execute_display(self, text: str, image_path: str, **kwargs: Any) -> str:
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
                content=text or "Image display",
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
            return f"Error: {str(e)}"
