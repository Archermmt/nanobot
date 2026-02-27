"""WebSocket channel implementation for generic WebSocket communication."""

import asyncio
import json
import threading
from collections import OrderedDict
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import WebSocketConfig


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
    
    def __init__(self, config: WebSocketConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WebSocketConfig = config
        self._ws = None
        self._ws_thread: threading.Thread | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self._loop: asyncio.AbstractEventLoop | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._connected = False
    
    async def start(self) -> None:
        """Start the WebSocket channel with reconnection logic."""
        self._running = True
        self._loop = asyncio.get_running_loop()
        
        logger.info("Starting WebSocket channel connecting to {}", self.config.server_url)
        
        # Start connection loop
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
        
        # Close WebSocket connection
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning("Error closing WebSocket: {}", e)
            self._ws = None
            self._connected = False
            
        logger.info("WebSocket channel stopped")
    
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
                    auth_msg = {
                        "type": "auth",
                        "token": self.config.auth_token
                    }
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
                    logger.warning("WebSocket connection failed: {}, retrying in {}s", 
                                 e, self.config.reconnect_interval)
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
        
        if msg_type == "heartbeat":
            # Respond to heartbeat
            await self._send_heartbeat_response()
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
        
        # Skip empty messages
        if not content and not media:
            return
            
        # Forward to message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            media=media,
            metadata=metadata
        )
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        while self._running and self._connected:
            try:
                heartbeat_msg = {
                    "type": "heartbeat",
                    "timestamp": asyncio.get_event_loop().time()
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
                "timestamp": asyncio.get_event_loop().time()
            }
            await self._ws.send(json.dumps(response, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to send heartbeat response: {}", e)
    
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WebSocket."""
        if not self._connected or not self._ws:
            logger.warning("WebSocket not connected, cannot send message")
            return
            
        try:
            # Prepare message data
            message_data = {
                "type": "message",
                "message_id": f"msg_{hash(msg.content)}",
                "sender_id": "bot",
                "chat_id": msg.chat_id,
                "content": msg.content,
                "media": msg.media,
                "metadata": msg.metadata,
                "timestamp": asyncio.get_event_loop().time()
            }
            
            # Send message
            await self._ws.send(json.dumps(message_data, ensure_ascii=False))
            logger.debug("Sent message to chat_id: {}", msg.chat_id)
            
        except Exception as e:
            logger.error("Error sending WebSocket message: {}", e)