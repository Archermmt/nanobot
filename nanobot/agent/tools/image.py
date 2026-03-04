"""Image vision tool for analyzing images using multimodal LLM models."""

import base64
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.providers.base import LLMProvider
from nanobot.config.loader import load_config


class ImageVisionTool(Tool):
    """
    Tool for analyzing and describing images using multimodal LLM models.

    Supports image analysis, text extraction (OCR), and visual question answering.
    """

    def __init__(self, provider: LLMProvider):
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
                "model_id": {
                    "type": "string",
                    "description": (
                        "The multimodal model to use for image analysis. "
                        "Examples: 'moonshot/kimi-k2.5', 'dashscope/qwen-vl', "
                        "'anthropic/claude-3-opus'. If not specified, uses a default vision model."
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

    async def execute(
        self,
        text: str,
        images: list[str],
        model_id: str = "moonshot/kimi-k2.5",
        **kwargs: Any,
    ) -> str:
        """
        Execute image vision analysis.

        Args:
            text: User's request/question about the image.
            images: List of image file paths.
            model_id: Model identifier for vision analysis.

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
            current_model, change_model = self.provider.get_default_model(), False
            if current_model != model_id:
                self.provider.change_model(load_config(), model_id)
                change_model = True
            response = await self.provider.chat(
                messages=messages,
                model=model_id,
                max_tokens=4096,
                temperature=0.7,
            )
            if change_model:
                self.provider.change_model(load_config(), current_model)
            if response.content:
                return response.content
            else:
                return "Error: No response content from vision model."

        except Exception as e:
            return f"Error calling vision model: {str(e)}"
