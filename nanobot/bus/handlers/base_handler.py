"""Base handler for message processing."""

from abc import ABC, abstractmethod
from typing import List

from nanobot.bus.events import InboundMessage


class BaseHandler(ABC):
    """Base class for all message handlers."""

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
