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

    def setup(self, kwargs: dict[str, Any]) -> None:
        """Setup the tool with WebSocket connection from kwargs."""
        if "websocket" in kwargs:
            self._websocket = kwargs["websocket"]
        self._timeout = kwargs.get("timeout", 30)
        self._result_queue = kwargs.get("result_queue")  # Queue for fetching MCP results
        self._tool_id = kwargs.get("tool_id", 1)

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
            "id": self._tool_id,
            "method": "tools/call",
            "params": {"name": self.name, "arguments": arguments},
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


# Automatically register with type 'xiaozhi'
ExternTool.register_type("xiaozhi", XiaozhiTool)
