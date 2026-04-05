"""WebSocket base protocol for handling WebSocket message processing."""

from abc import ABC, abstractmethod
from typing import Any

from nanobot.bus.events import OutboundMessage


class BaseProto(ABC):
    """
    Base class for WebSocket protocols.

    This class provides common functionality for WebSocket message processing including:
    - Message parsing and formatting
    - Media file handling
    - Protocol-specific message routing

    Connection management (start/stop, reconnection, heartbeat) is handled by WebSocketChannel.

    Subclasses should implement:
    - receive_msg(): Process incoming messages
    - send_msg(): Send outgoing messages
    """

    def __init__(self, config: Any = None, ws_config: Any = None):
        """
        Initialize the WebSocket base protocol.

        Args:
            config: Protocol-specific configuration.
            ws_config: WebSocket channel configuration (for host, port, etc.).
        """
        self.config = config
        self.ws_config = ws_config

    @abstractmethod
    async def receive_msg(self, msg_data: dict, client_info: dict) -> None:
        """
        Receive and process incoming message from WebSocket.

        Subclasses must implement this method to parse and handle received messages.

        Args:
            msg_data: Raw message data (JSON string or binary data).
            client_info: Client connection information (sender_id, chat_id, etc.).
        """
        pass

    async def accept(self, websocket) -> dict | None:
        """
        Check if the current websocket can be accepted by this proto.

        This method is called during WebSocket connection establishment to determine
        if this protocol handler should handle the connection.

        Args:
            websocket: The WebSocket connection object.

        Returns:
            A dictionary containing client information if accepted, None otherwise.
            When returning a dict, it should contain at least 'sender_id' and 'chat_id'.
        """
        # Default implementation returns None (not accepted)
        # Subclasses should override this method to provide custom acceptance logic
        return None

    @abstractmethod
    async def send_msg(self, msg: OutboundMessage) -> bool:
        """
        Send a message through WebSocket.

        Subclasses must implement this method to format and send messages.

        Args:
            msg: Message to send.

        Returns:
            True if message was sent successfully, False otherwise.
        """
        pass
