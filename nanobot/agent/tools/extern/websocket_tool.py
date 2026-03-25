"""WebSocket tool implementation using ExternTool."""

import asyncio
import json
from typing import Any

from .extern_tool import ExternTool


class WebsocketTool(ExternTool):
    """
    WebSocket tool that communicates via WebSocket.

    This tool wraps the WebSocket MCP (Model Context Protocol) functionality,
    allowing remote tool execution via WebSocket.
    """

    def setup(self, kwargs: dict[str, Any]) -> None:
        """Setup the tool with WebSocket connection from kwargs."""
        if "websocket" in kwargs:
            self._websocket = kwargs["websocket"]
        self._timeout = kwargs.get("timeout", 30)
        self._result_queue = kwargs.get("result_queue")  # Queue for fetching MCP results

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
        print("\n\n[TMINFO] websocket tool call " + str(message_data))
        # Send message ( works for both client and server mode)
        await self._websocket.send(json.dumps(message_data, ensure_ascii=False))

        # Fetch result from queue
        try:
            raw_result = None
            while True:
                # Get result from queue
                result_data = await asyncio.wait_for(
                    self._result_queue.get(), timeout=self._timeout
                )
                # Check if msg_id matches
                if result_data["msg_id"] == self.name:
                    # Extract result from kwargs (may contain 'result' or 'error')
                    kwargs_result = result_data.get("result", {})
                    if "error" in kwargs_result:
                        raise RuntimeError(kwargs_result["error"])
                    raw_result = kwargs_result.get("result", kwargs_result)
                    break
                else:
                    # Put back to queue if not matching
                    await self._result_queue.put(result_data)
                    await asyncio.sleep(0.1)
            return str(raw_result)

        except asyncio.TimeoutError:
            raise TimeoutError("Tool call request timeout")
        except Exception as e:
            raise e


# Automatically register with type 'xiaozhi'
ExternTool.register_type("websocket", WebsocketTool)
