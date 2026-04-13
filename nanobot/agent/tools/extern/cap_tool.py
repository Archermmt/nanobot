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

    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the CapWorker tool by calling remote agent via MCP.

        Args:
            **kwargs: Tool parameters including:
                - query_type: Type of query ('code' or 'decision')
                - prompt: Prompt messages for the agent
                - task_description: Description of the task
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

        # Process arguments
        query_type = kwargs.pop("query_type", "code")
        prompt = kwargs.pop("prompt", [])
        task_description = kwargs.pop("task_description", "")

        # Send tool call request
        payload = {
            "jsonrpc": "2.0",
            "id": self._tool_id,
            "method": "tools/call",
            "params": {
                "name": self.name,
                "arguments": {
                    "query_type": query_type,
                    "prompt": prompt,
                    "task_description": task_description,
                    **kwargs,
                },
            },
        }
        message = json.dumps({"type": "mcp", "payload": payload})
        await self._websocket.send(message)

        try:
            raw_result = None
            while True:
                # Get result from queue
                result_data = await asyncio.wait_for(
                    self._result_queue.get(), timeout=self._timeout
                )
                # Check if msg_id matches
                if result_data["msg_id"] == self._tool_id:
                    raw_result = result_data["result"]
                    break
                else:
                    # Put back to queue if not matching
                    await self._result_queue.put(result_data)
                    await asyncio.sleep(0.1)

            if isinstance(raw_result, dict):
                if raw_result.get("isError") is True:
                    error_msg = raw_result.get("error", "工具调用返回错误，但未提供具体错误信息")
                    raise RuntimeError(f"工具调用错误：{error_msg}")

                content = raw_result.get("content")
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict) and "text" in content[0]:
                        return content[0]["text"]

            return str(raw_result)

        except asyncio.TimeoutError:
            raise TimeoutError("工具调用请求超时")
        except Exception as e:
            raise e


# Automatically register with type 'cap'
ExternTool.register_type("cap", CapTool)
