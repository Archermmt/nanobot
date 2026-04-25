"""CapWorker tool implementation using ExternTool."""

import asyncio
import json
from typing import Any

from .extern_tool import ExternTool


class CapTool(ExternTool):
    """
    CapWorker tool that communicates via WebSocket.

    This tool wraps the CapWorker MCP (Model Context Protocol) functionality,
    allowing remote code generation and decision making on Cap agents.
    """

    def setup(self, config: dict[str, Any]) -> None:
        """Setup the tool with WebSocket connection from kwargs."""
        if "websocket" in config:
            self._websocket = config["websocket"]
        self._timeout = config.get("timeout", 150)
        self._server_url = config.get("server_url")

    async def execute(self, **kwargs: Any) -> str:
        """Execute the CapWorker tool."""
        if not self._websocket:
            raise RuntimeError("WebSocket not initialized")
        if self._tool_name == "trigger_cap_task":
            await self._websocket.send(
                json.dumps(
                    {
                        "type": "cap_task",
                        "content": kwargs["task"],
                        "args": {"server_url": self._server_url, "model": "nanobot"},
                    }
                )
            )
        else:
            raise TypeError(f"Unsupported tool {self._tool_name}")

        # wait for result
        def _checker(result: dict) -> bool:
            return self._chat_id == result["chat_id"] and self._tool_name == result["tool_name"]

        result = await self.wait_for_result(_checker)
        return str(result)


ExternTool.register_type("cap", CapTool)
