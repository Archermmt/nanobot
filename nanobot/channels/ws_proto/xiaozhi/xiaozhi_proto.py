"""XiaoZhi protocol handler for WebSocket communication with ESP32 devices."""

import asyncio
import json
import uuid
from enum import Enum
from typing import Any
from urllib.parse import parse_qs, urlparse

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.channels.ws_proto.base_proto import BaseProto
from nanobot.channels.ws_proto.xiaozhi.core.http_server import SimpleHttpServer
from nanobot.utils.text_utils import check_emoji, get_string_no_punctuation_or_emoji

from .core.schema import XiaoZhiProtoConfig


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


@BaseProto.register()
class XiaoZhiProto(BaseProto):
    """
    XiaoZhi protocol handler for WebSocket message processing.

    This protocol handles:
    - Device authentication via device-id, client-id, and authorization headers
    - Support for both header-based and URL parameter-based authentication
    - JSON message format for bidirectional communication
    - MCP (Model Context Protocol) support
    - TTS (Text-to-Speech) message handling
    """

    @classmethod
    def proto_name(cls) -> str:
        """Return the protocol name for registration."""
        return "xiaozhi"

    def __init__(self, config: XiaoZhiProtoConfig | dict, ws_config: Any, message_sender: Any):
        """
        Initialize the XiaoZhi protocol handler.

        Args:
            config: Protocol-specific configuration (dict or XiaoZhiProtoConfig).
            ws_config: WebSocket channel configuration (for host, port, etc.).
            message_sender: Callback function for sending messages.
        """
        if isinstance(config, dict):
            config = XiaoZhiProtoConfig.model_validate(config)
        super().__init__(config, ws_config, message_sender)
        self._features = {}
        self._session_id = str(uuid.uuid4())[:8]
        self._result_queue: asyncio.Queue = asyncio.Queue()
        self._ota_task: asyncio.Task | None = None
        self._stop_audio, self._interruptable = False, False

    async def connect(self, client_info: dict) -> None:
        """
        Connect the protocol handler and OTA server.

        This method is called when the WebSocket channel connects.
        Starts the OTA HTTP server for firmware updates.

        Args:
            client_info: Client connection information (sender_id, chat_id, etc.).
        """
        # Start OTA server
        ota_server = SimpleHttpServer(self.config, self.ws_config.host, self.ws_config.port)
        self._ota_task = asyncio.create_task(ota_server.start())
        logger.debug("XiaoZhi OTA server started")

    async def disconnect(self) -> None:
        """
        Disconnect the protocol handler and clean up resources.

        This method is called when the WebSocket channel disconnects.
        Cancels the OTA server task.
        """
        # Cancel OTA task
        if self._ota_task:
            self._ota_task.cancel()
            try:
                await self._ota_task
            except asyncio.CancelledError:
                pass
            self._ota_task = None
            logger.debug("XiaoZhi OTA server stopped")

    async def accept(self, websocket) -> dict | None:
        """
        Check if the current websocket can be accepted by this proto.

        The xiaozhi proto accepts connections from ESP32 devices and extracts
        client info from headers or URL parameters. Performs authentication if enabled.

        Args:
            websocket: The WebSocket connection object.

        Returns:
            A dictionary containing client information if accepted, None otherwise.
        """
        try:
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
                return None

            # Authenticate if enabled
            if self.config.auth_enabled:
                try:
                    await self._authenticate(device_id, client_id, authorization)
                except AuthenticationError as e:
                    logger.warning("Authentication failed for device {}: {}", device_id, str(e))
                    return None
            return {"sender_id": self._session_id, "chat_id": client_id or device_id}
        except Exception as e:
            logger.warning("Failed to accept xiaozhi connection: {}", e)
            return None

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
        allowed_devices = self.config.allowed_devices
        if allowed_devices and device_id in allowed_devices:
            logger.debug("Device {} in whitelist, skipping token validation", device_id)
            return

        # Validate token
        if not authorization:
            raise AuthenticationError("Missing authorization token")

        # Remove 'Bearer ' prefix if present
        token = authorization
        if token.startswith("Bearer "):
            token = token[7:]

        # Fallback to simple token validation
        if not token or token != self.config.auth_key:
            raise AuthenticationError("Invalid authorization token")

        logger.debug("Device {} authenticated successfully", device_id)

    async def receive_msg(self, msg_data: dict, client_info: dict, websocket) -> None:
        """
        Receive and process incoming message from WebSocket.

        Args:
            msg_data: Parsed message data dictionary.
            client_info: Client connection information (sender_id, chat_id, etc.).
            websocket: The WebSocket connection object.
        """
        msg_type = msg_data.get("type", TextMessageType.LISTEN.value)

        # Handle audio_clip message type
        if msg_type == "bytes":
            await self.message_sender(
                sender_id=client_info["sender_id"],
                chat_id=client_info["chat_id"],
                content=msg_data["data"],
                metadata={"msg_type": "audio_clip", "need_tts": True},
            )
            return

        # Handle hello message
        if msg_type == TextMessageType.HELLO.value:
            await self._handle_hello_message(msg_data, websocket)
            await self.message_sender(
                sender_id=client_info["sender_id"],
                chat_id=client_info["chat_id"],
                content="/update_features",
                metadata={"features": {"need_tts": True}},
            )
            return

        # Handle MCP message
        if msg_type == TextMessageType.MCP.value:
            await self._handle_mcp_message(msg_data, client_info, websocket)
            return

        if msg_type == TextMessageType.ABORT.value:
            self._stop_audio = True
            if self._interruptable:
                await self.message_sender(
                    sender_id=client_info["sender_id"],
                    chat_id=client_info["chat_id"],
                    content="/update_features",
                    metadata={"features": {"audio_playing": False}},
                )
            return

        # Handle unknown message types
        if msg_type != TextMessageType.LISTEN.value:
            logger.warning(f"Received unknown message({msg_type}): {msg_data}")
            return

        # Handle listen state messages
        if msg_data.get("state") == "start":
            await self.message_sender(
                sender_id=client_info["sender_id"],
                chat_id=client_info["chat_id"],
                content="/vad_reset",
                metadata={"msg_type": "audio_clip"},
            )
            return

        if msg_data.get("state") != "detect":
            logger.warning(f"Received unknown state type({msg_data.get('state')}): {msg_data}")
            return

        if "text" not in msg_data:
            logger.warning("No text in msg_data, nothing to response")
            return

        # Process chat message
        await self._process_chat_message(msg_data, client_info, websocket)

    async def _handle_hello_message(self, msg_data: dict, websocket: any):
        """Handle hello message."""
        response = {
            "session_id": self._session_id,
            "type": "hello",
            "version": 1,
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": 24000,
                "channels": 1,
                "frame_duration": 60,
            },
        }
        audio_params = msg_data.get("audio_params")
        if audio_params:
            response["audio_params"] = audio_params
        self._features = msg_data.get("features", {})
        if self._features.get("mcp"):
            asyncio.create_task(self._send_mcp_initialize_message(websocket))
        try:
            await websocket.send(json.dumps(response, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to send hello response: {}", e)

    async def _handle_mcp_message(self, msg_data: dict, client_info: dict, websocket: any) -> None:
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

        msg_id, result = int(payload.get("id", 0)), payload["result"]
        if msg_id == 1:  # mcpInitializeID
            logger.debug("Received MCP initialization response")
            server_info = result.get("serverInfo")
            if isinstance(server_info, dict):
                name = server_info.get("name")
                version = server_info.get("version")
                logger.debug(f"Client MCP server info: name={name}, version={version}")
            await asyncio.sleep(1)
            logger.debug("Initialization complete, start requesting MCP tool list")
            msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
            await self._send_mcp_message(msg, websocket)
            return

        if msg_id == 2:  # mcpToolsListID
            logger.debug("Received MCP tool list response")
            mcp_tools = []
            if isinstance(result, dict) and "tools" in result:
                tools_data = result["tools"]
                if not isinstance(tools_data, list):
                    logger.error("Tool list format error")
                    return
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
            await self.message_sender(
                sender_id=client_info["sender_id"],
                chat_id="xiaozhi",
                content="/register_extern_tools",
                metadata={
                    "type": "xiaozhi",
                    "kwargs": {
                        "websocket": websocket,
                        "timeout": 30,
                        "result_queue": self._result_queue,
                    },
                    "tools": mcp_tools,
                },
            )
            return

        # Handle tool call results (msg_id > 2)
        if msg_id > 2:
            await self._result_queue.put(
                {"chat_id": client_info["chat_id"], "tool_id": msg_id, "result": result}
            )
            return

    async def _send_mcp_initialize_message(self, websocket: any):
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
        await self._send_mcp_message(payload, websocket)

    async def _send_mcp_message(self, payload: dict, websocket: any):
        """Helper to send MCP messages, encapsulating common logic."""
        if not self._features.get("mcp"):
            logger.warning("Client does not support MCP, cannot send MCP message")
            return

        message = json.dumps({"type": "mcp", "payload": payload})
        try:
            await websocket.send(message)
            logger.debug(f"Successfully sent MCP message: {message}")
        except Exception as e:
            logger.error(f"Failed to send MCP message: {e}")

    async def _process_chat_message(self, msg_data, client_info, websocket: any) -> None:
        """Process chat message and prepare response."""
        content = msg_data["text"]
        stt_text = get_string_no_punctuation_or_emoji(content)
        await websocket.send(
            json.dumps({"type": "stt", "text": stt_text, "session_id": self._session_id})
        )
        await self.message_sender(
            sender_id=client_info["sender_id"],
            chat_id=client_info["chat_id"],
            content=content,
            metadata={"need_tts": True},
        )

    async def _send_tts_message(self, websocket: any, state, text=None):
        """Send TTS status message."""
        if text is None and state == "sentence_start":
            return
        message = {"type": "tts", "state": state, "session_id": self._session_id}
        if text is not None:
            message["text"] = check_emoji(text)
        await websocket.send(json.dumps(message))

    async def send_msg(self, msg: OutboundMessage, client_info: dict, websocket: Any) -> dict:
        """
        Send a message through WebSocket.

        Args:
            msg: Outbound message to send.
            client_info: Client connection information (sender_id, chat_id, etc.).
            websocket: The WebSocket connection object.

        Returns:
            info: A dictionary containing information about the sent message.
        """

        # filter messages
        msg_type = msg.metadata.get("msg_type", "audio")
        if msg.metadata.get("_cmd_ref", "") == "register_extern_tools":
            return {"success": True, "broadcast_msg": msg}
        if msg.metadata.get("_progress", False) or msg.metadata.get("_hide_message", False):
            return {"success": True, "broadcast_msg": msg}
        if msg.media and msg_type != "audio":
            return {"success": True, "broadcast_msg": msg}

        async def _sync_audio(audio_playing: bool):
            if self._interruptable:
                await self.message_sender(
                    sender_id=client_info["sender_id"],
                    chat_id=msg.chat_id,
                    content="/update_features",
                    metadata={"features": {"audio_playing": audio_playing}},
                )

        if msg.content == "/stop_audio":
            self._stop_audio = True
            await _sync_audio(False)
            return {"success": True}
        if msg_type == "audio":
            self._stop_audio = False
            await _sync_audio(True)
            frame_duration = msg.metadata.get("frame_duration", 60)
            await self._send_tts_message(websocket, "start")
            await self._send_tts_message(websocket, "sentence_start", msg.content)
            for media in msg.media:
                if self._stop_audio:
                    break
                await websocket.send(media)
                await asyncio.sleep(frame_duration / 1000.0)
            await self._send_tts_message(websocket, "sentence_end")
            await self._send_tts_message(websocket, "stop")
            await _sync_audio(False)
        else:
            await websocket.send(
                json.dumps({"type": "stt", "text": msg.content, "session_id": self._session_id})
            )
        msg.media = []
        msg.metadata.update({"msg_type": "text"})
        return {"success": True, "broadcast_msg": msg}
