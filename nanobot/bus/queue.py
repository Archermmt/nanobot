"""Async message queue for decoupled channel-agent communication."""

import asyncio
from typing import Dict, List

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.handlers.input.input_handler import InputHandler
from nanobot.bus.handlers.output.output_handler import OutputHandler
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
        self.input_handlers: Dict[str, List[InputHandler]] = self._init_input_handlers(config)
        self.output_handlers: Dict[str, List[OutputHandler]] = self._init_output_handlers(config)

    def _init_input_handlers(self, config: BusConfig):
        """Initialize input handlers from config."""
        handlers = {}

        def _add_handler(handler_cfg):
            if handler_cfg and handler_cfg.enabled:
                handler_cls = InputHandler.get_registered_type(handler_cfg.handler_type)
                if handler_cls:
                    sub_handlers = handlers.setdefault(handler_cls.msg_type(), [])
                    sub_handlers.append(handler_cls(handler_cfg))

        input_handler: InputHandlerConfig = config.input_handler
        _add_handler(input_handler.asr)
        logger.info(
            f"InputHandlers: {[(k, [h.handler_type() for h in v]) for k, v in handlers.items()]}"
        )
        return handlers

    def _init_output_handlers(self, config: BusConfig):
        """Initialize output handlers from config."""
        handlers = {}

        def _add_handler(handler_cfg):
            if handler_cfg and handler_cfg.enabled:
                handler_cls = OutputHandler.get_registered_type(handler_cfg.handler_type)
                if handler_cls:
                    sub_handlers = handlers.setdefault(handler_cls.msg_type(), [])
                    sub_handlers.append(handler_cls(handler_cfg))

        output_handler: OutputHandlerConfig = config.output_handler
        _add_handler(output_handler.tts)
        logger.info(
            f"OutputHandlers: {[(k, [h.handler_type() for h in v]) for k, v in handlers.items()]}"
        )
        return handlers

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """
        Publish a message from a channel to the agent.

        If the message contains media, it will be automatically
        transcribed to text before being published.
        """
        msg_type = msg.metadata.get("msg_type", "text")
        handlers = self.input_handlers.get(msg_type, [])
        for handler in handlers:
            if handler.can_handle(msg):
                logger.debug("Processing input({}) : {}", msg_type, handler.handler_type())
                msg = await handler.handle(msg)
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        msg_type = msg.metadata.get("msg_type", "text")
        handlers = self.output_handlers.get(msg_type, [])
        for handler in handlers:
            if handler.can_handle(msg):
                logger.debug("Processing output({}) : {}", msg_type, handler.handler_type())
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
