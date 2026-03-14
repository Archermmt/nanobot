"""Xiaozhi device tool implementation using ExternTool."""

import asyncio
import json
import re
from typing import Any

from .extern_tool import ExternTool


class XiaozhiTool(ExternTool):
    """
    Xiaozhi device tool that communicates via WebSocket.

    This tool wraps the Xiaozhi device MCP (Model Context Protocol) functionality,
    allowing remote tool execution on Xiaozhi devices.
    """

    def __init__(self, spec: dict[str, Any], **kwargs) -> None:
        super().__init__(spec, **kwargs)
        self._websocket = None
        self._timeout = 30
        self._next_id = 1
        self._lock = asyncio.Lock()

    @classmethod
    def __init_subclass__(cls, **kwargs):
        """Automatically register subclasses with type 'xiaozhi'."""
        super().__init_subclass__(**kwargs)
        ExternTool.register_type("xiaozhi", cls)

    def setup(self, kwargs: dict[str, Any]) -> None:
        """Setup the tool with WebSocket connection from kwargs."""
        if "websocket" in kwargs:
            self._websocket = kwargs["websocket"]
        self._timeout = kwargs.get("timeout", 30)

    async def _get_next_id(self) -> int:
        """Get next unique ID for tool calls."""
        async with self._lock:
            current_id = self._next_id
            self._next_id += 1
            return current_id

    async def _send_mcp_message(self, payload: dict) -> None:
        """Send MCP message via WebSocket."""
        if not self._websocket:
            raise RuntimeError("WebSocket not initialized")

        message = json.dumps({"type": "mcp", "payload": payload})
        await self._websocket.send(message)

    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the Xiaozhi tool by calling remote device via MCP.

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
        args = kwargs.get("args", "{}")
        if not self._websocket:
            raise RuntimeError("WebSocket not initialized")

        # Get next ID and create future for result
        tool_call_id = await self._get_next_id()

        # Process arguments
        try:
            if isinstance(args, str):
                if not args.strip():
                    arguments = {}
                else:
                    try:
                        arguments = json.loads(args)
                    except json.JSONDecodeError:
                        # Try to merge multiple JSON objects
                        try:
                            json_objects = re.findall(r"\{[^{}]*\}", args)
                            if len(json_objects) > 1:
                                merged_dict = {}
                                for json_str in json_objects:
                                    try:
                                        obj = json.loads(json_str)
                                        if isinstance(obj, dict):
                                            merged_dict.update(obj)
                                    except json.JSONDecodeError:
                                        continue
                                if merged_dict:
                                    arguments = merged_dict
                                else:
                                    raise ValueError(f"无法解析任何有效的 JSON 对象：{args}")
                            else:
                                raise ValueError(f"参数 JSON 解析失败：{args}")
                        except Exception as e:
                            raise ValueError(f"参数 JSON 解析失败：{str(e)}")
            elif isinstance(args, dict):
                arguments = args
            else:
                raise ValueError(f"参数类型错误，期望字符串或字典，实际类型：{type(args)}")

            if not isinstance(arguments, dict):
                raise ValueError(f"参数必须是字典类型，实际类型：{type(arguments)}")

        except Exception as e:
            if not isinstance(e, ValueError):
                raise ValueError(f"参数处理失败：{str(e)}")
            raise e

        # Send tool call request
        payload = {
            "jsonrpc": "2.0",
            "id": tool_call_id,
            "method": "tools/call",
            "params": {"name": self.name, "arguments": arguments},
        }

        await self._send_mcp_message(payload)
        result_future = asyncio.Future()

        try:
            # Wait for response or timeout
            raw_result = await asyncio.wait_for(result_future, timeout=self._timeout)

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


# Automatically register with type 'xiaozhi'
ExternTool.register_type("xiaozhi", XiaozhiTool)
