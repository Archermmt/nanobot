"""WebSocket channel implementation for generic WebSocket communication."""

import asyncio
import json

from botpy import Any
from loguru import logger
from pydantic import Field

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import Base


class WebSocketConfig(Base):
    """Generic WebSocket channel configuration."""

    enabled: bool = False
    host: str = "localhost"  # WebSocket server host
    port: int = 8765  # WebSocket server port
    allow_from: list[str] = Field(default_factory=list)  # Allowed sender identifiers
    reconnect_interval: int = 5  # Reconnection interval in seconds
    heartbeat_interval: int = 30  # Heartbeat interval in seconds
    as_server: bool = True  # If True, act as WebSocket server; if False, connect as client
    protos: dict[str, Any] = Field(default_factory=dict)  # Protocol handler configurations


class WebSocketChannel(BaseChannel):
    """
    Generic WebSocket channel for bidirectional communication.

    Uses WebSocket to receive and send messages - no public IP or webhook required.

    Features:
    - Automatic reconnection with exponential backoff
    - Heartbeat mechanism to maintain connection
    - Message deduplication
    - Media file handling (images, audio, files)
    - Authentication support

    Message format:
    Incoming messages should be JSON with structure:
    {
        "type": "message",
        "sender_id": "user123",
        "chat_id": "room456",
        "content": "Hello world",
        "media": ["path/to/file.jpg"],
        "metadata": {...}
    }

    Outgoing messages will be sent in the same format.
    """

    name = "websocket"

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return WebSocketConfig().model_dump(by_alias=True)

    def __init__(self, config: WebSocketConfig, bus: MessageBus):
        """Initialize the WebSocket channel with the given configuration and message bus.

        Args:
            config: WebSocket channel configuration.
            bus: Message bus for communication.
        """
        if isinstance(config, dict):
            config = WebSocketConfig.model_validate(config)
        super().__init__(config, bus)
        self.config: WebSocketConfig = config
        self._ws_client = None
        self._clients: dict[any, dict] = {}  # Track multiple client connections
        self._protos: dict[str, Any] = self._init_protos()
        self._connected = False
        self._heartbeat_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._mcp_result_queue: asyncio.Queue = asyncio.Queue()  # Queue for MCP results
        self._stop_audio = False

    def _init_protos(self) -> None:
        """Initialize protocol handlers discovered via ws_proto directory."""
        from nanobot.channels.ws_proto.registry import discover_all_protos

        # Initialize each discovered protocol handler
        protos: dict[str, Any] = {}
        for name, cls in discover_all_protos().items():
            try:
                section = self.config.protos.get(name, {})
                enabled = (
                    section.get("enabled", True)
                    if isinstance(section, dict)
                    else getattr(section, "enabled", True)
                )
                if not enabled:
                    continue
                # Initialize protocol with config and ws_config
                protos[name] = cls(config=section, ws_config=self.config)
            except Exception as e:
                logger.warning("{} protocol handler not available: {}", name, e)

        logger.info("WebSocket protocol handlers initialized: {}", list(protos.keys()))
        return protos

    async def start(self) -> None:
        """Start the WebSocket channel with reconnection logic."""
        self._running = True
        if self.config.as_server:
            await self._start_server()
        else:
            await self._connect_with_retry()
            # Keep running until stopped
            while self._running:
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the WebSocket channel."""

        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        # Close all connected clients
        for ws in list(self._clients.keys()):
            try:
                await ws.close()
            except Exception as e:
                logger.warning(f"Error closing client {ws} : {e}")
        self._clients.clear()
        self._connected = False
        self._running = False
        logger.info("WebSocket channel stopped")

    async def _start_server(self) -> None:
        """Start WebSocket server to accept client connections."""
        import websockets

        async def handler(websocket, *args):
            """Handle individual WebSocket connections."""
            try:
                await self._get_client_info(websocket)
                self._connected = True
                # Start heartbeat for this connection
                if self.config.heartbeat_interval > 0:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(websocket))
                # Process messages from this client
                await self._receive_messages(websocket)
            except websockets.exceptions.ConnectionClosed:
                logger.info("WebSocket client disconnected")
            except Exception as e:
                logger.error("Error handling WebSocket client: {}", e)
            finally:
                # Clean up
                if websocket in self._clients:
                    del self._clients[websocket]
                self._connected = False
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                    self._heartbeat_task = None
                # Close connection if still open
                try:
                    await websocket.close()
                except Exception as close_error:
                    logger.warning("Error closing connection: {}", close_error)

        # Start server
        try:
            host, port = self.config.host, self.config.port
            async with websockets.serve(handler, host, port, max_size=20 * 1024 * 1024):
                logger.info(f"WebSocket server started and listening on {host}:{port}")
                while self._running:
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error("WebSocket server error: {}", e)
            raise

    async def _connect_with_retry(self) -> None:
        """Connect to WebSocket server with retry logic."""
        import websockets

        server_url = f"ws://{self.config.host}:{self.config.port}"
        while self._running and not self._connected:
            try:
                logger.info("Connecting to WebSocket server at {}", server_url)
                self._ws_client = await websockets.connect(server_url)
                await self._get_client_info(self._ws_client)
                self._connected = True
                # Start heartbeat
                if self.config.heartbeat_interval > 0:
                    self._heartbeat_task = asyncio.create_task(
                        self._heartbeat_loop(self._ws_client)
                    )
                # Start message receiving
                await self._receive_messages(self._ws_client)
            except Exception as e:
                if self._running:
                    logger.warning(
                        "WebSocket connection failed: {}, retrying in {}s",
                        e,
                        self.config.reconnect_interval,
                    )
                    await asyncio.sleep(self.config.reconnect_interval)
                else:
                    break

    async def _receive_messages(self, websocket) -> None:
        """Handle incoming messages from connected clients."""
        async for message in websocket:
            if not self._running:
                break
            await self._receive_message(message, websocket)

    async def _receive_message(self, message: str | bytes, websocket: Any) -> None:
        """Process an incoming message from WebSocket."""

        msg_data = None
        try:
            if isinstance(message, str):
                msg_data = json.loads(message)
            else:
                msg_data = {"type": type(message).__name__, "data": message}
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON message received: {}", e)
        except Exception as e:
            logger.error("Error processing message: {}", e)
        if not msg_data:
            return
        # Common message processing
        msg_type = msg_data.get("type", "message")
        if msg_type == "heartbeat":
            await self._send_heartbeat_response()
            return

        # Get client info
        client_info = await self._get_client_info(websocket)
        if not client_info:
            logger.warning("No protocol handler accepted the connection")
            return
        # Process message using protocol handler
        proto_name = client_info.get("proto")
        if proto_name and proto_name in self._protos:
            kwargs = await self._protos[proto_name].receive_msg(msg_data, client_info, websocket)
            if kwargs:
                await self._handle_message(**kwargs)
        else:
            logger.warning("No protocol handler found for proto: {}", proto_name)

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WebSocket."""
        if not self._running:
            logger.warning("Channel not running, cannot send message")
            return

        # Find the appropriate client connection based on chat_id
        target_ws = None
        for ws, client_info in self._clients.items():
            if client_info["chat_id"] == msg.chat_id or client_info["sender_id"] == msg.chat_id:
                target_ws = ws
                break

        if not target_ws:
            logger.warning("No connected client found for chat_id: {}", msg.chat_id)
            return

        if (
            msg.metadata.get("msg_type", "text") == "audio"
            and msg.metadata.get("encoder_type", "") == "opus"
        ):
            self._stop_audio = False
            frame_duration = msg.metadata.get("frame_duration", 60)
            await target_ws.send(
                json.dumps({"type": "tts", "state": "start", "session_id": msg.chat_id})
            )
            await target_ws.send(
                json.dumps(
                    {
                        "type": "tts",
                        "state": "sentence_start",
                        "session_id": msg.chat_id,
                        "text": msg.content,
                        "metadata": msg.metadata,
                    }
                )
            )
            for media_item in msg.media:
                if self._stop_audio:
                    break
                await target_ws.send(media_item)
                await asyncio.sleep(frame_duration / 1000.0)
            await target_ws.send(
                json.dumps({"type": "tts", "state": "sentence_end", "session_id": msg.chat_id})
            )
            await target_ws.send(
                json.dumps({"type": "tts", "state": "stop", "session_id": msg.chat_id})
            )
        else:
            try:
                # Convert media bytes to base64 for JSON serialization
                media_items = []
                if msg.media:
                    for media_item in msg.media:
                        if isinstance(media_item, bytes):
                            import base64

                            media_items.append(base64.b64encode(media_item).decode("utf-8"))
                        else:
                            media_items.append(media_item)
                message_data = {
                    "type": "message",
                    "chat_id": msg.chat_id,
                    "content": msg.content,
                    "media": media_items,
                    "metadata": msg.metadata,
                    "timestamp": asyncio.get_event_loop().time(),
                }
                # Send message to the specific client
                await target_ws.send(json.dumps(message_data, ensure_ascii=False))
            except Exception as e:
                logger.error("Error sending WebSocket message: {}", e)

    async def _get_client_info(self, websocket) -> dict | None:
        """
        Get client info by trying each protocol handler's accept method.

        Args:
            websocket: The WebSocket connection object.

        Returns:
            Client information dictionary if accepted by a proto, None otherwise.
            The returned dict includes 'proto' field indicating which proto accepted it.
        """
        if websocket not in self._clients:
            for name, proto in self._protos.items():
                client_info = await proto.accept(websocket)
                if client_info:
                    self._clients[websocket] = {**client_info, "proto": name}
                    logger.info(f"Bind {websocket.remote_address} -> {self._clients[websocket]}")
        assert websocket in self._clients, "WebSocket not found in clients"
        return self._clients[websocket]

    async def _heartbeat_loop(self, websocket) -> None:
        """Send periodic heartbeat messages to connected client."""
        while self._running and self._connected:
            try:
                heartbeat_msg = {"type": "heartbeat", "timestamp": asyncio.get_event_loop().time()}
                await websocket.send(json.dumps(heartbeat_msg, ensure_ascii=False))
                await asyncio.sleep(self.config.heartbeat_interval)
            except Exception as e:
                logger.warning("Server heartbeat failed: {}", e)
                break

    async def _send_heartbeat_response(self) -> None:
        """Send heartbeat response."""
        try:
            response = {
                "type": "heartbeat_response",
                "timestamp": asyncio.get_event_loop().time(),
            }
            await self._ws_client.send(json.dumps(response, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to send heartbeat response: {}", e)
