"""Rerun channel for visualization through Rerun.io."""

import asyncio
from typing import Any

from loguru import logger
from pydantic import Field

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import Base


class RerunConfig(Base):
    """Rerun channel configuration."""

    enabled: bool = False
    grpc_port: int = 9876  # gRPC server port for Rerun
    web_port: int = 9090  # Web viewer port
    open_browser: bool = False  # Whether to automatically open browser
    allow_from: list[str] = Field(default_factory=list)  # Allowed sender identifiers


class RerunChannel(BaseChannel):
    """
    Rerun channel for real-time visualization.

    This channel starts a Rerun gRPC server and web viewer, allowing
    visual data to be sent and displayed in real-time through the Rerun.io platform.

    Features:
    - Automatic gRPC server startup
    - Web viewer integration
    - Configurable ports and host
    - Optional automatic browser opening
    - URL logging for easy access

    Usage:
    The channel will start a Rerun server that can receive visualization data.
    Access the web viewer at: http://{host}:{web_port}/?url={encoded_server_uri}
    """

    name = "rerun"

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return RerunConfig().model_dump(by_alias=True)

    def __init__(self, config: RerunConfig, bus: MessageBus):
        """Initialize the Rerun channel with the given configuration and message bus.

        Args:
            config: Rerun channel configuration.
            bus: Message bus for communication.
        """
        if isinstance(config, dict):
            config = RerunConfig.model_validate(config)
        super().__init__(config, bus)
        self._server_task: asyncio.Task | None = None
        self._rr_initialized = False
        self.server_uri: str | None = None
        self.web_viewer_url: str | None = None

    async def start(self) -> None:
        """Start the Rerun channel with server and web viewer."""
        self._running = True

        try:
            from urllib.parse import quote

            import rerun as rr

            # Initialize Rerun recording
            rr.init("nanobot_visualization")

            # Start gRPC server
            self.server_uri = rr.serve_grpc(
                grpc_port=self.config.grpc_port,
                default_blueprint=None,
                server_memory_limit="2GiB",
            )

            # Start web viewer
            rr.serve_web_viewer(
                open_browser=self.config.open_browser,
                web_port=self.config.web_port,
                connect_to=self.server_uri,
            )

            # Generate web viewer URL
            encoded_uri = quote(self.server_uri, safe="")
            self.web_viewer_url = f"http://127.0.0.1:{self.config.web_port}/?url={encoded_uri}"
            logger.info("Rerun gRPC server started: {}", self.server_uri)
            logger.info("Web Viewer URL: {}", self.web_viewer_url)
            self._rr_initialized = True

            # Keep the server running
            while self._running:
                await asyncio.sleep(1)

        except ImportError:
            logger.error(
                "Rerun package not installed. Please install it with: pip install rerun-sdk"
            )
            raise
        except Exception as e:
            logger.error("Failed to start Rerun server: {}", e)
            raise

    async def stop(self) -> None:
        """Stop the Rerun channel."""
        self._running = False

        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            self._server_task = None

        self._rr_initialized = False
        logger.info("Rerun channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """Send visualization data through Rerun.

        Args:
            msg: The outbound message containing visualization data.
        """
        if not self._running or not self._rr_initialized:
            logger.warning("Rerun channel not running, cannot send message")
            return

        try:
            import rerun as rr

            # Parse message content for visualization data
            # The content should contain instructions for what to visualize
            content = msg.content

            # Example: Log points based on message content
            # This is a basic implementation - can be extended based on specific needs
            if content:
                # For now, just log a simple message entity
                rr.log(f"messages/{msg.chat_id}", rr.TextLog(content))

            logger.debug("Sent visualization data via Rerun")

        except ImportError:
            logger.error("Rerun package not available")
        except Exception as e:
            logger.error("Failed to send message via Rerun: {}", e)

    async def send_delta(
        self, chat_id: str, delta: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Send streaming visualization data through Rerun.

        Args:
            chat_id: The chat identifier.
            delta: The incremental data to visualize.
            metadata: Optional metadata for the visualization.
        """
        if not self._running or not self._rr_initialized:
            logger.warning("Rerun channel not running, cannot send delta")
            return

        try:
            import rerun as rr

            # Log streaming data
            if delta:
                rr.log(f"stream/{chat_id}", rr.TextLog(delta))

            logger.debug("Sent streaming visualization data via Rerun")

        except ImportError:
            logger.error("Rerun package not available")
        except Exception as e:
            logger.error("Failed to send delta via Rerun: {}", e)
