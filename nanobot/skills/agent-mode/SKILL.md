---
name: agent-mode
description: Switch and manage LLM models used by nanobot.
metadata: {"nanobot":{"emoji":"🔄"}}
---

# Model Switcher

Switch and manage LLM models used by nanobot.

## Features

- View list of currently available models
- Switch to specified model
- View currently used model
- Support intelligent switching through model descriptions

## Tools

This skill provides the following three tools:

### 1. `agent_mode_list`

List all available model modes.

**Parameters**: None

**Example**:
```
<tool>agent_mode_list</tool>
```

### 2. `agent_mode_status`

Query the currently used model mode.

**Parameters**: None

**Example**:
```
<tool>agent_mode_status</tool>
```

### 3. `agent_mode_switch`

Switch to the specified model mode.

**Parameters**:
- `target` (string, required): Target model mode name or description keywords, such as 'coding', 'multimodal', 'code', 'multimodal', etc.

**Example**:
```
<tool>agent_mode_switch</tool>
<parameter name="target">coding</parameter>
```

## Configuration File

Model information is stored in `~/.nanobot/workspace/AGENTS.json` with the following format:

```json
{
  "modes": {
    "current_model": "common",
    "models": [
      {
        "name": "common",
        "model": "qwen3.5:cloud",
        "describe": "General mode, suitable for daily conversations and general tasks"
      },
      {
        "name": "coding",
        "model": "qwen3-coder-next:cloud",
        "describe": "Code mode, focused on programming, code generation, and technical issues"
      },
      {
        "name": "multimodal",
        "model": "kimi-k2.5",
        "describe": "Multimodal mode, supporting image, document, and other multimodal input processing"
      }
    ]
  }
}
```

## Usage

When users mention switching modes, viewing mode lists, or querying current modes, simply call the corresponding tools:

- "Switch to coding mode" → Call `agent_mode_switch`
- "What mode am I in now?" → Call `agent_mode_status`
- "What modes do you have?" → Call `agent_mode_list`

No need to overthink, just call the tools directly.
