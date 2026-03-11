"""XiaoZhi channel implementation for WebSocket communication with ESP32 devices."""

import asyncio
import json
import websockets
from loguru import logger
from urllib.parse import parse_qs, urlparse

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel


class AuthenticationError(Exception):
    """Exception raised when authentication fails."""

    pass


class XiaoZhiChannel(BaseChannel):
    """
    WebSocket channel for XiaoZhi ESP32 device communication.

    This channel acts as a WebSocket server that:
    1. Accepts connections from ESP32 devices or frontend clients
    2. Receives messages and forwards them to the message bus
    3. Sends responses from the message bus back to connected clients

    Features:
    - Device authentication via device-id, client-id, and authorization headers
    - Support for both header-based and URL parameter-based authentication
    - Automatic connection management and cleanup
    - JSON message format for bidirectional communication

    Message format (incoming):
    {
        "type": "message",
        "content": "Hello",
        "sender_id": "device-123",
        "chat_id": "session-456",
        "metadata": {...}
    }

    Message format (outgoing):
    {
        "type": "message",
        "content": "Hi there!",
        "sender_id": "bot",
        "chat_id": "session-456",
        "metadata": {...}
    }
    """

    name = "xiaozhi"

    def __init__(self, config: any, bus: MessageBus):
        """
        Initialize the XiaoZhi channel.

        Args:
            config: Channel configuration with server settings.
            bus: The message bus for communication.
        """
        super().__init__(config, bus)
        self._ws_server = None
        self._connected_clients: dict[any, dict] = {}
        self._message_handler_task: asyncio.Task | None = None
        self._auth_enabled = False
        self._allowed_devices: set = set()
        self._auth_key = ""

    async def start(self) -> None:
        """Start the WebSocket server and begin listening for connections."""
        self._running = True

        # Get server configuration
        host = getattr(self.config, "host", "0.0.0.0")
        port = getattr(self.config, "port", 8765)
        auth_enabled = getattr(self.config, "auth_enabled", False)
        allowed_devices = getattr(self.config, "allowed_devices", [])
        auth_key = getattr(self.config, "auth_key", "")

        logger.info(
            "Starting XiaoZhi WebSocket server on {}:{} (auth: {})",
            host,
            port,
            "enabled" if auth_enabled else "disabled",
        )

        # Store auth config for later use
        self._auth_enabled = auth_enabled
        self._allowed_devices = set(allowed_devices)
        self._auth_key = auth_key

        # Start WebSocket server
        try:
            async with websockets.serve(
                self._handle_connection,
                host,
                port,
                process_request=self._http_response,
                max_size=20 * 1024 * 1024,
            ):
                logger.info("XiaoZhi WebSocket server started and listening")
                while self._running:
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error("XiaoZhi WebSocket server error: {}", e)
            raise

    async def stop(self) -> None:
        """Stop the WebSocket server and clean up resources."""
        logger.info("Stopping XiaoZhi WebSocket server...")
        self._running = False

        # Close all connected clients
        for ws in list(self._connected_clients.keys()):
            try:
                await ws.close()
            except Exception as e:
                logger.warning("Error closing client connection: {}", e)

        self._connected_clients.clear()

        # Cancel message handler task
        if self._message_handler_task:
            self._message_handler_task.cancel()
            try:
                await self._message_handler_task
            except asyncio.CancelledError:
                pass
            self._message_handler_task = None

        logger.info("XiaoZhi WebSocket server stopped")

    async def _handle_connection(self, websocket: any) -> None:
        """
        Handle a new WebSocket connection.

        Args:
            websocket: The WebSocket connection object.
        """

        # Extract headers
        headers = dict(websocket.request.headers)

        # Try to get device-id from headers or URL parameters
        device_id = headers.get("device-id")
        client_id = headers.get("client-id")
        authorization = headers.get("authorization")

        # If not in headers, try URL parameters
        if not device_id:
            request_path = websocket.request.path
            if request_path:
                parsed_url = urlparse(request_path)
                query_params = parse_qs(parsed_url.query)

                if "device-id" in query_params:
                    device_id = query_params["device-id"][0]
                    headers["device-id"] = device_id

                if "client-id" in query_params:
                    client_id = query_params["client-id"][0]
                    headers["client-id"] = client_id

                if "authorization" in query_params:
                    authorization = query_params["authorization"][0]
                    headers["authorization"] = authorization

        # Validate device-id
        if not device_id:
            logger.warning("Connection rejected: missing device-id")
            await websocket.send("Error: device-id required")
            await websocket.close()
            return

        # Authenticate if enabled
        if self._auth_enabled:
            try:
                await self._authenticate(device_id, client_id, authorization)
            except AuthenticationError as e:
                logger.warning(
                    "Authentication failed for device {}: {}", device_id, str(e)
                )
                await websocket.send(f"Authentication failed: {str(e)}")
                await websocket.close()
                return

        # Register client
        client_info = {
            "device_id": device_id,
            "client_id": client_id or device_id,
            "authenticated": True,
        }
        self._connected_clients[websocket] = client_info

        logger.info(
            "New client connected: device_id={}, client_id={}",
            device_id,
            client_id or device_id,
        )

        try:
            # Handle messages from this client
            await self._handle_client_messages(websocket, client_info)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected: {}", device_id)
        except Exception as e:
            logger.error("Error handling client {}: {}", device_id, e)
        finally:
            # Clean up
            if websocket in self._connected_clients:
                del self._connected_clients[websocket]

            # Close connection if still open
            try:
                if not websocket.closed:
                    await websocket.close()
            except Exception as close_error:
                logger.warning("Error closing connection: {}", close_error)

    async def _authenticate(
        self, device_id: str, client_id: str | None, authorization: str | None
    ) -> None:
        """
        Authenticate a connecting client.

        Args:
            device_id: The device identifier.
            client_id: The client identifier.
            authorization: The authorization token.

        Raises:
            AuthenticationError: If authentication fails.
        """
        # Check whitelist
        if self._allowed_devices and device_id in self._allowed_devices:
            logger.debug("Device {} in whitelist, skipping token validation", device_id)
            return

        # Validate token
        if not authorization:
            raise AuthenticationError("Missing authorization token")

        # Remove 'Bearer ' prefix if present
        token = authorization
        if token.startswith("Bearer "):
            token = token[7:]

        # Simple token validation
        if not token or token != self._auth_key:
            raise AuthenticationError("Invalid authorization token")

        logger.debug("Device {} authenticated successfully", device_id)

    async def _handle_client_messages(self, websocket: any, client_info: dict) -> None:
        """
        Handle messages from a connected client.

        Args:
            websocket: The WebSocket connection.
            client_info: Client information dictionary.
        """
        async for message in websocket:
            if not self._running:
                break

            try:
                # Parse message
                msg_data = json.loads(message)
                await self._process_incoming_message(websocket, msg_data, client_info)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Invalid JSON message from {}: {}", client_info["device_id"], e
                )
                await websocket.send(
                    json.dumps({"type": "error", "content": "Invalid JSON format"})
                )
            except Exception as e:
                logger.error(
                    "Error processing message from {}: {}", client_info["device_id"], e
                )

    async def _process_incoming_message(
        self, websocket: any, msg_data: dict, client_info: dict
    ) -> None:
        """
        Process an incoming message and forward to message bus.

        Args:
            websocket: The WebSocket connection.
            msg_data: The message data.
            client_info: Client information.
        """
        msg_type = msg_data.get("type", "message")

        # Handle special message types
        if msg_type == "heartbeat":
            await websocket.send(
                json.dumps(
                    {
                        "type": "heartbeat_response",
                        "timestamp": asyncio.get_event_loop().time(),
                    }
                )
            )
            return
        elif msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong"}))
            return

        # Only process message type
        if msg_type != "message":
            logger.debug("Ignoring unknown message type: {}", msg_type)
            return

        # Extract message fields
        content = msg_data.get("content", "")
        sender_id = client_info["device_id"]
        chat_id = msg_data.get("chat_id", client_info["client_id"])
        metadata = msg_data.get("metadata", {})

        # Skip empty messages
        if not content and not metadata:
            return

        # Create inbound message
        msg = InboundMessage(
            channel=self.name,
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            media=msg_data.get("media", []),
            metadata=metadata,
        )

        # Publish to message bus
        await self.bus.publish_inbound(msg)
        logger.debug(
            "Forwarded message from device {} to bus: {}",
            sender_id,
            content[:100] if content else "<no content>",
        )

    async def _http_response(self, websocket: any, request_headers: any) -> any:
        """
        Handle HTTP requests (non-WebSocket upgrade requests).

        Args:
            websocket: The WebSocket connection.
            request_headers: The HTTP request headers.

        Returns:
            None for WebSocket upgrade requests, HTTP response otherwise.
        """
        # Check if it's a WebSocket upgrade request
        connection_header = request_headers.headers.get("connection", "").lower()

        if connection_header == "upgrade":
            return None
        else:
            return websocket.respond(200, "XiaoZhi Channel Server is running\n")

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message through the WebSocket channel.

        Args:
            msg: The outbound message to send.
        """
        if not self._running:
            logger.warning("Channel not running, cannot send message")
            return

        # Find the appropriate client connection
        target_ws = None
        for ws, client_info in self._connected_clients.items():
            if (
                client_info["client_id"] == msg.chat_id
                or client_info["device_id"] == msg.chat_id
            ):
                target_ws = ws
                break

        if not target_ws:
            logger.warning("No connected client found for chat_id: {}", msg.chat_id)
            return

        try:
            # Prepare message
            message_data = {
                "type": "message",
                "content": msg.content,
                "sender_id": "bot",
                "chat_id": msg.chat_id,
                "media": msg.media,
                "metadata": msg.metadata,
                "reply_to": msg.reply_to,
                "timestamp": asyncio.get_event_loop().time(),
            }

            # Send message
            await target_ws.send(json.dumps(message_data, ensure_ascii=False))
            logger.debug(
                "Sent message to device {}: {}",
                client_info["device_id"],
                msg.content[:100] if msg.content else "<no content>",
            )

        except Exception as e:
            logger.error("Error sending message to {}: {}", client_info["device_id"], e)
            if target_ws in self._connected_clients:
                del self._connected_clients[target_ws]
