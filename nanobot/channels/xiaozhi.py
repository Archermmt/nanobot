"""XiaoZhi channel implementation for WebSocket communication with ESP32 devices."""

import asyncio
import base64
import json
import subprocess
import tempfile
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import websockets
from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import XiaoZhiConfig


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
        self._ws_server = None
        self._connected_clients: dict[any, dict] = {}
        self._message_handler_task: asyncio.Task | None = None
        self._auth_enabled = False
        self._allowed_devices: set = set()
        self._auth_key = ""
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self.config_lock = asyncio.Lock()

        # VAD and module initialization
        self._vad = None

        # OTA handler initialization
        try:
            from .xiaozhi_server.core.api.ota_handler import OTAHandler

            self._ota_handler = OTAHandler(config)
        except Exception as e:
            logger.error(f"初始化 OTAHandler 失败：{e}")
            self._ota_handler = None

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

    async def _handle_ota_request(self, websocket: any, path: str, request_headers: any) -> any:
        """
        Handle OTA HTTP requests by delegating to OTAHandler.

        Args:
            websocket: The WebSocket connection object.
            path: The request path.
            request_headers: The HTTP request headers.

        Returns:
            HTTP response from OTAHandler.
        """
        if not self._ota_handler:
            logger.error("OTAHandler not initialized")
            return websocket.respond(500, "OTA service not available")

        try:
            # Delegate to OTAHandler based on path
            if path == "/xiaozhi/ota/" or path == "/xiaozhi/ota":
                # GET request
                return await self._ota_handler.handle_get(request_headers)
            elif path.startswith("/xiaozhi/ota/download/"):
                # Download request
                filename = path.replace("/xiaozhi/ota/download/", "")

                # Create a mock request object for OTAHandler
                class MockRequest:
                    def __init__(self, fname):
                        self.match_info = {"filename": fname}

                mock_request = MockRequest(filename)
                return await self._ota_handler.handle_download(mock_request)
            else:
                # POST request - would need proper implementation with body reading
                logger.warning("OTA POST request not fully supported in this context")
                return websocket.respond(405, "Method Not Allowed")
        except Exception as e:
            logger.error(f"OTA request error: {e}")
            return websocket.respond(500, f"Internal Server Error: {str(e)}")

    def _initialize_modules(self, update_vad: bool = False):
        """
        Initialize VAD module.

        Args:
            update_vad: Whether to update VAD module
        """
        try:
            # Try to import and initialize modules
            # This is a simplified version - in real implementation you would
            # load the actual VAD modules based on config
            if update_vad:
                logger.info("Reinitializing VAD module")
                # self._vad = load_vad_module(self.config)

            logger.info("Module initialization completed")
        except Exception as e:
            logger.error(f"初始化模块失败：{e}")

    def _check_vad_update(self, old_config: any, new_config: any) -> bool:
        """
        Check if VAD needs to be updated.

        Args:
            old_config: Old configuration
            new_config: New configuration

        Returns:
            bool: True if VAD needs update
        """
        try:
            old_vad = getattr(old_config, "selected_module", {}).get("VAD", "")
            new_vad = getattr(new_config, "selected_module", {}).get("VAD", "")
            return old_vad != new_vad
        except Exception:
            return False

    async def update_config(self) -> bool:
        """
        Update server configuration and reinitialize components.

        Returns:
            bool: True if update successful
        """
        try:
            async with self.config_lock:
                # Get new configuration (this is a placeholder - implement based on your config source)
                new_config = self.config  # TODO: Implement actual config fetching

                if new_config is None:
                    logger.error("获取新配置失败")
                    return False

                logger.info("获取新配置成功")

                # Check if VAD needs update
                update_vad = self._check_vad_update(self.config, new_config)
                logger.info(f"检查 VAD 类型是否需要更新：{update_vad}")

                # Update configuration
                self.config = new_config

                # Reinitialize modules
                self._initialize_modules(update_vad)

                logger.info("更新配置任务执行完毕")
                return True
        except Exception as e:
            logger.error(f"更新服务器配置失败：{str(e)}")
            return False

    async def _handle_ota_request(self, websocket: any, path: str, request_headers: any) -> any:
        """
        Handle OTA HTTP requests by delegating to OTAHandler.

        Args:
            websocket: The WebSocket connection object.
            path: The request path.
            request_headers: The HTTP request headers.

        Returns:
            HTTP response from OTAHandler.
        """
        if not self._ota_handler:
            logger.error("OTAHandler not initialized")
            return websocket.respond(500, "OTA service not available")

        try:
            # Delegate to OTAHandler based on path
            if path == "/xiaozhi/ota/" or path == "/xiaozhi/ota":
                # GET request
                return await self._ota_handler.handle_get(request_headers)
            elif path.startswith("/xiaozhi/ota/download/"):
                # Download request
                filename = path.replace("/xiaozhi/ota/download/", "")

                # Create a mock request object for OTAHandler
                class MockRequest:
                    def __init__(self, fname):
                        self.match_info = {"filename": fname}

                mock_request = MockRequest(filename)
                return await self._ota_handler.handle_download(mock_request)
            else:
                # POST request - would need proper implementation with body reading
                logger.warning("OTA POST request not fully supported in this context")
                return websocket.respond(405, "Method Not Allowed")
        except Exception as e:
            logger.error(f"OTA request error: {e}")
            return websocket.respond(500, f"Internal Server Error: {str(e)}")

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
        # Check if auth is enabled
        if not self._auth_enable:
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

    def get_vad(self):
        """
        Get the VAD instance.

        Returns:
            The VAD instance or None if not initialized.
        """
        return self._vad

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
                await self._process_incoming_message(msg_data)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON message from {}: {}", client_info["device_id"], e)
                await websocket.send(
                    json.dumps({"type": "error", "content": "Invalid JSON format"})
                )
            except Exception as e:
                logger.error("Error processing message from {}: {}", client_info["device_id"], e)

    async def _process_incoming_message(self, msg_data: dict) -> None:
        """Process an incoming message from WebSocket."""
        msg_type = msg_data.get("type", "message")

        # Handle special message types
        if msg_type == "heartbeat":
            await self._send_heartbeat_response()
            return
        elif msg_type == "ping":
            await self._send_pong_response()
            return
        elif msg_type != "message":
            # Ignore unknown message types
            return

        # Extract message fields
        message_id = msg_data.get("message_id") or str(hash(str(msg_data)))
        sender_id = msg_data.get("sender_id", "unknown")
        chat_id = msg_data.get("chat_id", "default")
        content = msg_data.get("content", "")
        media = msg_data.get("media", [])
        metadata = msg_data.get("metadata", {})

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
        # Handle base64-encoded media (images, audio, files)
        # Convert base64 data to temporary files
        content_parts = []
        media_paths = []
        if content:
            content_parts.append(content)
        elif media:
            content_parts.append("Just save the following files, do nothing else: ")
        if media:
            media_dir = Path.home() / ".nanobot" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            for i, media_item in enumerate(media):
                media_data, filename = media_item["data"], media_item.get("file_name", "")
                # Check if media is base64 data (data URL format: data:<mime>;base64,<data>)
                if isinstance(media_data, str) and media_data.startswith("data:"):
                    try:
                        # Parse data URL
                        header, b64_data = media_data.split(",", 1)
                        mime_type = header.split(";")[0].replace("data:", "")

                        # Decode base64
                        file_data = base64.b64decode(b64_data)
                        if not filename:
                            # Determine file extension from mime type
                            ext_map = {
                                "image/jpeg": ".jpg",
                                "image/png": ".png",
                                "image/gif": ".gif",
                                "image/webp": ".webp",
                                "audio/webm": ".webm",
                                "audio/mp3": ".mp3",
                                "audio/aac": ".aac",
                                "audio/ogg": ".ogg",
                                "audio/wav": ".wav",
                                "video/mp4": ".mp4",
                            }
                            ext = ext_map.get(mime_type, ".bin")

                            # Save to temporary file
                            filename = f"ws_{message_id[:8]}_{i}{ext}"
                        file_path = media_dir / filename
                        # Read converted WAV file
                        if filename.endswith(".webm"):
                            # Change file extension from .webm to .wav
                            file_path = str(file_path).replace(".webm", ".wav")
                            with tempfile.NamedTemporaryFile(
                                suffix=".webm", delete=False
                            ) as tmp_in:
                                tmp_in.write(file_data)
                                tmp_in_path = tmp_in.name

                            result = subprocess.run(
                                [
                                    "ffmpeg",
                                    "-i",
                                    tmp_in_path,
                                    "-ar",
                                    "16000",
                                    "-ac",
                                    "1",
                                    "-f",
                                    "wav",
                                    "-y",
                                    file_path,
                                ],
                                capture_output=True,
                                check=True,
                            )
                            # Check if conversion was successful
                            if result.returncode != 0:
                                logger.error(f"FFmpeg conversion failed: {result.stderr.decode()}")
                                raise RuntimeError(
                                    f"FFmpeg conversion failed with code {result.returncode}"
                                )
                            logger.info("Successfully converted audio to WAV format")
                        else:
                            file_path.write_bytes(file_data)
                        media_paths.append(str(file_path))
                        content_parts.append(f"{filename}({msg_type}) saved to {file_path}")
                        logger.debug("Saved base64 media to {}", file_path)
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

    async def _send_heartbeat_response(self) -> None:
        """Send heartbeat response."""
        if not self._connected_clients:
            return
        # Send to first connected client (can be optimized for multiple clients)
        ws = next(iter(self._connected_clients.keys()))
        try:
            response = {
                "type": "heartbeat_response",
                "timestamp": asyncio.get_event_loop().time(),
            }
            await ws.send(json.dumps(response, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to send heartbeat response: {}", e)

    async def _send_pong_response(self) -> None:
        """Send pong response."""
        if not self._connected_clients:
            return
        # Send to first connected client (can be optimized for multiple clients)
        ws = next(iter(self._connected_clients.keys()))
        try:
            response = {"type": "pong"}
            await ws.send(json.dumps(response, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to send pong response: {}", e)

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
            # Check if it's an OTA request
            path = request_headers.path
            if path and path.startswith("/xiaozhi/ota"):
                return await self._handle_ota_request(websocket, path, request_headers)
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
            if client_info["client_id"] == msg.chat_id or client_info["device_id"] == msg.chat_id:
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
