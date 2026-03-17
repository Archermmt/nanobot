"""Async message queue for decoupled channel-agent communication."""

import asyncio
from typing import Dict

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.handlers.input.audio_handler import BaseAudioHandler
from nanobot.bus.handlers.input.input_handler import InputHandler
from nanobot.bus.handlers.output.text_handler import BaseTextHandler
from nanobot.config.schema import BusConfig, InputHandlerConfig, OutputHandlerConfig


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
        self.input_handlers: Dict[str, InputHandler] = {}
        self.output_handlers: Dict[str, InputHandler] = {}
        input_handler: InputHandlerConfig = self.config.input_handler
        if input_handler.audio and input_handler.audio.enabled:
            handler_cls = BaseAudioHandler.get_registered_type(input_handler.audio.handler_type)
            self.input_handlers["audio"] = handler_cls(input_handler.audio)
        output_handler: OutputHandlerConfig = self.config.output_handler
        if output_handler.text and output_handler.text.enabled:
            handler_cls = BaseTextHandler.get_registered_type(output_handler.text.handler_type)
            self.output_handlers["text"] = handler_cls(output_handler.text)
        logger.info(f"InputHandlers: {list(self.input_handlers.keys())}")
        logger.info(f"OutputHandlers: {list(self.output_handlers.keys())}")

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """
        Publish a message from a channel to the agent.

        If the message contains media, it will be automatically
        transcribed to text before being published.
        """
        msg_type = msg.metadata.get("msg_type", "text")
        handler = self.input_handlers.get(msg_type)
        if handler and handler.can_handle(msg):
            logger.debug("Processing input({}) : {}", msg_type, handler.__class__.__name__)
            msg = await handler.handle(msg)
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        msg_type = msg.metadata.get("msg_type", "text")
        handler = self.output_handlers.get(msg_type)
        if handler and handler.can_handle(msg):
            logger.debug("Processing output({}) : {}", msg_type, handler.__class__.__name__)
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
