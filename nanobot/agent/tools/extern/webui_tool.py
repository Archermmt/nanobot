"""WebSocket tool implementation using ExternTool."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from nanobot.config.paths import get_media_dir
from nanobot.utils.artifacts import decode_image_data_url
from nanobot.utils.media_decode import save_media

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
        if "image_data" in result:
            result["image"] = save_media(
                result.pop("image_data"), self.name + ".jpg", media_dir=get_media_dir("websocket")
            )[0]
        print(f"[TMINFO] WebUI tool '{self._name}' final result: {result}", flush=True)
        return str(result)


ExternTool.register_type("webui", WebUITool)
