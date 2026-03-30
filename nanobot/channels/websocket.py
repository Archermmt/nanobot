"""WebSocket channel implementation for generic WebSocket communication."""

import asyncio
import json
from collections import OrderedDict
from pathlib import Path

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
    server_url: str = "ws://localhost:8765"  # WebSocket server URL
    auth_token: str = ""  # Authentication token for WebSocket connection
    allow_from: list[str] = Field(default_factory=list)  # Allowed sender identifiers
    reconnect_interval: int = 5  # Reconnection interval in seconds
    heartbeat_interval: int = 30  # Heartbeat interval in seconds
    as_server: bool = True  # If True, act as WebSocket server; if False, connect as client
    frame_duration: int = 60  # Frame duration in milliseconds
    cache_media: bool = False  # If True, save media files locally


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
        self._ws = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        # self._loop: asyncio.AbstractEventLoop | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._connected = False
        self._mcp_result_queue: asyncio.Queue = asyncio.Queue()  # Queue for MCP results

    async def start(self) -> None:
        """Start the WebSocket channel with reconnection logic."""
        self._running = True
        # self._loop = asyncio.get_running_loop()

        if self.config.as_server:
            # Act as WebSocket server
            logger.info("Starting WebSocket server on {}", self.config.server_url)
            await self._start_server()
        else:
            # Act as WebSocket client (connect to external server)
            logger.info("Starting WebSocket client connecting to {}", self.config.server_url)
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

        # Close WebSocket connection/server
        if self._ws:
            try:
                if self.config.as_server and hasattr(self._ws, "close"):
                    # Server mode - close server
                    await self._ws.close()
                elif hasattr(self._ws, "close"):
                    # Client mode - close connection
                    await self._ws.close()
            except Exception as e:
                logger.warning("Error closing WebSocket: {}", e)
            self._ws = None
            self._connected = False

        logger.info("WebSocket channel stopped")

    async def _start_server(self) -> None:
        """Start WebSocket server to accept client connections."""
        # Parse server URL to get host and port
        from urllib.parse import urlparse

        import websockets

        parsed = urlparse(self.config.server_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8765

        logger.info("Starting WebSocket server on {}:{}", host, port)

        async def handler(websocket, *args):
            """Handle individual WebSocket connections."""
            logger.info("New WebSocket client connected from {}", websocket.remote_address)
            self._ws = websocket
            self._connected = True

            try:
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

                # Start heartbeat for this connection
                if self.config.heartbeat_interval > 0:
                    self._heartbeat_task = asyncio.create_task(
                        self._server_heartbeat_loop(websocket)
                    )

                # Process messages from this client
                await self._handle_client_messages(websocket)

            except websockets.exceptions.ConnectionClosed:
                logger.info("WebSocket client disconnected")
            except Exception as e:
                logger.error("Error handling WebSocket client: {}", e)
            finally:
                self._connected = False
                self._ws = None
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                    self._heartbeat_task = None

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

    async def _handle_client_messages(self, websocket) -> None:
        """Handle incoming messages from connected clients."""
        async for message in websocket:
            if not self._running:
                break

            try:
                if isinstance(message, str):
                    msg_data = json.loads(message)
                elif isinstance(message, bytes):
                    msg_data = {"type": "audio_clip", "bytes": message}
                else:
                    return
                await self._process_incoming_message(msg_data)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON message received: {}", e)
            except Exception as e:
                logger.error("Error processing message: {}", e)

    async def _server_heartbeat_loop(self, websocket) -> None:
        """Send periodic heartbeat messages to connected client."""
        while self._running and self._connected:
            try:
                heartbeat_msg = {
                    "type": "heartbeat",
                    "timestamp": asyncio.get_event_loop().time(),
                }
                await websocket.send(json.dumps(heartbeat_msg, ensure_ascii=False))
                await asyncio.sleep(self.config.heartbeat_interval)
            except Exception as e:
                logger.warning("Server heartbeat failed: {}", e)
                break

    async def _connect_with_retry(self) -> None:
        """Connect to WebSocket server with retry logic."""
        while self._running and not self._connected:
            try:
                import websockets

                logger.info("Connecting to WebSocket server at {}", self.config.server_url)

                self._ws = await websockets.connect(self.config.server_url)
                self._connected = True

                # Send authentication if token provided
                if self.config.auth_token:
                    auth_msg = {"type": "auth", "token": self.config.auth_token}
                    await self._ws.send(json.dumps(auth_msg, ensure_ascii=False))
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
            async for message in self._ws:
                if not self._running:
                    break

                try:
                    # Parse message
                    msg_data = json.loads(message)
                    await self._process_incoming_message(msg_data)
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

    async def _process_incoming_message(self, msg_data: dict) -> None:
        """Process an incoming message from WebSocket."""
        msg_type = msg_data.get("type", "message")
        # Extract message fields
        message_id = msg_data.get("message_id") or str(hash(str(msg_data)))
        sender_id = msg_data.get("sender_id", "unknown")
        chat_id = msg_data.get("chat_id", "default")
        content = msg_data.get("content", "")
        media = msg_data.get("media", [])
        metadata = msg_data.get("metadata", {})

        if msg_type == "audio_clip":
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=msg_data["bytes"],
                metadata={"msg_type": "audio_clip"},
            )
            return
        if content == "/register_extern_tools":
            mcp_tools, tools_data = [], metadata["tools"]
            logger.info(f"Number of tools supported by client device: {len(tools_data)}")
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
                new_tool = {
                    "name": name,
                    "description": description,
                    "inputSchema": input_schema,
                }
                mcp_tools.append(new_tool)
                logger.debug(f"Client tool #{i + 1}: {name}")
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content="/register_extern_tools",
                metadata={
                    "type": "websocket",
                    "kwargs": {
                        "websocket": self._ws,
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
        # Deduplication check
        if message_id in self._processed_message_ids:
            return
        self._processed_message_ids[message_id] = None

        # Trim cache
        while len(self._processed_message_ids) > 1000:
            self._processed_message_ids.popitem(last=False)

        # Skip empty messages (unless it's a media message)
        if not content and not media and not metadata:
            return

        media_dir = Path.home() / ".nanobot" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        if not content and meta_type == "audio":
            # Save media if cache_media is enabled
            if self.config.cache_media and media:
                for media_item in media:
                    media_data, filename = media_item["data"], media_item.get("file_name", "")
                    if isinstance(media_data, str) and media_data.startswith("data:"):
                        try:
                            file_path, filename = save_media(
                                media_data, filename, target_type="audio/wav"
                            )
                            logger.info("Saved audio file to: {}", file_path)
                        except Exception as e:
                            logger.error("Failed to save audio media: {}", e)
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

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        while self._running and self._connected:
            try:
                heartbeat_msg = {
                    "type": "heartbeat",
                    "timestamp": asyncio.get_event_loop().time(),
                }
                await self._ws.send(json.dumps(heartbeat_msg, ensure_ascii=False))
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
            await self._ws.send(json.dumps(response, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to send heartbeat response: {}", e)

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WebSocket."""
        if not self._connected or not self._ws:
            logger.warning("WebSocket not connected, cannot send message")
            return

        if (
            msg.metadata.get("msg_type", "text") == "audio"
            and msg.metadata.get("encoder_type", "") == "opus"
        ):
            # Send opus back for testing
            await self._ws.send(
                json.dumps({"type": "tts", "state": "start", "session_id": msg.chat_id})
            )
            await self._ws.send(
                json.dumps(
                    {
                        "type": "tts",
                        "state": "sentence_start",
                        "session_id": msg.chat_id,
                        "text": msg.content,
                    }
                )
            )
            for media in msg.media:
                await self._ws.send(media)
            await self._ws.send(
                json.dumps({"type": "tts", "state": "sentence_end", "session_id": msg.chat_id})
            )
            play_time = len(msg.media) * self.config.frame_duration / 1000.0
            logger.debug(f"Sending audio message as opus frames, wait {play_time} s")
            await asyncio.sleep(play_time)
            await self._ws.send(
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
                    "message_id": f"msg_{hash(msg.content)}",
                    "sender_id": "bot",
                    "chat_id": msg.chat_id,
                    "content": msg.content,
                    "media": media_items,
                    "metadata": msg.metadata,
                    "timestamp": asyncio.get_event_loop().time(),
                }
                # Send message ( works for both client and server mode)
                await self._ws.send(json.dumps(message_data, ensure_ascii=False))
            except Exception as e:
                logger.error("Error sending WebSocket message: {}", e)
