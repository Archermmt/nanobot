"""External tool wrapper for dynamic tool specifications."""

from typing import Any, Type

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
        self._name = config["name"]
        self._chat_id = config["chatId"]
        if config.get("bound_session", False):
            self._description = f"[CHAT_ID: {self._chat_id}] {config['description']}\n\n**IMPORTANT**: This tool is exclusively bound to chat session '{self._chat_id}'. Only invoke this tool when you need to perform actions specifically related to this chat session. Do not use this tool for other chat sessions or general purposes."
        else:
            self._description = config["description"]
        self._parameters = config["inputSchema"]
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
