"""CapWorker tool implementation using ExternTool."""

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
        self._timeout = config.get("timeout", 30)
        self._result_queue = config.get("result_queue")  # Queue for fetching MCP results
        self._tool_id = config.get("tool_id", 1)

    async def execute(self, **kwargs: Any) -> str:
        """Execute the CapWorker tool."""
        if not self._websocket:
            raise RuntimeError("WebSocket not initialized")
        if self.name == "send_task_to_capworker":
            await self._websocket.send(json.dumps({"type": "cap_task", "content": kwargs["task"]}))
        else:
            raise TypeError(f"Unsupported tool {self.name}")


# Automatically register with type 'cap'
ExternTool.register_type("cap", CapTool)
