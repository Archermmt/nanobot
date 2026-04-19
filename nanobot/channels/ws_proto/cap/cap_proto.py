"""CapWorker protocol for WebSocket-based agent interaction.

This module defines the protocol handler for CapWorker to communicate with
external agent servers via WebSocket, handling code generation queries,
multi-turn decisions, and trial execution results.
"""

import asyncio
import json
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.channels.ws_proto.base_proto import BaseProto
from nanobot.config.schema import Base


class CapProtoConfig(Base):
    """CapWorker protocol configuration."""

    enabled: bool = True  # Whether this protocol is enabled
    auth_token: str = ""  # Authentication token for WebSocket connection
    max_retries: int = 3  # Maximum number of retry attempts for failed operations
    retry_delay: float = 1.0  # Delay between retries in seconds
    timeout: float = 300.0  # Timeout for WebSocket operations in seconds


@BaseProto.register()
class CapProto(BaseProto):
    """
    Protocol handler for CapWorker WebSocket communication.

    This protocol handles:
    - Connection establishment and authentication
    - Code generation query/response
    - Multi-turn decision query/response
    - Trial status updates
    - Error handling and retries
    """

    @classmethod
    def proto_name(cls) -> str:
        """Return the protocol name for registration."""
        return "cap"

    def __init__(self, config: CapProtoConfig | dict, ws_config: Any):
        """
        Initialize the CapWorker protocol handler.

        Args:
            config: Protocol-specific configuration (dict or CapProtoConfig).
            ws_config: WebSocket channel configuration (for host, port, etc.).
        """
        # Convert dict to config object if needed
        if isinstance(config, dict):
            config = CapProtoConfig.model_validate(config)
        super().__init__(config=config, ws_config=ws_config)

    async def accept(self, websocket) -> dict | None:
        """
        Check if the current websocket can be accepted by this proto.

        The CapWorker proto accepts connections from authorized agent servers
        and performs authentication if configured.

        Args:
            websocket: The WebSocket connection object.

        Returns:
            A dictionary containing client information if accepted, None otherwise.
        """

        try:
            headers = dict(websocket.request.headers) if hasattr(websocket, "request") else {}
            agent_id = headers.get("agent_id", "unknown-client")
            client_type = headers.get("client_type", "unknown")
            if client_type != "cap-worker":
                return None

            # Handle authentication if token is configured
            if self.config.auth_token:
                try:
                    auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    auth_data = json.loads(auth_msg)
                    if (
                        auth_data.get("type") == "auth"
                        and auth_data.get("token") == self.config.auth_token
                    ):
                        logger.debug("Agent authenticated successfully")
                        agent_id = auth_data.get("agent_id", agent_id)
                    else:
                        logger.warning("Authentication failed")
                        return None
                except asyncio.TimeoutError:
                    logger.warning("Authentication timeout")
                    return None
                except json.JSONDecodeError:
                    logger.warning("Invalid authentication message")
                    return None

            return {"sender_id": client_type, "chat_id": agent_id}

        except Exception as e:
            logger.warning(f"Failed to extract client info from websocket: {e}")
            return None

    async def receive_msg(self, msg_data: dict, client_info: dict, websocket) -> dict | None:
        """
        Receive and process incoming message from WebSocket.

        Handles different message types from the agent server:
        - agent_start: Register extern tools
        - code_response: Generated code from agent
        - decision_response: Multi-turn decision from agent
        - status: Status updates
        - error: Error messages

        Args:
            msg_data: Parsed message data dictionary.
            client_info: Client connection information (agent_id, etc.).
            websocket: The WebSocket connection object.

        Returns:
            Processed message dictionary or None if ignored.
        """

        msg_type = msg_data.get("type", "")

        try:
            if msg_type == "extern_tools":
                # Register extern tools from agent
                ex_tools, tools_data = [], msg_data.get("tools", [])
                for i, tool in enumerate(tools_data):
                    if not isinstance(tool, dict):
                        continue
                    name = tool.get("name", "")
                    description = tool.get("description", "")
                    input_schema = {"type": "object", "properties": {}, "required": []}
                    if "inputSchema" in tool and isinstance(tool["inputSchema"], dict):
                        schema = tool["inputSchema"]
                        input_schema["type"] = schema.get("type", "object")
                        input_schema["properties"] = schema.get("properties", {})
                        input_schema["required"] = [
                            s for s in schema.get("required", []) if isinstance(s, str)
                        ]
                    new_tool = {
                        "name": name,
                        "description": description,
                        "inputSchema": input_schema,
                    }
                    ex_tools.append(new_tool)
                return {
                    "sender_id": client_info["sender_id"],
                    "chat_id": client_info["chat_id"],
                    "content": "/register_extern_tools",
                    "metadata": {
                        "type": "cap",
                        "kwargs": {"websocket": websocket, "timeout": 30},
                        "tools": ex_tools,
                    },
                }
            elif msg_type == "query_model":
                return {
                    "type": "prompt",
                    "sender_id": client_info["sender_id"],
                    "chat_id": client_info["chat_id"],
                    "content": json.dumps(msg_data["prompt"]),
                }
            else:
                # Unknown message type
                logger.warning(f"Unknown message type: {msg_type}")
                return None
        except Exception as e:
            logger.error(f"Failed to process incoming message: {e}")
            return None

    async def send_msg(
        self, msg: OutboundMessage, client_info: dict, websocket: Any, callback=None
    ) -> dict:
        """
        Send a message through WebSocket to the agent server.

        Handles different message types to agent:
        - query_code: Request code generation
        - query_decision: Request multi-turn decision
        - trial_result: Send trial execution results

        Args:
            msg: Outbound message to send.
            client_info: Client connection information (agent_id, etc.).
            websocket: The WebSocket connection object.
            callback: Optional callback function for sending messages.

        Returns:
            info: A dictionary containing information about the sent message.
        """
        msg_type = msg.metadata.get("msg_type", "text")
        if msg_type == "text":
            await websocket.send(
                json.dumps({"type": "query_model_response", "content": msg.content})
            )
            return {"success": True}
        return {"success": False}
