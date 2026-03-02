"""Tests for WebSocketChannel implementation."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.websocket import WebSocketChannel
from nanobot.config.schema import WebSocketConfig


def _make_config(as_server: bool = True) -> WebSocketConfig:
    """Create a test WebSocket configuration."""
    return WebSocketConfig(
        enabled=True,
        server_url="ws://localhost:8765",
        auth_token="test-token",
        allow_from=["user1", "user2"],
        reconnect_interval=5,
        heartbeat_interval=30,
        as_server=as_server,
    )


def test_websocket_channel_initialization():
    """Test WebSocketChannel initialization."""
    config = _make_config()
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)

    assert channel.name == "websocket"
    assert channel.config == config
    assert channel._ws is None
    assert channel._connected is False
    assert channel.is_running is False


@pytest.mark.asyncio
async def test_websocket_channel_start_initialization():
    """Test WebSocket channel initialization and basic start setup."""
    config = _make_config()
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)

    # Test initial state
    assert channel._running is False
    assert channel._connected is False
    assert channel._ws is None

    # Test that start sets running flag
    with patch.object(channel, "_connect_with_retry", return_value=None):
        start_task = asyncio.create_task(channel.start())
        await asyncio.sleep(0.01)  # Let it start
        assert channel._running is True
        await channel.stop()
        start_task.cancel()


@pytest.mark.asyncio
async def test_websocket_channel_send_message():
    """Test sending messages through WebSocket channel."""
    config = _make_config()
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)
    channel._connected = True

    # Mock WebSocket connection
    mock_ws = AsyncMock()
    channel._ws = mock_ws

    # Create test message
    msg = OutboundMessage(
        channel="websocket",
        chat_id="test-room",
        content="Hello, World!",
        media=["image.jpg"],
        metadata={"custom": "data"},
    )

    # Send message
    await channel.send(msg)

    # Get the actual sent message
    sent_message_str = mock_ws.send.call_args[0][0]
    sent_message = json.loads(sent_message_str)

    # Verify structure
    assert sent_message["type"] == "message"
    assert sent_message["sender_id"] == "bot"
    assert sent_message["chat_id"] == "test-room"
    assert sent_message["content"] == "Hello, World!"
    assert sent_message["media"] == ["image.jpg"]
    assert sent_message["metadata"] == {"custom": "data"}
    assert "message_id" in sent_message
    assert "timestamp" in sent_message


@pytest.mark.asyncio
async def test_websocket_channel_receive_message():
    """Test receiving messages from WebSocket."""
    config = _make_config()
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)
    channel._running = True
    channel._loop = asyncio.get_running_loop()

    # Mock the _handle_message method to capture calls
    handle_message_calls = []

    async def mock_handle_message(
        sender_id, chat_id, content, media=None, metadata=None
    ):
        handle_message_calls.append(
            {
                "sender_id": sender_id,
                "chat_id": chat_id,
                "content": content,
                "media": media or [],
                "metadata": metadata or {},
            }
        )

    channel._handle_message = mock_handle_message

    # Test message data
    test_message = {
        "type": "message",
        "message_id": "msg123",
        "sender_id": "user1",
        "chat_id": "room456",
        "content": "Test message",
        "media": ["photo.jpg"],
        "metadata": {"source": "web"},
    }

    # Process the message
    await channel._process_incoming_message(test_message)

    # Verify _handle_message was called correctly
    assert len(handle_message_calls) == 1
    call = handle_message_calls[0]
    assert call["sender_id"] == "user1"
    assert call["chat_id"] == "room456"
    assert call["content"] == "Test message"
    assert call["media"] == ["photo.jpg"]
    assert call["metadata"] == {"source": "web"}


@pytest.mark.asyncio
async def test_websocket_channel_deduplication():
    """Test message deduplication functionality."""
    config = _make_config()
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)
    channel._running = True
    channel._loop = asyncio.get_running_loop()

    # Mock _handle_message
    handle_message_calls = []
    channel._handle_message = AsyncMock(
        side_effect=lambda *args, **kwargs: handle_message_calls.append(True)
    )

    # Same message ID should be deduplicated
    message_data = {
        "type": "message",
        "message_id": "duplicate_msg",
        "sender_id": "user1",
        "chat_id": "room1",
        "content": "Hello",
    }

    # Process the same message twice
    await channel._process_incoming_message(message_data)
    await channel._process_incoming_message(message_data)

    # Should only be processed once
    assert len(handle_message_calls) == 1


@pytest.mark.asyncio
async def test_websocket_channel_is_allowed():
    """Test sender permission checking."""
    config = _make_config()
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)

    # Test allowed users
    assert channel.is_allowed("user1") is True
    assert channel.is_allowed("user2") is True

    # Test disallowed user
    assert channel.is_allowed("user3") is False

    # Test with empty allow list (should allow everyone)
    config_empty = WebSocketConfig(enabled=True, server_url="ws://test")
    channel_empty = WebSocketChannel(config_empty, bus)
    assert channel_empty.is_allowed("anyone") is True


@pytest.mark.asyncio
async def test_websocket_channel_connection_retry_logic():
    """Test connection retry logic setup."""
    config = _make_config()
    config.reconnect_interval = 0.1  # Fast retry for testing
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)

    # Test that retry interval is properly set
    assert channel.config.reconnect_interval == 0.1

    # Test that channel initializes with proper state
    assert channel._reconnect_task is None
    assert channel._connected is False


@pytest.mark.asyncio
async def test_websocket_channel_send_when_disconnected():
    """Test sending message when WebSocket is not connected."""
    config = _make_config()
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)
    channel._connected = False
    channel._ws = None

    # This should not raise an exception
    msg = OutboundMessage(channel="websocket", chat_id="test", content="Hello")

    await channel.send(msg)
    # If we get here without exception, the test passes


@pytest.mark.asyncio
async def test_websocket_channel_as_server_mode():
    """Test WebSocket channel in server mode."""
    config = _make_config(as_server=True)
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)

    # Verify configuration
    assert channel.config.as_server is True
    assert channel.name == "websocket"

    # Test initial state
    assert channel._running is False
    assert channel._connected is False
    assert channel._ws is None


@pytest.mark.asyncio
async def test_websocket_channel_as_client_mode():
    """Test WebSocket channel in client mode."""
    config = _make_config(as_server=False)
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)

    # Verify configuration
    assert channel.config.as_server is False
    assert channel.name == "websocket"

    # Test initial state
    assert channel._running is False
    assert channel._connected is False
    assert channel._ws is None


@pytest.mark.asyncio
async def test_websocket_channel_server_mode_start():
    """Test WebSocket channel start in server mode."""
    config = _make_config(as_server=True)
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)

    # Mock the _start_server method
    with patch.object(channel, "_start_server", return_value=None) as mock_start_server:
        start_task = asyncio.create_task(channel.start())
        await asyncio.sleep(0.01)  # Let it start

        # Verify _start_server was called
        mock_start_server.assert_called_once()
        assert channel._running is True

        await channel.stop()
        start_task.cancel()


@pytest.mark.asyncio
async def test_websocket_channel_client_mode_start():
    """Test WebSocket channel start in client mode."""
    config = _make_config(as_server=False)
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)

    # Mock the _connect_with_retry method
    with patch.object(
        channel, "_connect_with_retry", return_value=None
    ) as mock_connect:
        start_task = asyncio.create_task(channel.start())
        await asyncio.sleep(0.01)  # Let it start

        # Verify _connect_with_retry was called
        mock_connect.assert_called_once()
        assert channel._running is True

        await channel.stop()
        start_task.cancel()


@pytest.mark.asyncio
async def test_websocket_channel_server_mode_send():
    """Test sending messages in server mode."""
    config = _make_config(as_server=True)
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)
    channel._connected = True

    # Mock WebSocket connection (server side)
    mock_ws = AsyncMock()
    channel._ws = mock_ws

    # Create test message
    msg = OutboundMessage(
        channel="websocket",
        chat_id="server-room",
        content="Server message",
        media=[],
        metadata={"mode": "server"},
    )

    # Send message
    await channel.send(msg)

    # Verify message was sent
    mock_ws.send.assert_called_once()
    sent_message_str = mock_ws.send.call_args[0][0]
    sent_message = json.loads(sent_message_str)

    assert sent_message["type"] == "message"
    assert sent_message["sender_id"] == "bot"
    assert sent_message["chat_id"] == "server-room"
    assert sent_message["content"] == "Server message"
    assert sent_message["metadata"] == {"mode": "server"}


@pytest.mark.asyncio
async def test_websocket_channel_server_mode_stop():
    """Test stopping WebSocket channel in server mode."""
    config = _make_config(as_server=True)
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)
    channel._running = True
    channel._connected = True

    # Mock WebSocket server
    mock_ws = AsyncMock()
    channel._ws = mock_ws

    # Stop the channel
    await channel.stop()

    # Verify cleanup
    assert channel._running is False
    assert channel._connected is False
    mock_ws.close.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_channel_client_mode_stop():
    """Test stopping WebSocket channel in client mode."""
    config = _make_config(as_server=False)
    bus = MessageBus()

    channel = WebSocketChannel(config, bus)
    channel._running = True
    channel._connected = True

    # Mock WebSocket client connection
    mock_ws = AsyncMock()
    channel._ws = mock_ws

    # Stop the channel
    await channel.stop()

    # Verify cleanup
    assert channel._running is False
    assert channel._connected is False
    mock_ws.close.assert_called_once()


if __name__ == "__main__":
    # pytest.main([__file__, "-v"])
    test_websocket_channel_initialization()
