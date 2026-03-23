"""Async message queue for decoupled channel-agent communication."""

import asyncio
from typing import Dict, List

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.handlers.base_handler import BaseHandler
from nanobot.config.schema import BusConfig, HandlersConfig


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
        self.handlers: Dict[str, List[BaseHandler]] = self._init_handlers(config)

    def _init_handlers(self, config: BusConfig):
        """Initialize input handlers from config."""
        handlers = {}

        def _add_handler(handler_cfg):
            if handler_cfg and handler_cfg.enabled:
                handler_cls = BaseHandler.get_registered_type(handler_cfg.handler_type)
                if handler_cls:
                    sub_handlers = handlers.setdefault(handler_cls.msg_type(), [])
                    sub_handlers.append(handler_cls(handler_cfg))

        handlers_config: HandlersConfig = config.handlers
        _add_handler(handlers_config.asr)
        _add_handler(handlers_config.vad)
        _add_handler(handlers_config.tts)
        info = {k: [h.handler_type() for h in v] for k, v in handlers.items()}
        logger.info(f"Handlers: {info}")
        return handlers

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """
        Publish a message from a channel to the agent.

        If the message contains media, it will be automatically
        transcribed to text before being published.
        """
        msg_type, processed = msg.metadata.get("msg_type", "text"), True
        while msg_type in self.handlers and processed:
            processed = False
            for handler in self.handlers[msg_type]:
                h_mark = f"{handler.handler_type()}_processed"
                if handler.can_handle_input(msg) and not msg.metadata.get(h_mark, False):
                    msg = await handler.handle_input(msg)
                    msg.metadata[h_mark], processed = True, True
            msg_type = msg.metadata.get("msg_type", "text")
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        msg_type, processed = msg.metadata.get("msg_type", "text"), True
        while msg_type in self.handlers and processed:
            processed = False
            for handler in self.handlers[msg_type]:
                h_mark = f"{handler.handler_type()}_processed"
                if handler.can_handle_output(msg) and not msg.metadata.get(h_mark, False):
                    msg = await handler.handle_output(msg)
                    msg.metadata[h_mark], processed = True, True
            msg_type = msg.metadata.get("msg_type", "text")
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
