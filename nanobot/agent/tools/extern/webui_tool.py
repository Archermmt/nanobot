"""WebSocket tool implementation using ExternTool."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from nanobot.config.paths import get_media_dir
from nanobot.utils.artifacts import decode_image_data_url

from .extern_tool import ExternTool


class WebUITool(ExternTool):
    """
    WebUI tool that communicates via WebSocket.

    This tool wraps the WebSocket MCP (Model Context Protocol) functionality,
    allowing remote tool execution via WebSocket to the frontend.
    """

    def setup(self, config: dict[str, Any]) -> None:
        """Setup the tool with WebSocket connection from kwargs."""
        if "websocket" in config:
            self._websocket = config["websocket"]
        print(
            f"[TMINFO] init with timeout: {self._timeout}, websocket: {self._websocket}, result_queue: {self._result_queue}",
            flush=True,
        )

    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the WebUI tool by calling frontend via WebSocket.

        Args:
            **kwargs: Tool parameters including:
                - tool_name: Name of the tool to call
                - args: Arguments for the tool (dict or JSON string)
                - timeout: Timeout in seconds (default: 30)

        Returns:
            String result from the tool execution.

        Raises:
            RuntimeError: If WebSocket not initialized or tool call fails.
            TimeoutError: If tool call times out.
            ValueError: If parameters are invalid.
        """

        if not self._websocket:
            raise RuntimeError("WebSocket not initialized")
        if not self._result_queue:
            raise RuntimeError("Result queue not initialized")
        message = {"type": "tool_call", "name": self.name, "kwargs": kwargs}
        print(f"[TMINFO] WebUI tool '{self._name}' send with message: {message}", flush=True)
        await self._websocket.send(json.dumps(message, ensure_ascii=False))

        # wait for result
        def _checker(result: dict) -> bool:
            return self._name == result["tool_name"]

        result = await self.wait_for_result(_checker)
        print(f"[TMINFO] WebUI tool '{self._name}' received result: {result}", flush=True)

        # Handle image data: save to local path and build artifact metadata
        if "image_data" in result:
            image_data_url = result["image_data"]

            # Decode the image data URL
            raw_bytes, mime_type = decode_image_data_url(image_data_url)

            # Determine file extension from MIME type
            mime_to_ext = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
            }
            ext = mime_to_ext.get(mime_type, ".jpg")

            # Generate media path
            media_dir = get_media_dir("websocket")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self._name}_{timestamp}{ext}"
            media_path = media_dir / filename

            # Save the image file
            media_path.write_bytes(raw_bytes)

            # Build artifact metadata (similar to media.py store_artifacts)
            artifact_metadata = {
                "id": media_path.stem,
                "path": str(media_path),
                "mime": mime_type,
                "created_at": datetime.now().astimezone().isoformat(),
            }

            # Build result with artifact info (similar to media.py _generate_result)
            result_with_artifact = json.dumps(
                {
                    "artifacts": [artifact_metadata],
                    "next_step": (
                        "Use this artifact path as reference_image for follow-up operations. "
                        "Call the message tool with the artifact path in the media parameter "
                        "to deliver the image to the provider."
                    ),
                },
                ensure_ascii=False,
            )
            print(f"[TMINFO] result_with_artifact {result_with_artifact}", flush=True)

            return result_with_artifact

        return str(result)


ExternTool.register_type("webui", WebUITool)
