"""External tool wrapper for dynamic tool specifications."""

import asyncio
import time
from typing import Any, Callable, Type

from loguru import logger

from ..base import Tool


class ExternTool(Tool):
    """
    External tool wrapper that dynamically creates tools from specifications.

    This class allows creating tools at runtime by providing a specification
    that includes name, description, and input schema.
    """

    _registered_types: dict[str, Type["ExternTool"]] = {}

    def __init__(self, config) -> None:
        """
        Initialize the external tool.

        Args:
            **kwargs: Tool-specific parameters.
        """

        required = ["name", "description", "inputSchema", "chatId"]
        for key in required:
            if key not in config:
                raise ValueError(f"Missing required key in spec: {key}")
        self._chat_id = config["chatId"]
        self._tool_name = config["name"]
        self._name = f"{self._tool_name}_{self._chat_id}"
        self._description = config["description"]
        self._parameters = config["inputSchema"]
        self._result_queue = config.get("result_queue")
        self._timeout = config.get("timeout", 30)
        self.setup(config)

    def setup(self, config: dict[str, Any]) -> None:
        """Setup method to initialize the tool with additional parameters."""
        pass

    @property
    def name(self) -> str:
        """Tool name used in function calls."""
        return self._name

    @property
    def description(self) -> str:
        """Description of what the tool does."""
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the external tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters passed to the external tool.

        Returns:
            String result of the tool execution.

        Raises:
            NotImplementedError: This method should be overridden by subclasses
                or the tool should be configured with an execution handler.
        """
        raise NotImplementedError(
            f"ExternTool '{self._name}' execution not implemented. "
            "Subclass this class and override execute() method."
        )

    async def wait_for_result(
        self, checker: Callable[[dict], bool], max_wait_time: float = 120
    ) -> Any:
        """
        Wait for a result from the queue that matches the checker condition.

        Args:
            checker: A function that takes a result dict and returns True if it matches.
            max_wait_time: Maximum total wait time in seconds. If None, no limit.

        Returns:
            The 'result' field from the matching message, or None if max_wait_time exceeded.

        Raises:
            RuntimeError: If the result contains an error.
            TimeoutError: If no matching result is received within timeout.
        """
        if not self._result_queue:
            return {}
        start_time, result = time.time(), {}
        while True:
            if (time.time() - start_time) >= max_wait_time:
                logger.debug(f"Max wait time {max_wait_time}s exceeded")
                break
            msg = await asyncio.wait_for(self._result_queue.get(), timeout=self._timeout)
            if checker(msg):
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                result = msg["result"]
                break
            else:
                await self._result_queue.put(msg)
                await asyncio.sleep(0.5)
        return result

    @staticmethod
    def register_type(type_name: str, tool_class: Type["ExternTool"]) -> None:
        """
        Register a subclass of ExternTool.

        Args:
            type_name: Unique identifier for the tool type.
            tool_class: The subclass to register.
        """
        ExternTool._registered_types[type_name] = tool_class

    @staticmethod
    def get_registered_type(type_name: str) -> Type["ExternTool"] | None:
        """
        Get a registered subclass by type name.

        Args:
            type_name: The unique identifier of the tool type.

        Returns:
            The registered subclass, or None if not found.
        """
        return ExternTool._registered_types.get(type_name)
