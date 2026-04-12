"""Providers manager for handling multiple LLM providers and modes."""

from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.config.schema import Config
from nanobot.providers.base import LLMProvider, LLMResponse


class ProvidersManager:
    """
    Manager for multiple LLM providers with mode-based selection.

    This class handles provider initialization and routing based on modes
    (main, coding, multimodal) to optimize for different use cases.
    """

    def __init__(
        self, config: Config, modes: dict, default_mode: str = "auto", provider_creator=None
    ):
        """
        Initialize the providers manager.

        Args:
            modes: AgentModes instance with mode configurations (main, coding, multimodal)
            default_mode: Default mode to use when none is specified ("auto" by default)
        """
        self._modes = modes
        self._default_mode, self._current_mode = default_mode, "main"
        self._config = config
        self._provider_creator = provider_creator
        self._send_callback = None
        self._default_channel = None
        self._default_chat_id = None
        self._default_message_id = None

    def _create_provider(self, model_id: str) -> LLMProvider:
        """
        Create a provider for the given model.

        Args:
            model_id: Model identifier (e.g., "anthropic/claude-opus-4-5")

        Returns:
            Initialized LLMProvider instance
        """

        if self._provider_creator:
            return self._provider_creator(model_id)
        p = self._config.get_provider(model_id)
        return LLMProvider(
            api_key=p.api_key if p else None,
            api_base=self._config.get_api_base(model_id),
            default_model=model_id,
            extra_headers=p.extra_headers if p else None,
        )

    async def choose_mode(self, content: str, mode: str = "") -> LLMProvider:
        """Choose provider from messages"""

        mode = mode or self._default_mode
        if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
            content = content.split("\n\n")[1]
        if not content:
            mode, content = "main", "foo task"
        if isinstance(content, list):
            mode = "multimodal"
        preview = str(content)[:20]
        if mode == "auto":
            assert "main" in self._modes, "No main mode configured for auto mode"
            # For auto mode, use decider to choose the best mode
            decider = self.get_provider("main")
            system_prompt = f"You are mode decider. You can choose the best mode for process the user's task. The modes are:\n{self.summary_modes()}"
            user_prompt = f"Which mode is best to process the task `{content}`? The answer should only has one word!"
            decider_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            # Get decider's response - it should return only a mode name
            decider_response = await decider.chat_with_retry(messages=decider_messages)
            selected_mode = decider_response.content.strip() if decider_response.content else "main"
            # Use the selected mode's provider
            if selected_mode in self._modes:
                logger.debug(f"Choose {selected_mode} for task: {preview}")
                self._current_mode = selected_mode
            else:
                # Fallback to main if selected mode not found
                logger.debug(f"Fallback to main for task: {preview}")
                self._current_mode = "main"
        elif mode in self._modes:
            logger.debug(f"Use specified {mode} for task: {preview}")
            self._current_mode = mode
        elif "main" in self._modes:
            logger.debug(f"Fallback to main for task: {preview}")
            self._current_mode = "main"
        else:
            raise ValueError(f"Unknown mode: {mode} and no fallback available")
        return self._current_mode

    async def check_fast_reply(self, msg: InboundMessage, features: dict) -> OutboundMessage | None:
        """Check if the content is a fast reply and return the corresponding message"""
        if features.get("audio_playing", False):
            decider = self.get_provider("main")
            system_prompt = "You are an audio playback controller. Determine if the user's message indicates they want to stop the current audio playback. Answer only with 'yes' or 'no'."
            user_prompt = f"User message: `{msg.content}`\n\nShould we stop the audio playback? Answer yes or no only."
            decider_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            # Get decider's response - it should return only yes or no
            decider_response = await decider.chat_with_retry(messages=decider_messages)
            decision = (
                decider_response.content.strip().lower() if decider_response.content else "no"
            )
            logger.debug(
                "Audio playback {} by user request".format(
                    "stopped" if decision == "yes" else "continued"
                )
            )
            if decision == "yes":
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="/stop_audio",
                    metadata={"_is_final": True, "_hide_message": True},
                )
        return None

    async def chat_stream_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: object = LLMProvider._SENTINEL,
        temperature: object = LLMProvider._SENTINEL,
        reasoning_effort: object = LLMProvider._SENTINEL,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        """Wrapper of chat_stream_with_retry of provider"""

        provider = self.get_provider(self._current_mode)
        return await provider.chat_stream_with_retry(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            on_content_delta=on_content_delta,
        )

    async def chat_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: object = LLMProvider._SENTINEL,
        temperature: object = LLMProvider._SENTINEL,
        reasoning_effort: object = LLMProvider._SENTINEL,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Wrapper of chat_with_retry of provider"""

        provider = self.get_provider(self._current_mode)
        return await provider.chat_with_retry(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )

    async def add_mode(self, mode: str, model_id: str, describe: str) -> None:
        """
        Add a new mode with the given configuration.

        Args:
            mode: Mode name (e.g., "main", "coding", "multimodal")
            model_id: Model identifier for this mode
            describe: Description of this mode's purpose
        """
        # Add to mode data
        self._modes[mode] = {
            "provider": self._create_provider(model_id),
            "describe": describe,
        }
        msg = OutboundMessage(
            channel=self._default_channel,
            chat_id=self._default_chat_id,
            content=f"Add mode -> {mode}",
            metadata={"_trigger_cmd": "/inspect"},
        )
        await self._send_callback(msg)

    async def update_mode(self, mode: str, model_id: str) -> None:
        """
        Update an existing mode's configuration.

        Args:
            mode: Mode name to update
            model_id: New model identifier for this mode
        """
        if mode not in self._modes:
            raise ValueError(f"Mode '{mode}' does not exist. Use add_mode to create it first.")

        # Check if we need to create a new provider
        current_model = self.get_model(mode)
        assert model_id == current_model, "Model ID unchanged"
        if model_id != current_model:
            # Create new provider for the new model
            self._modes[mode].update({"provider": self._create_provider(model_id)})
        msg = OutboundMessage(
            channel=self._default_channel,
            chat_id=self._default_chat_id,
            content=f"Update mode -> {mode}",
            metadata={"_trigger_cmd": "/inspect"},
        )
        await self._send_callback(msg)

    async def remove_mode(self, mode: str) -> None:
        """
        Remove a mode from the modes configuration.

        Args:
            mode: Mode name to remove
        """
        if mode in self._modes:
            self._modes.pop(mode)
        msg = OutboundMessage(
            channel=self._default_channel,
            chat_id=self._default_chat_id,
            content=f"Remove mode -> {mode}",
            metadata={"_trigger_cmd": "/inspect"},
        )
        await self._send_callback(msg)

    async def change_mode(self, mode):
        """Set the default mode."""

        self._default_mode = mode
        msg = OutboundMessage(
            channel=self._default_channel,
            chat_id=self._default_chat_id,
            content=f"Change mode -> {mode}",
            metadata={"_trigger_cmd": "/inspect"},
        )
        await self._send_callback(msg)

    def summary_modes(self) -> str:
        """
        Generate a summary string describing all available modes.

        Returns:
            A string describing each mode's model_id and describe, suitable for
            passing to provider.chat for mode selection decisions.
        """
        if not self._modes:
            return "No modes configured."

        summary_parts = []
        for mode_name, m_info in self._modes.items():
            summary_parts.append(
                f"Mode '{mode_name}'({self.get_model(mode_name)}) : {m_info['describe']}"
            )
        return "\n".join(summary_parts)

    def get_provider(self, mode: str):
        """
        Returns the provider for the given mode.
        Args:
            mode: Mode name (e.g., "main", "coding", "multimodal")
        """

        assert mode in self._modes, "Mode not found"
        assert "provider" in self._modes[mode], "Provider not found in mode configuration"
        return self._modes[mode]["provider"]

    def get_model(self, mode: str):
        """
        Returns the model for the given mode.
        Args:
            mode: Mode name (e.g., "main", "coding", "multimodal")
        """

        return self.get_provider(mode).get_default_model()

    def get_default_model(self) -> str:
        """Get the default model."""
        return self.get_model("main")

    def get_default_mode(self):
        """Get the default mode."""
        return self._default_mode

    def list_models(self) -> list[str]:
        """List all available models."""

        return [
            {"name": k, "model": self.get_model(k), "describe": v["describe"]}
            for k, v in self._modes.items()
        ]

    def set_send_callback(self, send_callback) -> None:
        """Set the callback for sending messages."""
        self._send_callback = send_callback

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_message_id = message_id

    @property
    def generation(self):
        """Get the generation settings."""
        return self.get_provider("main").generation
