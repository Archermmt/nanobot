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
        self._timeout = config.get("timeout", 30)
        self._result_queue = config.get("result_queue")  # Queue for fetching MCP results
        self._tool_id = config.get("tool_id", 1)
        self._server_url = config.get("server_url")

    async def execute(self, **kwargs: Any) -> str:
        """Execute the CapWorker tool."""
        if not self._websocket:
            raise RuntimeError("WebSocket not initialized")
        if self.name == "trigger_cap_task":
            await self._websocket.send(
                json.dumps(
                    {
                        "type": "cap_task",
                        "content": kwargs["task"],
                        "args": {"server_url": self._server_url},
                    }
                )
            )
        else:
            raise TypeError(f"Unsupported tool {self.name}")

        try:
            raw_result = None
            while True:
                # Get result from queue
                result_data = await asyncio.wait_for(
                    self._result_queue.get(), timeout=self._timeout
                )
                # Check if msg_id matches
                if result_data["chat_id"] == self._chat_id and result_data["tool_id"] == self.name:
                    raw_result = result_data["result"]
                    break
                else:
                    # Put back to queue if not matching
                    await self._result_queue.put(result_data)
                    await asyncio.sleep(0.1)
            return str(raw_result)

        except asyncio.TimeoutError:
            raise TimeoutError("CapWorker tool request timed out")
        except Exception as e:
            raise e


# Automatically register with type 'cap'
ExternTool.register_type("cap", CapTool)
