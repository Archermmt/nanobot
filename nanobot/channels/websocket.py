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
from nanobot.utils.media import save_media


class WebSocketConfig(Base):
    """Generic WebSocket channel configuration."""

    enabled: bool = False
    host: str = "localhost"  # WebSocket server host
    port: int = 8765  # WebSocket server port
    auth_token: str = ""  # Authentication token for WebSocket connection
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
        self._server = None
        self._clients: dict[any, dict] = {}  # Track multiple client connections
        self._heartbeat_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._mcp_result_queue: asyncio.Queue = asyncio.Queue()  # Queue for MCP results
        self._connected = False
        self._stop_audio = False
        self._protos: dict[str, Any] = self._init_protos()

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
            # Act as WebSocket server
            logger.info("Starting WebSocket server on {}:{}", self.config.host, self.config.port)
            await self._start_server()
        else:
            # Act as WebSocket client (connect to external server)
            server_url = f"ws://{self.config.host}:{self.config.port}"
            logger.info("Starting WebSocket client connecting to {}", server_url)
            await self._connect_with_retry()

            # Keep running until stopped
            while self._running:
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the WebSocket channel."""
        self._running = False

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
                logger.warning("Error closing client connection: {}", e)

        self._clients.clear()

        # Close WebSocket connection/server
        if self._server:
            try:
                if self.config.as_server and hasattr(self._server, "close"):
                    # Server mode - close server
                    await self._server.close()
                elif hasattr(self._server, "close"):
                    # Client mode - close connection
                    await self._server.close()
            except Exception as e:
                logger.warning("Error closing WebSocket: {}", e)
            self._server = None
            self._connected = False

        logger.info("WebSocket channel stopped")

    def _get_websocket_for_chat(self, chat_id: str):
        """
        Get the WebSocket connection for a specific chat_id.

        Args:
            chat_id: The chat identifier to find the connection for.

        Returns:
            WebSocket connection if found, None otherwise.
        """
        for ws, client_info in self._clients.items():
            if client_info.get("chat_id") == chat_id or client_info.get("sender_id") == chat_id:
                return ws
        return None

    async def _start_server(self) -> None:
        """Start WebSocket server to accept client connections."""
        import websockets

        host = self.config.host
        port = self.config.port

        logger.info("Starting WebSocket server on {}:{}", host, port)

        async def handler(websocket, *args):
            """Handle individual WebSocket connections."""
            logger.info("New WebSocket client connected from {}", websocket.remote_address)

            try:
                """
                for name, proto in self._protos.items():
                    client_info = proto.accept(websocket)
                    if client_info:
                        print("should use the proto " + str(proto))
                        self._clients[websocket] = client_info
                        logger.info(f"Client accepted by {name} : {client_info}")
                assert websocket in self._clients, "Can not find accept proto for client " + str(
                    websocket
                )
                """

                headers = dict(websocket.request.headers)
                print("[TMINFO] headers " + str(headers), flush=True)

                # Extract sender_id and chat_id from URL query parameters
                client_sender_id = "web_user"
                client_chat_id = "default"

                try:
                    # Get query parameters from the request path
                    request_path = websocket.request.path
                    if "?" in request_path:
                        query_string = request_path.split("?", 1)[1]
                        from urllib.parse import parse_qs

                        query_params = parse_qs(query_string)

                        # Extract sender_id and chat_id from query params
                        if "sender_id" in query_params:
                            client_sender_id = query_params["sender_id"][0]
                        if "chat_id" in query_params:
                            client_chat_id = query_params["chat_id"][0]
                        print(
                            "[TMINFO] Extracted from URL - sender_id: {}, chat_id: {}".format(
                                client_sender_id, client_chat_id
                            ),
                            flush=True,
                        )

                        logger.info(
                            "Extracted from URL - sender_id: {}, chat_id: {}",
                            client_sender_id,
                            client_chat_id,
                        )
                except Exception as e:
                    logger.warning("Failed to extract query parameters: {}", e)

                # Handle authentication if token is required
                if self.config.auth_token:
                    try:
                        auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        auth_data = json.loads(auth_msg)
                        if (
                            auth_data.get("type") == "auth"
                            and auth_data.get("token") == self.config.auth_token
                        ):
                            logger.debug("Client authenticated successfully")
                            # Extract sender_id and chat_id from auth message if provided,
                            # otherwise use values from URL query parameters
                            client_sender_id = auth_data.get("sender_id", client_sender_id)
                            client_chat_id = auth_data.get("chat_id", client_chat_id)
                        else:
                            logger.warning("Authentication failed")
                            await websocket.close(4001, "Authentication required")
                            return
                    except asyncio.TimeoutError:
                        logger.warning("Authentication timeout")
                        await websocket.close(4001, "Authentication timeout")
                        return
                    except json.JSONDecodeError:
                        logger.warning("Invalid authentication message")
                        await websocket.close(4001, "Invalid authentication")
                        return

                # Register client
                client_info = {
                    "sender_id": client_sender_id,
                    "chat_id": client_chat_id,
                    "authenticated": True,
                }
                self._clients[websocket] = client_info
                logger.info(
                    "Client registered: sender_id={}, chat_id={}",
                    client_sender_id,
                    client_chat_id,
                )

                # Start heartbeat for this connection
                if self.config.heartbeat_interval > 0:
                    self._heartbeat_task = asyncio.create_task(
                        self._server_heartbeat_loop(websocket)
                    )

                # Process messages from this client
                await self._handle_client_messages(websocket, client_info)

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
            # Set max_size to 20MB to support large file uploads
            async with websockets.serve(handler, host, port, max_size=20 * 1024 * 1024):
                logger.info("WebSocket server started and listening")
                # Keep server running
                while self._running:
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error("WebSocket server error: {}", e)
            raise

    async def _handle_client_messages(self, websocket, client_info: dict) -> None:
        """Handle incoming messages from connected clients."""
        async for message in websocket:
            if not self._running:
                break
            try:
                await self._process_incoming_message(message, client_info)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON message received: {}", e)
            except Exception as e:
                logger.error("Error processing message: {}", e)

    async def _process_incoming_message(self, message: str | bytes, client_info: dict) -> None:
        """Process an incoming message from WebSocket."""

        msg_data = None
        try:
            if isinstance(message, str):
                msg_data = json.loads(message)
            elif isinstance(message, bytes):
                msg_data = {"type": "bytes", "data": message}
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON message received: {}", e)
        except Exception as e:
            logger.error("Error processing message: {}", e)
        if not msg_data:
            return

        msg_type = msg_data.get("type", "message")
        sender_id = msg_data.get("sender_id", client_info["sender_id"])
        chat_id = msg_data.get("chat_id", client_info["chat_id"])
        content = msg_data.get("content", "")
        media = msg_data.get("media", [])
        metadata = msg_data.get("metadata", {})

        if msg_type == "bytes":
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=msg_data["data"],
                metadata={"msg_type": "audio_clip"},
            )
            return
        if content == "/stop_audio":
            self._stop_audio = True
            return
        if content == "/register_extern_tools":
            mcp_tools, tools_data = [], metadata["tools"]
            for i, tool in enumerate(tools_data):
                if not isinstance(tool, dict):
                    continue
                name = tool.get("name", "")
                description = tool.get("description", "")
                input_schema = {"type": "object", "properties": {}, "required": []}
                if "inputSchema" in tool and isinstance(tool["inputSchema"], dict):
                    schema = tool["inputSchema"]
                    input_schema["type"] = schema.get("type", "object")
                    input_schema["properties"] = schema.get("properties", {})
                    input_schema["required"] = [
                        s for s in schema.get("required", []) if isinstance(s, str)
                    ]
                new_tool = {"name": name, "description": description, "inputSchema": input_schema}
                mcp_tools.append(new_tool)
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content="/register_extern_tools",
                metadata={
                    "type": "websocket",
                    "kwargs": {
                        "websocket": self._server,
                        "timeout": 30,
                        "result_queue": self._mcp_result_queue,
                    },
                    "tools": mcp_tools,
                },
            )
            return
        if msg_type == "heartbeat":
            # Respond to heartbeat
            await self._send_heartbeat_response()
            return
        if msg_type == "tool_call":
            # Put result into queue for tool to fetch
            try:
                tool_name = msg_data.get("name") or metadata.get("tool_name")
                await self._mcp_result_queue.put(
                    {"msg_id": tool_name, "result": msg_data.get("result", {})}
                )
                logger.debug(f"Put tool call result into queue, tool_name={tool_name}")
            except Exception as e:
                logger.error(f"Failed to put tool call result into queue: {e}")
        if msg_type != "message":
            # Ignore unknown message types
            return

        meta_type = metadata.get("msg_type", "text")
        # Skip empty messages (unless it's a media message)
        if not content and not media and not metadata:
            return

        if not content and meta_type == "audio":
            # Handle the message
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                media=media,
                metadata=metadata,
            )
            return

        # Handle base64-encoded media (images, audio, files)
        # Convert base64 data to temporary files
        content_parts = []
        media_paths = []
        if content:
            content_parts.append(content)
        elif media:
            content_parts.append("Just save the following files, do nothing else: ")
        if media:
            for media_item in media:
                media_data, filename = media_item["data"], media_item.get("file_name", "")
                # Check if media is base64 data (data URL format: data:<mime>;base64,<data>)
                if isinstance(media_data, str) and media_data.startswith("data:"):
                    try:
                        file_path, filename = save_media(media_data, filename)
                        media_paths.append(str(file_path))
                        content_parts.append(f"{filename}({meta_type}) saved to {file_path}")
                    except Exception as e:
                        logger.error("Failed to process base64 media: {}", e)
                else:
                    # Already a file path
                    media_paths.append(media_item)

        content = "\n".join(content_parts) if content_parts else ""
        # Forward to message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            media=media_paths,
            metadata=metadata,
        )

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

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        while self._running and self._connected:
            try:
                heartbeat_msg = {
                    "type": "heartbeat",
                    "timestamp": asyncio.get_event_loop().time(),
                }
                await self._server.send(json.dumps(heartbeat_msg, ensure_ascii=False))
                await asyncio.sleep(self.config.heartbeat_interval)
            except Exception as e:
                logger.warning("Heartbeat failed: {}", e)
                break

    async def _send_heartbeat_response(self) -> None:
        """Send heartbeat response."""
        try:
            response = {
                "type": "heartbeat_response",
                "timestamp": asyncio.get_event_loop().time(),
            }
            await self._server.send(json.dumps(response, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to send heartbeat response: {}", e)

    async def _server_heartbeat_loop(self, websocket) -> None:
        """Send periodic heartbeat messages to connected client."""
        while self._running and self._connected:
            try:
                heartbeat_msg = {"type": "heartbeat", "timestamp": asyncio.get_event_loop().time()}
                await websocket.send(json.dumps(heartbeat_msg, ensure_ascii=False))
                await asyncio.sleep(self.config.heartbeat_interval)
            except Exception as e:
                logger.warning("Server heartbeat failed: {}", e)
                break

    async def _connect_with_retry(self) -> None:
        """Connect to WebSocket server with retry logic."""
        import websockets

        server_url = f"ws://{self.config.host}:{self.config.port}"
        while self._running and not self._connected:
            try:
                logger.info("Connecting to WebSocket server at {}", server_url)

                self._server = await websockets.connect(server_url)
                self._connected = True

                # Send authentication if token provided
                if self.config.auth_token:
                    auth_msg = {"type": "auth", "token": self.config.auth_token}
                    await self._server.send(json.dumps(auth_msg, ensure_ascii=False))
                    logger.debug("Sent authentication token")

                logger.info("Connected to WebSocket server")

                # Start heartbeat
                if self.config.heartbeat_interval > 0:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Start message receiving
                await self._receive_messages()

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

    async def _receive_messages(self) -> None:
        """Receive and process incoming messages."""
        try:
            async for message in self._server:
                if not self._running:
                    break

                try:
                    # Parse message
                    await self._process_incoming_message(message)
                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON message received: {}", e)
                except Exception as e:
                    logger.error("Error processing message: {}", e)

        except Exception as e:
            logger.warning("WebSocket connection lost: {}", e)
            self._connected = False
            if self._running:
                # Schedule reconnection
                self._reconnect_task = asyncio.create_task(self._connect_with_retry())
