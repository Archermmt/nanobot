"""Agent tools: list modes, show current mode, switch mode."""

import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


# file path of agent
AGENT_FILE = Path.home() / ".nanobot" / "workspace" / "AGENT.json"


def _load_agent() -> dict:
    """Load AGENT.json file, return (data, errors)."""
    if not AGENT_FILE.exists():
        return {}

    try:
        with open(AGENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        return {}
    except IOError as e:
        return {}


def _load_modes() -> tuple[dict, list[str]]:
    """Load modes form AGENT.json file, return (data, errors)."""

    agent = _load_agent()
    if not agent.get("modes"):
        return {}, [f"Can not find modes in agent config {agent}"]

    try:
        return agent["modes"], []
    except json.JSONDecodeError as e:
        return {}, [f"Configuration file format error: {e}"]
    except IOError as e:
        return {}, [f"Read configuration file failed: {e}"]


def _save_modes(data: dict) -> list[str]:
    """Save modes to AGENT.json file, return errors."""

    agent = _load_agent()
    agent["modes"] = data
    try:
        with open(AGENT_FILE, "w", encoding="utf-8") as f:
            json.dump(agent, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return []
    except IOError as e:
        return [f"Save configuration file failed: {e}"]


class AgentModeListTool(Tool):
    """Tool to list all available modes."""

    @property
    def name(self) -> str:
        return "agent_mode_list"

    @property
    def description(self) -> str:
        return "List all available modes."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        data, errors = _load_modes()
        if errors:
            return "\n".join(errors)

        current = data.get("current_model", "unknown")
        models = data.get("models", [])

        lines = ["## 可用模型\n", "| 模式 | 模型 | 描述 |", "|------|------|------|"]

        for model in models:
            name = model.get("name", "unknown")
            model_id = model.get("model", "unknown")
            desc = model.get("describe", "unknown")
            lines.append(f"| {name} | {model_id} | {desc} |")

        current_model = next((m for m in models if m["name"] == current), None)
        if current_model:
            lines.append(f"\n**当前使用**: {current} ({current_model['model']})")
        else:
            lines.append(f"\n**当前使用**: {current} (模型未找到)")

        return "\n".join(lines)


class AgentModeStatusTool(Tool):
    """Tool to show current mode."""

    @property
    def name(self) -> str:
        return "agent_mode_status"

    @property
    def description(self) -> str:
        return "Query the current mode."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        data, errors = _load_modes()
        if errors:
            return "\n".join(errors)

        current = data.get("current_model", "unknown")
        models = data.get("models", [])

        current_model = next((m for m in models if m["name"] == current), None)
        if current_model:
            return f"当前模型：{current} ({current_model['model']})\n描述：{current_model.get('describe', '无描述')}"
        else:
            return f"当前模型：{current} (模型未找到)"


class AgentModeSwitchTool(Tool):
    """Tool to switch to a specific mode."""

    @property
    def name(self) -> str:
        return "agent_mode_switch"

    @property
    def description(self) -> str:
        return "Switch to a specific mode."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Target model mode name or description keyword, such as 'coding', 'multimodal', 'code', 'program', etc.",
                }
            },
            "required": ["target"],
        }

    async def execute(self, target: str, **kwargs: Any) -> str:
        data, errors = _load_modes()
        if errors:
            return "\n".join(errors)

        models = data.get("models", [])
        if not models:
            return "错误：没有可用的模型配置"

        # 尝试精确匹配模型名称
        target = target.strip().lower()
        matched = None

        # 先尝试精确匹配 name
        for model in models:
            if model["name"].lower() == target:
                matched = model["name"]
                break

        # 如果没有精确匹配，尝试智能匹配描述
        if not matched:
            keywords_map = {
                "coding": [
                    "代码",
                    "编程",
                    "开发",
                    "debug",
                    "函数",
                    "类",
                    "code",
                    "program",
                    "写代码",
                ],
                "multimodal": [
                    "图片",
                    "图像",
                    "多模态",
                    "ocr",
                    "文档",
                    "pdf",
                    "image",
                    "vision",
                    "看图",
                ],
                "common": [
                    "日常",
                    "聊天",
                    "通用",
                    "default",
                    "normal",
                    "普通",
                ],
            }

            # 统计每个模型匹配到的关键词数量
            match_scores = {}
            for model in models:
                name = model["name"].lower()
                desc = model.get("describe", "").lower()
                match_scores[model["name"]] = 0

                if name in keywords_map:
                    for keyword in keywords_map[name]:
                        if keyword in target:
                            match_scores[model["name"]] += 1
                        if keyword in desc:
                            match_scores[model["name"]] += 0.5

            # 选择得分最高的模型
            best_score = 0
            for model_name, score in match_scores.items():
                if score > best_score:
                    best_score = score
                    matched = model_name

        # 如果还是没有匹配，使用第一个模型作为默认
        if not matched and models:
            matched = models[0]["name"]

        if not matched:
            return f"错误：找不到模型 '{target}'"

        # 更新当前模型
        old_current = data.get("current_model", "unknown")
        data["current_model"] = matched
        save_errors = _save_modes(data)
        if save_errors:
            return "\n".join(save_errors)

        matched_model = next((m for m in models if m["name"] == matched), None)
        return (
            f"✓ 模型已切换：{old_current} → {matched}\n"
            f"  模型：{matched_model['model']}\n"
            f"  描述：{matched_model.get('describe', '无描述')}"
        )
