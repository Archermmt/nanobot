"""Base handler for outbound message processing."""

from abc import ABC, abstractmethod
from typing import Dict, List, Type

from nanobot.bus.events import OutboundMessage


class OutputHandler(ABC):
    """Base class for all outbound message handlers."""

    _registry: Dict[str, Type["OutputHandler"]] = {}

    @classmethod
    def register_type(cls, msg_type: str, handler_type: str) -> None:
        """
        Register a subclass with a specific message type.

        Args:
            msg_type: The message type to register (e.g., "audio", "text", "image")
            handler_type: The handler type to register (e.g., "vosk", "funasr")
        """
        cls._registry[msg_type + "." + handler_type] = cls

    @classmethod
    def get_registered_type(cls, msg_type: str, handler_type: str) -> Type["OutputHandler"] | None:
        """
        Get a registered handler class by message type.

        Args:
            msg_type: The message type to look up
            handler_type: The handler type to look up

        Returns:
            The registered handler class, or None if not found
        """
        return cls._registry.get(msg_type + "." + handler_type)

    @abstractmethod
    async def handle(self, msg: OutboundMessage) -> OutboundMessage:
        """
        Process an outbound message.

        Args:
            msg: The outbound message to process

        Returns:
            The processed outbound message (may be modified or the same instance)
        """
        return msg

    def can_handle(self, msg: OutboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The outbound message to check

        Returns:
            True if the message type is supported, False otherwise
        """
        return False
