"""Base handler for processing inbound and outbound messages."""

from abc import ABC, abstractmethod
from typing import Dict, Type

from nanobot.bus.events import InboundMessage, OutboundMessage


class BaseHandler(ABC):
    """Base class for all message handlers (both inbound and outbound)."""

    _registry: Dict[str, Type["BaseHandler"]] = {}

    @classmethod
    def msg_type(cls) -> str:
        """Return the message type for this handler. Must be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement msg_type() class method")

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
                def msg_type(cls) -> str:
                    return "audio"

                @classmethod
                def handler_type(cls) -> str:
                    return "funasr"
        """

        def decorator(subclass: Type["BaseHandler"]) -> Type["BaseHandler"]:
            if not hasattr(subclass, "msg_type") or not callable(subclass.msg_type):
                raise TypeError(f"Subclass {subclass.__name__} must define msg_type() class method")
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

    def can_handle_input(self, msg: InboundMessage) -> bool:
        """
        Check if this handler can process the given inbound message.

        Args:
            msg: The inbound message to check

        Returns:
            True if the message can be handled, False otherwise
        """
        return False

    def can_handle_output(self, msg: OutboundMessage) -> bool:
        """
        Check if this handler can process the given outbound message.

        Args:
            msg: The outbound message to check

        Returns:
            True if the message can be handled, False otherwise
        """
        return False

    async def handle_input(self, msg: InboundMessage) -> InboundMessage:
        """
        Process an inbound message.

        Args:
            msg: The inbound message to process

        Returns:
            The processed inbound message (may be modified or the same instance)
        """
        return msg

    async def handle_output(self, msg: OutboundMessage) -> OutboundMessage:
        """
        Process an outbound message.

        Args:
            msg: The outbound message to process

        Returns:
            The processed outbound message (may be modified or the same instance)
        """
        return msg
