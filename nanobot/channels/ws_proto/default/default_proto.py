"""Default protocol handler for generic WebSocket communication."""

import asyncio
import base64
import json
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.channels.ws_proto.base_proto import BaseProto
from nanobot.config.schema import Base
from nanobot.utils.media import save_media


class DefaultProtoConfig(Base):
    """Default protocol handler configuration."""

    enabled: bool = True  # Whether this protocol is enabled
    auth_token: str = ""  # Authentication token for WebSocket connection
    accept_senders: list[str] = ["web_user"]  # List of accepted sender IDs


class DefaultProto(BaseProto):
    """
    Default protocol handler for WebSocket message processing.

    This protocol handles:
    - Incoming message parsing and routing
    - Outgoing message formatting and sending
    - Media file handling (images, audio, files)
    - Tool call result management
    """

    def __init__(self, config: DefaultProtoConfig | dict, ws_config: Any):
        """
        Initialize the default protocol handler.

        Args:
            config: Protocol-specific configuration (dict or DefaultProtoConfig).
            ws_config: WebSocket channel configuration (for host, port, etc.).
        """
        # Convert dict to config object if needed
        if isinstance(config, dict):
            config = DefaultProtoConfig.model_validate(config)
        super().__init__(config=config, ws_config=ws_config)
        self._mcp_result_queue: asyncio.Queue = asyncio.Queue()
        self._stop_audio = False

    async def accept(self, websocket) -> dict | None:
        """
        Check if the current websocket can be accepted by this proto.

        The default proto accepts all connections and extracts client info from
        URL query parameters or uses default values. If auth_token is configured,
        it will perform authentication.

        Args:
            websocket: The WebSocket connection object.

        Returns:
            A dictionary containing client information if accepted, None otherwise.
        """

        from urllib.parse import parse_qs

        try:
            # Extract sender_id and chat_id from URL query parameters
            sender_id, chat_id = None, None
            # Get query parameters from the request path
            request_path = websocket.request.path
            if "?" in request_path:
                query_params = parse_qs(request_path.split("?", 1)[1])
                # Extract sender_id and chat_id from query params
                if "sender_id" in query_params:
                    sender_id = query_params["sender_id"][0]
                if "chat_id" in query_params:
                    chat_id = query_params["chat_id"][0]

            # Check if sender_id is in the list of accepted senders
            if sender_id not in self.config.accept_senders:
                logger.warning(f"Sender {sender_id} not accepted from {websocket.remote_address}")
                return None

            # Handle authentication if token is configured
            if self.config.auth_token:
                try:
                    auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    auth_data = json.loads(auth_msg)
                    if (
                        auth_data.get("type") == "auth"
                        and auth_data.get("token") == self.config.auth_token
                    ):
                        logger.debug("Client authenticated successfully")
                        sender_id = auth_data.get("sender_id", sender_id)
                        chat_id = auth_data.get("chat_id", chat_id)
                    else:
                        logger.warning("Authentication failed")
                        return None
                except asyncio.TimeoutError:
                    logger.warning("Authentication timeout")
                    return None
                except json.JSONDecodeError:
                    logger.warning("Invalid authentication message")
                    return None

            return {"sender_id": sender_id, "chat_id": chat_id}
        except Exception as e:
            logger.warning("Failed to extract client info from websocket: {}", e)
            return None

    async def receive_msg(self, msg_data: dict, client_info: dict) -> None:
        """
        Receive and process incoming message from WebSocket.

        Args:
            msg_data: Parsed message data dictionary.
            client_info: Client connection information (sender_id, chat_id, etc.).
        """
        msg_type = msg_data.get("type", "message")
        sender_id = msg_data.get("sender_id", client_info.get("sender_id", "default_user"))
        chat_id = msg_data.get("chat_id", client_info.get("chat_id", "default"))
        content = msg_data.get("content", "")
        media = msg_data.get("media", [])
        metadata = msg_data.get("metadata", {})

        # Handle binary/audio clip messages
        if msg_type == "bytes":
            await self.channel_ref._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=msg_data["data"],
                metadata={"msg_type": "audio_clip"},
            )
            return

        # Handle stop audio command
        if content == "/stop_audio":
            self._stop_audio = True
            return

        # Handle external tool registration
        if content == "/register_extern_tools":
            await self._handle_register_extern_tools(sender_id, chat_id, metadata)
            return

        # Handle tool call results
        if msg_type == "tool_call":
            await self._handle_tool_call_result(msg_data, metadata)
            return

        # Ignore non-message types
        if msg_type != "message":
            return

        # Process regular messages
        await self._process_text_message(sender_id, chat_id, content, media, metadata)

    async def _process_text_message(
        self, sender_id: str, chat_id: str, content: str, media: list, metadata: dict
    ) -> None:
        """
        Process text message with optional media attachments.

        Args:
            sender_id: Message sender identifier.
            chat_id: Chat session identifier.
            content: Message text content.
            media: List of media items.
            metadata: Additional message metadata.
        """
        meta_type = metadata.get("msg_type", "text")

        # Skip empty messages (unless it's a media message)
        if not content and not media and not metadata:
            return

        # Handle audio-only messages
        if not content and meta_type == "audio":
            await self.channel_ref._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                media=media,
                metadata=metadata,
            )
            return

        # Handle base64-encoded media (images, audio, files)
        content_parts = []
        media_paths = []

        if content:
            content_parts.append(content)
        elif media:
            content_parts.append("Just save the following files, do nothing else: ")

        if media:
            for media_item in media:
                media_data = media_item["data"]
                filename = media_item.get("file_name", "")

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
        await self.channel_ref._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            media=media_paths,
            metadata=metadata,
        )

    async def send_msg(self, msg: OutboundMessage) -> bool:
        """
        Send a message through WebSocket.

        Args:
            msg: Outbound message to send.

        Returns:
            True if message was sent successfully, False otherwise.
        """
        if not self.channel_ref or not self.channel_ref._running:
            logger.warning("Channel not running, cannot send message")
            return False

        # Get the appropriate websocket connection from channel
        websocket = self.channel_ref._get_websocket_for_chat(msg.chat_id)
        if not websocket:
            logger.warning("No WebSocket connection available for chat_id: {}", msg.chat_id)
            return False

        try:
            # Handle audio messages with opus encoding
            if (
                msg.metadata.get("msg_type", "text") == "audio"
                and msg.metadata.get("encoder_type", "") == "opus"
            ):
                return await self._send_audio_message(msg, websocket)
            else:
                return await self._send_text_message(msg, websocket)
        except Exception as e:
            logger.error("Error sending WebSocket message: {}", e)
            return False

    async def _send_audio_message(self, msg: OutboundMessage, websocket: Any) -> bool:
        """
        Send audio message with TTS streaming.

        Args:
            msg: Outbound message containing audio data.
            websocket: WebSocket connection.

        Returns:
            True if message was sent successfully.
        """
        self._stop_audio = False
        frame_duration = msg.metadata.get("frame_duration", 60)

        # Send TTS start signals
        await websocket.send(
            json.dumps({"type": "tts", "state": "start", "session_id": msg.chat_id})
        )
        await websocket.send(
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

        # Send audio frames
        for media_item in msg.media:
            if self._stop_audio:
                break
            await websocket.send(media_item)
            await asyncio.sleep(frame_duration / 1000.0)

        # Send TTS end signals
        await websocket.send(
            json.dumps({"type": "tts", "state": "sentence_end", "session_id": msg.chat_id})
        )
        await websocket.send(
            json.dumps({"type": "tts", "state": "stop", "session_id": msg.chat_id})
        )

        return True

    async def _send_text_message(self, msg: OutboundMessage, websocket: Any) -> bool:
        """
        Send text message with optional media.

        Args:
            msg: Outbound message containing text and/or media.
            websocket: WebSocket connection.

        Returns:
            True if message was sent successfully.
        """
        # Convert media bytes to base64 for JSON serialization
        media_items = []
        if msg.media:
            for media_item in msg.media:
                if isinstance(media_item, bytes):
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

        await websocket.send(json.dumps(message_data, ensure_ascii=False))
        return True

    async def _handle_register_extern_tools(self, sender_id: str, chat_id: str, metadata: dict):
        """Handle external tool registration request."""
        mcp_tools = []
        tools_data = metadata.get("tools", [])

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

        await self.channel_ref._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content="/register_extern_tools",
            metadata={
                "type": "websocket",
                "kwargs": {
                    "websocket": self.channel_ref._server,
                    "timeout": 30,
                    "result_queue": self._mcp_result_queue,
                },
                "tools": mcp_tools,
            },
        )

    async def _handle_tool_call_result(self, msg_data: dict, metadata: dict):
        """Handle tool call result and put it into queue."""
        try:
            tool_name = msg_data.get("name") or metadata.get("tool_name")
            await self._mcp_result_queue.put(
                {"msg_id": tool_name, "result": msg_data.get("result", {})}
            )
            logger.debug(f"Put tool call result into queue, tool_name={tool_name}")
        except Exception as e:
            logger.error(f"Failed to put tool call result into queue: {e}")
