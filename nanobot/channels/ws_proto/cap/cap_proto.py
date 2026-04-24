"""CapWorker protocol for WebSocket-based agent interaction.

This module defines the protocol handler for CapWorker to communicate with
external agent servers via WebSocket, handling code generation queries,
multi-turn decisions, and trial execution results.
"""

import asyncio
import json
import time
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
    http_port: int = 8110  # HTTP server port for LLM requests


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
    - HTTP server for LLM request processing
    """

    def __init__(self, config: CapProtoConfig | dict, ws_config: Any, message_sender: Any):
        """
        Initialize the CapWorker protocol handler.

        Args:
            config: Protocol-specific configuration (dict or CapProtoConfig).
            ws_config: WebSocket channel configuration (for host, port, etc.).
            message_sender: Callback function for sending messages.
        """
        # Convert dict to config object if needed
        if isinstance(config, dict):
            config = CapProtoConfig.model_validate(config)
        super().__init__(config, ws_config, message_sender)
        self._result_queue: asyncio.Queue = asyncio.Queue()
        self._http_server, self._server_url = None, None
        self._task_response = None

    @classmethod
    def proto_name(cls) -> str:
        """Return the protocol name for registration."""
        return "cap"

    async def connect(self, client_info: dict) -> None:
        """
        Connect the protocol handler and OTA server.

        This method is called when the WebSocket channel connects.
        Starts the OTA HTTP server for firmware updates.

        Args:
            client_info: Client connection information (sender_id, chat_id, etc.).
        """
        import uvicorn

        # Start llm server
        http_app = self._create_http_app(
            sender_id=client_info["sender_id"], chat_id=client_info["chat_id"]
        )
        config = uvicorn.Config(
            http_app, host="localhost", port=self.config.http_port, log_level="info"
        )
        self._http_server = uvicorn.Server(config)
        self._server_url = f"http://localhost:{self.config.http_port}"
        asyncio.create_task(self._http_server.serve())
        logger.info(f"HTTP server started on {self._server_url}")

    def _create_http_app(self, sender_id: str = "cap_worker", chat_id: str = ""):
        """Create FastAPI application for LLM requests.

        Args:
            sender_id: The sender identifier for message routing.
            chat_id: The chat identifier for message routing.
        """
        try:
            from capx.serving.openrouter_server import (
                ChatCompletionRequest,
                ChatCompletionResponse,
                ChatCompletionResponseChoice,
                Message,
            )
            from fastapi import FastAPI, HTTPException
            from fastapi.middleware.cors import CORSMiddleware

            app = FastAPI(title="CapProto LLM Proxy", version="1.0.0")
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

            @app.post("/chat/completions")
            async def chat_completions(request: ChatCompletionRequest):
                """Handle chat completion requests."""
                try:
                    # Put request into inbound queue
                    self._task_response = None
                    client_kwargs = request.model_dump(exclude_none=True)
                    self.message_sender(
                        sender_id=sender_id,
                        chat_id=chat_id,
                        content=client_kwargs["prompt"],
                        metadata={
                            "msg_type": "prompt",
                            "llm_mode": client_kwargs.get("llm_mode", "main"),
                        },
                    )

                    print(f"[TMINFO] get client_kwargs {client_kwargs}", flush=True)
                    while not self._task_response:
                        await asyncio.sleep(0.5)

                    if self._task_response.get("error"):
                        raise HTTPException(status_code=500, detail=self._task_response["error"])

                    # Build response
                    choice = ChatCompletionResponseChoice(
                        index=0,
                        message=Message(role="assistant", content=self._task_response["content"]),
                        finish_reason=self._task_response.get("finish_reason", "stop"),
                    )

                    return ChatCompletionResponse(
                        id=f"chatcmpl-{int(time.time())}",
                        created=int(time.time()),
                        model="nanobot",
                        choices=[choice],
                    )

                except HTTPException:
                    raise
                except asyncio.TimeoutError:
                    logger.error("Timeout waiting for LLM response")
                    raise HTTPException(status_code=504, detail="Timeout waiting for LLM response")
                except Exception as e:
                    logger.error(f"Error in chat_completions: {e}")
                    import traceback

                    traceback.print_exc()
                    raise HTTPException(status_code=500, detail=str(e))

            @app.get("/health")
            async def health():
                return {"status": "ok"}

            return app

        except ImportError as e:
            logger.error(f"FastAPI dependencies not installed: {e}")
            logger.info("Install with: pip install fastapi uvicorn pydantic openai")
            raise

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

            logger.info(f"Client {agent_id} registered")
            return {"sender_id": client_type, "chat_id": agent_id}

        except Exception as e:
            logger.warning(f"Failed to extract client info from websocket: {e}")
            return None

    async def receive_msg(self, msg_data: dict, client_info: dict, websocket) -> None:
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
        """

        msg_type = msg_data.get("type", "")

        try:
            if msg_type == "extern_tools":
                # Register extern tools from agent
                ex_tools, tools_data = [], msg_data.get("tools", [])
                for tool in tools_data:
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
                await self.message_sender(
                    sender_id=client_info["sender_id"],
                    chat_id=client_info["chat_id"],
                    content="/register_extern_tools",
                    metadata={
                        "type": "cap",
                        "kwargs": {
                            "websocket": websocket,
                            "timeout": 30,
                            "server_url": self._server_url,
                            "result_queue": self._result_queue,
                        },
                        "tools": ex_tools,
                    },
                )
                return
            if msg_type == "task_result":
                # Put result into queue for tool to fetch
                await self._result_queue.put(
                    {
                        "chat_id": client_info["chat_id"],
                        "tool_id": "trigger_cap_task",
                        "result": msg_data["result"],
                    }
                )
                logger.debug(
                    f"Put trigger_cap_task result into queue, chat_id={client_info['chat_id']}"
                )
                return
            logger.warning(f"Unknown message type: {msg_type}")
            return
        except Exception as e:
            logger.error(f"Failed to process incoming message: {e}")
            import traceback

            traceback.print_exc()
            return

    async def send_msg(self, msg: OutboundMessage, client_info: dict, websocket: Any) -> dict:
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

        Returns:
            info: A dictionary containing information about the sent message.
        """
        msg_type = msg.metadata.get("msg_type", "text")
        if msg_type == "text":
            self._task_response = {"content": msg.content, **msg.metadata}
        return {"success": False}
