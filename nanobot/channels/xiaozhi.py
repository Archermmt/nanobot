"""XiaoZhi channel implementation for WebSocket communication with ESP32 devices."""

import asyncio
import json
import uuid
from collections import OrderedDict
from enum import Enum
from urllib.parse import parse_qs, urlparse

import websockets
from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.channels.xiaozhi_server.core.http_server import SimpleHttpServer
from nanobot.config.schema import XiaoZhiConfig
from nanobot.utils.text_utils import check_emoji, get_string_no_punctuation_or_emoji


class TextMessageType(Enum):
    """Message type enumeration."""

    HELLO = "hello"
    ABORT = "abort"
    LISTEN = "listen"
    IOT = "iot"
    MCP = "mcp"
    SERVER = "server"
    PING = "ping"


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

    def __init__(self, config: XiaoZhiConfig, bus: MessageBus):
        """
        Initialize the XiaoZhi channel.

        Args:
            config: Channel configuration with server settings.
            bus: The message bus for communication.
        """
        super().__init__(config, bus)
        self.config: XiaoZhiConfig = config
        self._ws = None
        self._connected_clients: dict[any, dict] = {}
        self._auth_enabled = False
        self._allowed_devices: set = set()
        self._auth_key = ""
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self.config_lock = asyncio.Lock()
        self.session_id = str(uuid.uuid4())[:8]
        self.features = {}
        self._mcp_result_queue: asyncio.Queue = asyncio.Queue()  # Queue for MCP results

    async def start(self) -> None:
        """Start the WebSocket server and begin listening for connections."""
        self._running = True

        # Start ota_server
        ota_server = SimpleHttpServer(self.config)
        self.ota_task = asyncio.create_task(ota_server.start())

        # Get server configuration
        host = self.config.host
        port = self.config.port
        self._allowed_devices = self.config.allowed_devices
        self._auth_enabled = self.config.auth_enabled
        self._auth_key = self.config.auth_key

        logger.info(
            "Starting XiaoZhi WebSocket server on {}:{} (auth: {})",
            host,
            port,
            "enabled" if self._auth_enabled else "disabled",
        )

        # Start WebSocket server
        try:
            async with websockets.serve(
                self._handle_connection,
                host,
                port,
                max_size=20 * 1024 * 1024,
                process_request=self._http_response,
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
        # Close WebSocket connection/server
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning("Error closing WebSocket: {}", e)
            self._ws = None

        if self.ota_task:
            self.ota_task.cancel()

        logger.info("XiaoZhi WebSocket server stopped")

    async def _handle_connection(self, websocket: any) -> None:
        """
        Handle a new WebSocket connection.

        Args:
            websocket: The WebSocket connection object.
        """

        self._ws = websocket

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
                logger.warning("Authentication failed for device {}: {}", device_id, str(e))
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
                await websocket.close()
            except Exception as close_error:
                logger.warning("Error closing connection: {}", close_error)

    async def _http_response(self, websocket, request_headers):
        # Check if it's a WebSocket upgrade request
        if request_headers.headers.get("connection", "").lower() == "upgrade":
            # If it's a WebSocket request, return None to allow handshake to continue
            return None
        else:
            # If it's a regular HTTP request, return "server is running"
            return websocket.respond(200, "Server is running\n")

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
        # Check if auth is enabled
        if not self._auth_enabled:
            return

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

        # Verify token using AuthManager
        if self._auth:
            auth_success = self._auth.verify_token(
                token, client_id=client_id or device_id, username=device_id
            )
            if not auth_success:
                raise AuthenticationError("Invalid or expired token")
        else:
            # Fallback to simple token validation if AuthManager not available
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
                if isinstance(message, str):
                    msg_data = json.loads(message)
                elif isinstance(message, bytes):
                    msg_data = {"type": "audio_clip", "bytes": message}
                else:
                    return
                # Parse message
                await self._process_incoming_message(msg_data, client_info)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON message from {}: {}", client_info["device_id"], e)
                await websocket.send(
                    json.dumps({"type": "error", "content": "Invalid JSON format"})
                )
            except Exception as e:
                logger.error("Error processing message from {}: {}", client_info["device_id"], e)

    async def _process_incoming_message(self, msg_data: dict, client_info: dict) -> None:
        """Process an incoming message from WebSocket."""

        msg_type = msg_data.get("type", TextMessageType.LISTEN)
        # Handle msg_type handler
        if msg_type == "audio_clip":
            await self._handle_message(
                sender_id=self.session_id,
                chat_id=client_info["client_id"],
                content=msg_data["bytes"],
                metadata={"msg_type": "audio_clip", "need_tts": True},
            )
            return
        if msg_type == TextMessageType.HELLO.value:
            await self._handle_hello_message(msg_data)
            return
        if msg_type == TextMessageType.MCP.value:
            await self._handle_mcp_message(msg_data, client_info)
            return
        if msg_type != TextMessageType.LISTEN.value:
            logger.warning("Received unknown message type: {}", msg_type)
            return

        if msg_data["state"] != "detect":
            logger.warning("Received unknown state type: {}", msg_data["state"])
            return

        if "text" not in msg_data:
            logger.warning("No text in msg_data, nothing to response")
            return

        await self._start_to_chat(msg_data, client_info)
        return

    async def _handle_hello_message(self, msg_data: dict):
        """Handle hello message."""

        response = {
            "session_id": self.session_id,
            "type": "hello",
            "version": 1,
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": 24000,
                "channels": 1,
                "frame_duration": self.config.frame_duration,
            },
        }
        audio_params = msg_data.get("audio_params")
        if audio_params:
            response["audio_params"] = audio_params
        self.features = msg_data.get("features", {})
        if self.features.get("mcp"):
            asyncio.create_task(self._send_mcp_initialize_message())
        try:
            await self._ws.send(json.dumps(response, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to send hello response: {}", e)

    async def _handle_mcp_message(self, msg_data: dict, client_info: dict):
        """Handle MCP message."""

        # Handle result
        payload = msg_data["payload"]
        if "error" in payload:
            error_data = payload["error"]
            error_msg = error_data.get("message", "Unknown error")
            logger.error(f"Received MCP error response: {error_msg}")
            return

        if "result" not in payload:
            return

        result = payload["result"]
        msg_id = int(payload.get("id", 0))
        if msg_id == 1:  # mcpInitializeID
            logger.debug("Received MCP initialization response")
            server_info = result.get("serverInfo")
            if isinstance(server_info, dict):
                name = server_info.get("name")
                version = server_info.get("version")
                logger.debug(f"Client MCP server info: name={name}, version={version}")
            await asyncio.sleep(1)
            logger.debug("Initialization complete, start requesting MCP tool list")
            await self._send_mcp_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            return

        if msg_id == 2:  # mcpToolsListID
            logger.debug("Received MCP tool list response")
            mcp_tools = []
            if isinstance(result, dict) and "tools" in result:
                tools_data = result["tools"]
                if not isinstance(tools_data, list):
                    logger.error("Tool list format error")
                    return
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
                        "tool_id": i + 3,
                    }
                    mcp_tools.append(new_tool)
                    logger.debug(f"Client tool #{i + 1}: {name}")
            await self._handle_message(
                sender_id=self.session_id,
                chat_id=msg_data.get("chat_id", client_info["client_id"]),
                content="/register_extern_tools",
                metadata={
                    "type": "xiaozhi",
                    "kwargs": {
                        "websocket": self._ws,
                        "timeout": 30,
                        "result_queue": self._mcp_result_queue,
                    },
                    "tools": mcp_tools,
                },
            )
            return

        # Handle tool call results (msg_id > 2)
        if msg_id > 2:
            logger.debug(f"Received MCP tool call result, msg_id={msg_id}")
            # Put result into queue for tool to fetch
            try:
                await self._mcp_result_queue.put({"msg_id": msg_id, "result": result})
                logger.debug(f"Put tool call result into queue, msg_id={msg_id}")
            except Exception as e:
                logger.error(f"Failed to put tool call result into queue: {e}")

    async def _send_mcp_initialize_message(self):
        """Send MCP initialization message."""

        payload = {
            "jsonrpc": "2.0",
            "id": 1,  # mcpInitializeID
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": {
                    "name": "XiaozhiClient",
                    "version": "1.0.0",
                },
            },
        }
        await self._send_mcp_message(payload)

    async def _send_mcp_message(self, payload: dict):
        """Helper to send MCP messages, encapsulating common logic."""
        if not self.features.get("mcp"):
            logger.warning("Client does not support MCP, cannot send MCP message")
            return

        message = json.dumps({"type": "mcp", "payload": payload})
        try:
            await self._ws.send(message)
            logger.debug(f"Successfully sent MCP message: {message}")
        except Exception as e:
            logger.error(f"Failed to send MCP message: {e}")

    async def _start_to_chat(self, msg_data, client_info):
        content = msg_data["text"]
        stt_text = get_string_no_punctuation_or_emoji(content)
        await self._ws.send(
            json.dumps({"type": "stt", "text": stt_text, "session_id": self.session_id})
        )
        await self._handle_message(
            sender_id=self.session_id,
            chat_id=msg_data.get("chat_id", client_info["client_id"]),
            content=content,
            metadata={"need_tts": True},
        )

    async def _send_tts_message(self, state, text=None, websocket=None):
        """Send TTS status message."""
        if text is None and state == "sentence_start":
            return
        message = {"type": "tts", "state": state, "session_id": self.session_id}
        if text is not None:
            message["text"] = check_emoji(text)
        # Send message to client
        websocket = websocket or self._ws
        await websocket.send(json.dumps(message))

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message through the WebSocket channel.

        Args:
            msg: The outbound message to send.
        """
        if not self._running:
            logger.warning("Channel not running, cannot send message")
            return

        # Ignore some cases
        if msg.metadata.get("_task_ref", "") == "register_extern_tools":
            return
        if msg.metadata.get("_progress", False) or msg.metadata.get("_hide_message", False):
            return

        # Find the appropriate client connection
        target_ws = None
        for ws, client_info in self._connected_clients.items():
            if client_info["client_id"] == msg.chat_id or client_info["device_id"] == msg.chat_id:
                target_ws = ws
                break

        if not target_ws:
            logger.warning("No connected client found for chat_id: {}", msg.chat_id)
            return

        msg_type = msg.metadata.get("type", "audio")
        if msg_type == "audio":
            await self._send_tts_message("start", websocket=target_ws)
            await self._send_tts_message("sentence_start", msg.content, websocket=target_ws)
            for media in msg.media:
                await target_ws.send(media)
            play_time = len(msg.media) * self.config.frame_duration / 1000.0
            await asyncio.sleep(play_time)
            await self._send_tts_message("stop", websocket=target_ws)
        else:
            target_ws.send(
                json.dumps({"type": "stt", "text": msg.content, "session_id": self.session_id})
            )
