"""Base handler for message processing."""

from abc import ABC, abstractmethod
from typing import Dict, List, Type

from nanobot.bus.events import InboundMessage


class InputHandler(ABC):
    """Base class for all message handlers."""

    _registry: Dict[str, Type["InputHandler"]] = {}

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
    def get_registered_type(cls, msg_type: str, handler_type: str) -> Type["InputHandler"] | None:
        """
        Get a registered handler class by message type.

        Args:
            msg_type: The message type to look up
            handler_type: The handler type to look up

        Returns:
            The registered handler class, or None if not found
        """
        return cls._registry.get(msg_type + "." + handler_type)

    @property
    @abstractmethod
    def supported_msg_types(self) -> List[str]:
        """
        Get list of message types that this handler can process.

        Returns:
            List of supported message type strings (e.g., ["audio", "text", "image"])
        """
        pass

    @abstractmethod
    async def handle(self, msg: InboundMessage) -> InboundMessage:
        """
        Process an inbound message.

        Args:
            msg: The inbound message to process

        Returns:
            The processed inbound message (may be modified or the same instance)
        """
        pass

    def can_handle(self, msg: InboundMessage) -> bool:
        """
        Check if this handler can process the given message.

        Args:
            msg: The inbound message to check

        Returns:
            True if the message type is supported, False otherwise
        """
        msg_type = msg.metadata.get("msg_type", "text")
        return msg_type in self.supported_msg_types
