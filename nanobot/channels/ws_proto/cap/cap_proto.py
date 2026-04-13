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
    accept_senders: list[str] = ["cap-agent"]  # List of accepted sender IDs
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
        self._result_queue: asyncio.Queue = asyncio.Queue()
        self._mcp_result_queue: asyncio.Queue = asyncio.Queue()
        self._connected = False

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
        from urllib.parse import parse_qs

        try:
            # Extract agent_id from URL query parameters
            agent_id = None
            request_path = getattr(websocket, "path", "")
            if "?" in request_path:
                query_params = parse_qs(request_path.split("?", 1)[1])
                if "agent_id" in query_params:
                    agent_id = query_params["agent_id"][0]

            # Check if agent_id is in the list of accepted senders
            if agent_id not in self.config.accept_senders:
                logger.warning(f"Agent {agent_id} not accepted from {websocket.remote_address}")
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

            self._connected = True
            return {"agent_id": agent_id}

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
        agent_id = msg_data.get("agent_id", client_info.get("agent_id"))
        chat_id = client_info.get("chat_id", agent_id)
        content = msg_data.get("content", "")
        metadata = msg_data.get("metadata", {})

        try:
            if content == "/register_extern_tools":
                # Register extern tools from agent
                mcp_tools, tools_data = [], metadata.get("tools", [])
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
                    mcp_tools.append(new_tool)
                return {
                    "sender_id": agent_id,
                    "chat_id": chat_id,
                    "content": "/register_extern_tools",
                    "metadata": {
                        "type": "cap",
                        "kwargs": {
                            "websocket": websocket,
                            "timeout": 30,
                            "result_queue": self._mcp_result_queue,
                        },
                        "tools": mcp_tools,
                    },
                }

            if msg_type == "tool_call":
                # Put result into queue for tool to fetch
                try:
                    tool_name = msg_data.get("name") or metadata.get("tool_name")
                    await self._mcp_result_queue.put(
                        {"msg_id": tool_name, "result": msg_data.get("result", {})}
                    )
                    logger.debug(f"Put tool call result into queue, tool_name={tool_name}")
                except Exception as e:
                    logger.error(f"Failed to put tool call result into queue: {e}")
                return None

            if msg_type == "code_response":
                # Agent responded with generated code
                content = msg_data.get("content", "")
                reasoning = msg_data.get("reasoning", "")

                result = {
                    "sender_id": agent_id,
                    "chat_id": chat_id,
                    "content": content,
                    "metadata": {
                        "msg_type": "code_response",
                        "reasoning": reasoning,
                        **msg_data.get("metadata", {}),
                    },
                }

                # Put result into queue for CapWorker to fetch
                await self._result_queue.put(result)
                logger.debug(f"Received code response from agent {agent_id}")
                return result

            elif msg_type == "decision_response":
                # Agent responded with multi-turn decision
                content = msg_data.get("content", "")

                # Validate decision
                if content not in ["regenerate", "finish", "continue"]:
                    logger.warning(f"Invalid decision: {content}")
                    return None

                result = {
                    "sender_id": agent_id,
                    "chat_id": chat_id,
                    "content": content,
                    "metadata": {
                        "msg_type": "decision_response",
                        **msg_data.get("metadata", {}),
                    },
                }

                # Put result into queue for CapWorker to fetch
                await self._result_queue.put(result)
                logger.debug(f"Received decision response: {content} from agent {agent_id}")
                return result

            elif msg_type == "status":
                # Status update from agent
                status = msg_data.get("status", "")
                logger.info(f"Agent status: {status}")
                return {
                    "sender_id": agent_id,
                    "chat_id": chat_id,
                    "content": f"Status: {status}",
                    "metadata": {
                        "msg_type": "status",
                        "status": status,
                        **msg_data.get("metadata", {}),
                    },
                }

            elif msg_type == "error":
                # Error message from agent
                error_msg = msg_data.get("message", "Unknown error")
                logger.error(f"Agent error: {error_msg}")
                return {
                    "sender_id": agent_id,
                    "chat_id": chat_id,
                    "content": f"Error: {error_msg}",
                    "metadata": {
                        "msg_type": "error",
                        "error_message": error_msg,
                        **msg_data.get("metadata", {}),
                    },
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

        try:
            if msg_type == "query_code":
                # Send code generation query to agent
                message_data = {
                    "type": "query_code",
                    "prompt": msg.metadata.get("prompt", []),
                    "task_description": msg.content,
                    "metadata": msg.metadata,
                    "timestamp": asyncio.get_event_loop().time(),
                }

                await websocket.send(json.dumps(message_data, ensure_ascii=False))
                logger.debug("Sent query_code to agent")
                return {"success": True}

            elif msg_type == "query_decision":
                # Send multi-turn decision query to agent
                message_data = {
                    "type": "query_decision",
                    "prompt": msg.metadata.get("prompt", []),
                    "task_description": msg.content,
                    "metadata": msg.metadata,
                    "timestamp": asyncio.get_event_loop().time(),
                }

                await websocket.send(json.dumps(message_data, ensure_ascii=False))
                logger.debug("Sent query_decision to agent")
                return {"success": True}

            elif msg_type == "trial_result":
                # Send trial execution result to agent
                message_data = {
                    "type": "trial_result",
                    "trial": msg.metadata.get("trial", 0),
                    "success": msg.metadata.get("success", False),
                    "reward": msg.metadata.get("reward", 0.0),
                    "sandbox_rc": msg.metadata.get("sandbox_rc", -1),
                    "log": msg.metadata.get("log", ""),
                    "metadata": msg.metadata,
                    "timestamp": asyncio.get_event_loop().time(),
                }

                await websocket.send(json.dumps(message_data, ensure_ascii=False))
                logger.debug(f"Sent trial_result to agent (trial={msg.metadata.get('trial')})")
                return {"success": True}

            elif msg_type == "ping":
                # Keep-alive ping
                message_data = {
                    "type": "ping",
                    "timestamp": asyncio.get_event_loop().time(),
                }

                await websocket.send(json.dumps(message_data, ensure_ascii=False))
                return {"success": True}

            else:
                # Send common messages
                message_data = {
                    "type": "message",
                    "chat_id": msg.chat_id,
                    "content": msg.content,
                    "media": msg.media if msg.media else [],
                    "metadata": msg.metadata,
                    "timestamp": asyncio.get_event_loop().time(),
                }
                await websocket.send(json.dumps(message_data, ensure_ascii=False))
                return {"success": True}

        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            return {"success": False}

    async def wait_for_response(
        self, expected_type: str, timeout: float | None = None
    ) -> dict | None:
        """
        Wait for a specific type of response from the agent.

        Args:
            expected_type: Expected message type (e.g., 'code_response', 'decision_response')
            timeout: Timeout in seconds (uses config timeout if not specified)

        Returns:
            Response message dictionary or None if timeout/error
        """
        if timeout is None:
            timeout = self.config.timeout

        try:
            # Wait for response with timeout
            result = await asyncio.wait_for(self._result_queue.get(), timeout=timeout)

            # Verify message type
            if result.get("type") != expected_type:
                logger.warning(f"Expected {expected_type}, got {result.get('type')}")
                return None

            return result

        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for {expected_type}")
            return None
        except Exception as e:
            logger.error(f"Error waiting for response: {e}")
            return None

    async def close(self):
        """Close the protocol handler and clean up resources."""
        self._connected = False
        # Clear the result queue
        while not self._result_queue.empty():
            try:
                self._result_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.debug("CapProto closed")
