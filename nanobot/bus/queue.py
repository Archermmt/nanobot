"""Async message queue for decoupled channel-agent communication."""

import asyncio
from typing import Dict
from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.handlers.base_handler import BaseHandler
from nanobot.bus.handlers.audio_handler import load_audio_handler
from nanobot.config.schema import BusConfig


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.

    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    """

    def __init__(self, config: BusConfig | None = None):
        self.config = config or BusConfig()
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._handlers: Dict[str, BaseHandler] = {}
        if self.config.audio_handler and self.config.audio_handler.enabled:
            self._handlers["audio"] = load_audio_handler(self.config.audio_handler)

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """
        Publish a message from a channel to the agent.

        If the message contains audio media, it will be automatically
        transcribed to text before being published.
        """
        # Process audio messages automatically
        msg_type = msg.metadata.get("msg_type", "text")
        if msg_type in self._handlers and self._handlers[msg_type].can_handle(msg):
            logger.info("Processing {} message with {}", msg_type, self._handlers[msg_type].__class__.__name__)
            msg = await self._handlers[msg_type].handle(msg)
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()
