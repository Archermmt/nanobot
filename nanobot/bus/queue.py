"""Async message queue for decoupled channel-agent communication."""

import asyncio
from typing import Dict
from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.handlers.audio_handler import load_audio_handler
from nanobot.bus.handlers.base_handler import BaseHandler
from nanobot.config.schema import BusConfig, InputHandlerConfig


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
        self._input_handlers: Dict[str, BaseHandler] = {}
        self._output_handlers: Dict[str, BaseHandler] = {}
        input_handler: InputHandlerConfig = self.config.input_handler
        if input_handler.audio and input_handler.audio.enabled:
            self._input_handlers["audio"] = load_audio_handler(input_handler.audio)

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """
        Publish a message from a channel to the agent.

        If the message contains media, it will be automatically
        transcribed to text before being published.
        """
        msg_type = msg.metadata.get("msg_type", "text")
        handler = self._input_handlers.get(msg_type)
        if handler and handler.can_handle(msg):
            logger.info(
                "Processing {} input with {}", msg_type, handler.__class__.__name__
            )
            msg = await handler.handle(msg)
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        msg_type = msg.metadata.get("msg_type", "text")
        handler = self._output_handlers.get(msg_type)
        if handler and handler.can_handle(msg):
            logger.info(
                "Processing {} output with {}", msg_type, handler.__class__.__name__
            )
            msg = await handler.handle(msg)
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
