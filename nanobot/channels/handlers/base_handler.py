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
    channel: str | None = None  # Channel name
    chat_id: str | None = None  # Chat ID
    session_key_override: str | None = None  # Optional override for session key

    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        if self.session_key_override:
            return self.session_key_override
        return f"{self.channel}:{self.chat_id}" if self.channel and self.chat_id else "unknown"


class BaseHandler(ABC):
    """Base class for all message handlers (both inbound and outbound)."""

    _registry: Dict[str, Type["BaseHandler"]] = {}

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
            h_type = subclass.handler_type()
            cls._registry[h_type] = subclass
            return subclass

        return decorator

    @classmethod
    def get_registered_type(cls, handler_type: str) -> Type["BaseHandler"] | None:
        """
        Get a registered handler class by handler type.
        The message type is obtained from the subclass's msg_type() class method.

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
