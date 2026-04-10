"""WebSocket base protocol for handling WebSocket message processing."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Type

from loguru import logger

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

    Registration:
        Use @BaseProto.register() decorator to register a protocol handler.
        The protocol name is obtained from the subclass's proto_name() class method.

        Usage:
            @BaseProto.register()
            class MyProto(BaseProto):
                @classmethod
                def proto_name(cls) -> str:
                    return "my_protocol"
    """

    _registry: Dict[str, Type["BaseProto"]] = {}

    def __init__(self, config: Any = None, ws_config: Any = None):
        """
        Initialize the WebSocket base protocol.

        Args:
            config: Protocol-specific configuration.
            ws_config: WebSocket channel configuration (for host, port, etc.).
        """
        self.config = config
        self.ws_config = ws_config

    @classmethod
    def register(cls):
        """
        Decorator to register a protocol handler subclass.
        The protocol name is obtained from the subclass's proto_name() class method.

        Usage:
            @BaseProto.register()
            class MyProto(BaseProto):
                @classmethod
                def proto_name(cls) -> str:
                    return "my_protocol"
        """

        def decorator(subclass: Type["BaseProto"]) -> Type["BaseProto"]:
            if not hasattr(subclass, "proto_name") or not callable(subclass.proto_name):
                raise TypeError(
                    f"Subclass {subclass.__name__} must define proto_name() class method"
                )
            proto_name = subclass.proto_name()
            cls._registry[proto_name] = subclass
            logger.debug("Registered protocol handler: {} -> {}", proto_name, subclass.__name__)
            return subclass

        return decorator

    @classmethod
    def get_registered_proto(cls, proto_name: str) -> Type["BaseProto"] | None:
        """
        Get a registered protocol handler class by protocol name.

        Args:
            proto_name: The protocol name to look up

        Returns:
            The registered protocol handler class, or None if not found
        """
        return cls._registry.get(proto_name)

    @classmethod
    def get_all_protos(cls) -> Dict[str, Type["BaseProto"]]:
        """Get all registered protocol handlers."""
        return cls._registry.copy()

    @classmethod
    def clear_registry(cls) -> None:
        """Clear all registered protocol handlers."""
        cls._registry.clear()

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
        return None

    async def start(self) -> None:
        """
        Start the protocol handler.

        This method is called when the WebSocket channel starts.
        Subclasses can override this to perform initialization tasks.
        """
        pass

    async def stop(self) -> None:
        """
        Stop the protocol handler.

        This method is called when the WebSocket channel stops.
        Subclasses can override this to perform cleanup tasks.
        """
        pass

    @abstractmethod
    async def receive_msg(self, msg_data: dict, client_info: dict, websocket) -> dict | None:
        """
        Receive and process incoming message from WebSocket.

        Subclasses must implement this method to parse and handle received messages.

        Args:
            msg_data: Raw message data (JSON string or binary data).
            client_info: Client connection information (sender_id, chat_id, etc.).
            websocket: The WebSocket connection object.
        """
        pass

    @abstractmethod
    async def send_msg(self, msg: OutboundMessage, websocket: Any) -> dict:
        """
        Send a message through WebSocket.

        Args:
            msg: Outbound message to send.
            websocket: The WebSocket connection object.

        Returns:
            info: A dictionary containing information about the sent message.
        """
        pass
