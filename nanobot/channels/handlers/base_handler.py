"""Base handler for processing inbound and outbound messages."""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Dict, Type


@dataclass
class HandlerMessage:
    """Message received from a chat channel."""

    content: str | None = None  # Message text
    media: list[str] = field(default_factory=list)  # Media URLs
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data
    error: str | None = None


class BaseHandler(ABC):
    """Base class for all message handlers (both inbound and outbound)."""

    _registry: Dict[str, Type["BaseHandler"]] = {}
    name: str = ""  # Handler identifier (to be set by subclasses)
    config_cls: Any = None  # Pydantic config class (to be set by subclasses)

    @classmethod
    def register(cls):
        """
        Decorator to register a subclass with its handler type.
        The handler type is obtained from the subclass's handler_type() class method,
        and the message type is obtained from msg_type().

        Usage:
            @BaseHandler.register()
            class MyHandler(BaseHandler):
                @classmethod
                def handler_type(cls) -> str:
                    return "funasr"
        """

        def decorator(subclass: Type["BaseHandler"]) -> Type["BaseHandler"]:
            if not hasattr(subclass, "handler_type") or not callable(subclass.handler_type):
                raise TypeError(
                    f"Subclass {subclass.__name__} must define handler_type() class method"
                )
            if not getattr(subclass, "name", None):
                raise TypeError(f"Subclass {subclass.__name__} must define name class attribute")
            if not getattr(subclass, "config_cls", None):
                raise TypeError(
                    f"Subclass {subclass.__name__} must define config_cls class attribute"
                )
            h_type = subclass.handler_type()
            cls._registry[h_type] = subclass
            return subclass

        return decorator

    @classmethod
    def get_registered_type(cls, handler_type: str) -> Type["BaseHandler"] | None:
        """
        Get a registered handler class by handler type.

        Args:
            handler_type: The handler type to look up

        Returns:
            The registered handler class, or None if not found
        """
        return cls._registry.get(handler_type)

    async def process(self, msg: HandlerMessage) -> HandlerMessage:
        """
        Process a message (unified handler for both input and output).

        Args:
            msg: The message to process

        Returns:
            The processed message (may be modified or the same instance)
        """
        return msg
