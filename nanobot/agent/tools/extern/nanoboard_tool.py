"""WebSocket tool implementation using ExternTool."""

import asyncio
import json
from typing import Any

from nanobot.utils.media import save_media

from .extern_tool import ExternTool


class NanoboardTool(ExternTool):
    """
    Nanoboard tool that communicates via WebSocket.

    This tool wraps the WebSocket MCP (Model Context Protocol) functionality,
    allowing remote tool execution via WebSocket.
    """

    def setup(self, config: dict[str, Any]) -> None:
        """Setup the tool with WebSocket connection from kwargs."""
        if "websocket" in config:
            self._websocket = config["websocket"]
        self._timeout = config.get("timeout", 30)

    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the WebSocket tool by calling remote device via MCP.

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

        message_data = {"type": "tool_call", "name": self.name, "kwargs": kwargs}
        await self._websocket.send(json.dumps(message_data, ensure_ascii=False))

        # wait for result
        def _checker(result: dict) -> bool:
            return self._chat_id == result["chat_id"] and self._tool_name == result["tool_name"]

        result = await self.wait_for_result(_checker)
        if "image_data" in result:
            result["image_data"] = save_media(result["image_data"], self.name + ".jpg")[0]
        return str(result)


ExternTool.register_type("nanoboard", NanoboardTool)
