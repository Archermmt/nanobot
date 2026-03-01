"""Agent tools: unified mode management with add, remove, update, list, and switch methods."""

import json
from pathlib import Path
from typing import Any
from nanobot.agent.tools.base import Tool
from nanobot.config.loader import load_config
from nanobot.providers.base import LLMProvider


def _load_agent(workspace: Path) -> dict:
    """Load AGENT.json file, return data dict."""

    agent_file = workspace / "AGENT.json"
    if not agent_file.exists():
        return {}

    try:
        with open(agent_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError:
        return {}
    except IOError:
        return {}


def _save_agent(workspace: Path, data: dict) -> list[str]:
    """Save data to AGENT.json file, return errors."""

    agent_file = workspace / "AGENT.json"
    try:
        with open(agent_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return []
    except IOError as e:
        return [f"Save configuration file failed: {e}"]


def _find_model_by_mode_and_price(modes: dict, mode: str, price: str) -> dict | None:
    """Find a model by mode name and price tier."""
    models = modes.get("models", [])
    for model in models:
        if model.get("name") == mode:
            model_price = model.get("price", "free")
            if price == "" or model_price == price:
                return model
    return None


def _find_all_models_by_mode(modes: dict, mode: str) -> list[dict]:
    """Find all models by mode name (regardless of price)."""
    models = modes.get("models", [])
    return [model for model in models if model.get("name") == mode]


def _find_similar_mode(modes: dict, target: str) -> str | None:
    """Find a mode that matches or is similar to the target string."""
    if not target:
        return None

    target_lower = target.strip().lower()
    models = modes.get("models", [])

    # Direct name match
    for model in models:
        if model.get("name", "").lower() == target_lower:
            return model["name"]

    # Keywords mapping
    keywords_map = {
        "coding": ["代码", "编程", "开发", "debug", "函数", "类", "code", "program", "写代码"],
        "multimodal": ["图片", "图像", "多模态", "ocr", "文档", "pdf", "image", "vision", "看图"],
        "common": ["日常", "聊天", "通用", "default", "normal", "普通"],
    }

    # Score each mode
    match_scores = {}
    for model in models:
        name = model["name"]
        desc = model.get("describe", "").lower()
        if name not in match_scores:
            match_scores[name] = 0

        if name.lower() in keywords_map:
            for keyword in keywords_map[name.lower()]:
                if keyword in target_lower:
                    match_scores[name] += 1
                if keyword in desc:
                    match_scores[name] += 0.5

    # Return best match
    best_score = 0
    best_match = None
    for name, score in match_scores.items():
        if score > best_score:
            best_score = score
            best_match = name

    return best_match


class AgentModeTool(Tool):
    """
    Unified tool for agent mode management.

    Supports 5 methods:
    - add: Add a new model configuration
    - remove: Remove an existing model configuration
    - update: Update an existing model configuration
    - list: List all available models
    - switch: Switch to a specific model mode
    """

    def __init__(self, workspace: Path, provider: LLMProvider):
        """Initialize the agent mode tool with workspace and provider."""
        self.workspace = workspace
        self.provider = provider
        self.current_price = ""

    @property
    def name(self) -> str:
        return "agent_mode"

    @property
    def description(self) -> str:
        return (
            "Unified tool for managing agent LLM modes. "
            "Supports: add (add model), remove (remove model), update (update model), "
            "list (list all models), switch (switch to a mode)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["add", "remove", "update", "list", "switch"],
                    "description": "The method to perform: add, remove, update, list, or switch",
                },
                "price": {
                    "type": "string",
                    "description": "Price tier for the model (e.g., 'free', 'medium', 'high'). Default is '' (all prices). Required for all methods except list.",
                    "default": "",
                },
                "mode": {
                    "type": "string",
                    "description": "Mode name (e.g., 'common', 'coding', 'multimodal'). Required for all methods except list.",
                    "default": "common",
                },
                # Additional parameters for add/update
                "model": {
                    "type": "string",
                    "description": "Model identifier (e.g., 'openai/qwen3.5:cloud'). Required for add and update methods.",
                },
                # Additional parameters for add
                "describe": {
                    "type": "string",
                    "description": "Description of the model. Required for add and update methods.",
                },
            },
            "required": ["method"],
        }

    async def execute(self, method: str, price: str = "", mode: str = "common", **kwargs: Any) -> str:
        """Execute the specified method."""

        method = method.lower()
        if price and not self.current_price:
            self.current_price = price
        price = price or self.current_price
        if method == "list":
            return await self._list_modes()
        elif method == "switch":
            return await self._switch_mode(mode, price)
        elif method == "add":
            return await self._add_model(mode, price, kwargs.get("model"), kwargs.get("describe"))
        elif method == "remove":
            return await self._remove_model(mode, price)
        elif method == "update":
            return await self._update_model(mode, price, kwargs.get("model"), kwargs.get("describe"))
        else:
            return f"Error: Unknown method '{method}'. Supported methods: add, remove, update, list, switch"

    async def _list_modes(self) -> str:
        """List all available modes."""
        agent = _load_agent(self.workspace)
        modes = agent.get("modes", {})
        current_mode = modes.get("current_mode", "unknown")
        current_price = modes.get("current_price", "free")
        models = modes.get("models", [])
        lines = [
            "## Available Models",
            "",
            "| Mode | Price | Model | Description |",
            "|------|-------|-------|-------------|",
        ]

        for model in models:
            name = model.get("name", "unknown")
            model_price = model.get("price", "free")
            model_id = model.get("model", "unknown")
            desc = model.get("describe", "unknown")
            lines.append(f"| {name} | {model_price} | {model_id} | {desc} |")

        current_model = next(
            (m for m in models if m.get("name") == current_mode and m.get("price") == current_price), None
        )
        if current_model:
            lines.append("")
            lines.append(f"**Current**: {current_mode} ({current_price}) - {current_model['model']}")
        else:
            lines.append("")
            lines.append("**No mode available**")

        return "\n".join(lines)

    async def _switch_mode(self, mode: str, price: str) -> str:
        """Switch to a specific mode."""

        agent = _load_agent(self.workspace)
        modes = agent.get("modes", {})

        models = modes.get("models", [])
        if not models:
            return "Error: No model configurations found"

        # Find matching model
        target_mode = _find_similar_mode(modes, mode) if mode else mode

        if not target_mode:
            return f"Error: Could not find mode '{mode}'"

        # Find specific model by mode and price
        matched = _find_model_by_mode_and_price(modes, target_mode, price)

        if not matched:
            # Try to find any model in this mode
            mode_models = _find_all_models_by_mode(modes, target_mode)
            if not mode_models:
                return f"Error: No models found for mode '{target_mode}'"
            matched = mode_models[0]

        # Update current model
        old_current = modes.get("current_mode", "unknown")
        modes["current_mode"] = matched["name"]
        modes["current_price"] = matched.get("price", "free")

        # change provider
        self.provider.change_model(load_config(), matched["model"])

        save_errors = _save_agent(self.workspace, agent)
        if save_errors:
            return "\n".join(save_errors)

        return (
            f"✓ Mode switched: {old_current} → {matched['name']}\n"
            f"  Model: {matched['model']}\n"
            f"  Price: {matched.get('price', 'free')}\n"
            f"  Description: {matched.get('describe', 'No description')}"
        )

    async def _add_model(self, mode: str, price: str, model_id: str | None, describe: str | None) -> str:
        """Add a new model configuration."""
        if not model_id:
            return "Error: 'model' parameter is required for add method"
        if not describe:
            return "Error: 'describe' parameter is required for add method"
        if not mode:
            return "Error: 'mode' parameter is required for add method"

        agent = _load_agent(self.workspace)
        modes = agent.get("modes", {})

        models = modes.get("models", [])

        # Check if model with same mode and price already exists
        for m in models:
            if m.get("name") == mode and m.get("price") == price:
                return f"Error: Model '{mode}' with price '{price}' already exists"

        # Add new model
        new_model = {"name": mode, "price": price, "model": model_id, "describe": describe}
        models.append(new_model)
        modes["models"] = models
        agent["modes"] = modes

        save_errors = _save_agent(self.workspace, agent)
        if save_errors:
            return "\n".join(save_errors)

        return f"✓ Model added: {mode} ({price})\n" f"  Model: {model_id}\n" f"  Description: {describe}"

    async def _remove_model(self, mode: str, price: str) -> str:
        """Remove a model configuration."""
        if not mode:
            return "Error: 'mode' parameter is required for remove method"

        agent = _load_agent(self.workspace)
        modes = agent.get("modes", {})
        models = modes.get("models", [])

        # Find model to remove
        target_mode = _find_similar_mode(modes, mode) if mode else mode

        if not target_mode:
            return f"Error: Could not find mode '{mode}'"

        # Find specific model by mode and price
        matched = _find_model_by_mode_and_price(modes, target_mode, price)

        if not matched:
            return f"Error: No model found for mode '{target_mode}' with price '{price}'"

        # Remove the model
        models = [m for m in models if not (m.get("name") == target_mode and m.get("price") == price)]

        # Update current model if it was removed
        if modes.get("current_mode") == target_mode:
            if models:
                modes["current_mode"] = models[0]["name"]
            else:
                modes["current_mode"] = ""

        modes["models"] = models
        agent["modes"] = modes

        save_errors = _save_agent(self.workspace, agent)
        if save_errors:
            return "\n".join(save_errors)

        return f"✓ Model removed: {target_mode} ({price})\n" f"  Model: {matched['model']}"

    async def _update_model(self, mode: str, price: str, model_id: str | None) -> str:
        """Update an existing model configuration."""
        if not mode:
            return "Error: 'mode' parameter is required for update method"

        if not model_id:
            return "Error: 'model_id' parameter is required for update method"

        agent = _load_agent(self.workspace)
        modes = agent.get("modes", {})
        models = modes.get("models", [])

        # Find model to update
        target_mode = _find_similar_mode(modes, mode) if mode else mode

        if not target_mode:
            return f"Error: Could not find mode '{mode}'"

        # Find specific model by mode and price
        matched = _find_model_by_mode_and_price(modes, target_mode, price)

        if not matched:
            return f"Error: No model found for mode '{target_mode}' with price '{price}'"

        # Update fields
        if model_id:
            matched["model"] = model_id
        modes["models"] = models
        agent["modes"] = modes

        save_errors = _save_agent(self.workspace, agent)
        if save_errors:
            return "\n".join(save_errors)

        return (
            f"✓ Model updated: {target_mode} ({price})\n"
            f"  Model: {matched['model']}\n"
            f"  Description: {matched.get('describe', 'No description')}"
        )
