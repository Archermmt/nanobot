"""Chat channels module with plugin architecture."""

from nanobot.channels.base import BaseChannel
from nanobot.channels.manager import ChannelManager
from nanobot.channels.websocket import WebSocketChannel

__all__ = ["BaseChannel", "ChannelManager", "WebSocketChannel"]
