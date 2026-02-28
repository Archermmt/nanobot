---
name: model-switcher
description: 切换和管理 nanobot 使用的 LLM 模型。
metadata: {"nanobot":{"emoji":"🔄"}}
---

# Model Switcher

切换和管理 nanobot 使用的 LLM 模型。

## 功能

- 查看当前可用的模型列表
- 切换到指定的模型
- 查看当前使用的模型
- 支持通过模型描述进行智能切换

## 配置文件

模型信息存储在 `~/.nanobot/workspace/models.json` 中，格式如下：

```json
{
  "current_model": "common",
  "models": [
    {
      "name": "common",
      "model": "qwen3.5:cloud",
      "describe": "常规模式，适用于日常对话和通用任务"
    },
    {
      "name": "coding",
      "model": "qwen3-coder-next:cloud",
      "describe": "代码模式，专注于编程、代码生成和技术问题"
    },
    {
      "name": "multimodal",
      "model": "kimi-k2.5",
      "describe": "多模态模式，支持图像、文档等多模态输入处理"
    }
  ]
}
```

## 使用方法

### 查看可用模型列表

```bash
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py list
```

输出示例：
```markdown
## 可用模型

| 模式 | 模型 | 描述 |
|------|------|------|
| common | qwen3.5:cloud | 常规模式，适用于日常对话和通用任务 |
| coding | qwen3-coder-next:cloud | 代码模式，专注于编程、代码生成和技术问题 |
| multimodal | kimi-k2.5 | 多模态模式，支持图像、文档等多模态输入处理 |

**当前使用**: common (qwen3.5:cloud)
```

### 切换到指定模型

```bash
# 通过模型名称切换
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py switch coding

# 通过描述关键词切换（智能匹配）
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py switch "我要写代码"
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py switch "处理图片"
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py switch "日常聊天"
```

### 查看当前模型

```bash
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py current
```

输出示例：
```
当前模型：common (qwen3.5:cloud)
描述：常规模式，适用于日常对话和通用任务
```

## 智能切换逻辑

当使用描述性语言切换时，系统会根据关键词自动匹配最合适的模型：

| 关键词 | 匹配模式 |
|--------|----------|
| 代码、编程、开发、debug、函数、类 | coding |
| 图片、图像、多模态、OCR、文档、PDF | multimodal |
| 其他（默认） | common |

## 添加新模型

编辑 `~/.nanobot/workspace/models.json` 文件，在 `models` 数组中添加新模型：

```json
{
  "name": "your-mode-name",
  "model": "your-model-id",
  "describe": "模型描述"
}
```

然后更新 `current_model` 字段（如果需要）。

## 注意事项

1. **模型可用性**: 确保切换的模型已在你的 LLM 提供商处配置并可访问
2. **配置生效**: 切换模型后，后续的 `provider.chat` 调用将使用新模型
3. **持久化**: 模型选择会持久化保存在 `models.json` 中，重启后依然有效
4. **智能匹配**: 使用描述切换时，匹配基于关键词，可能不够精确，建议直接用模型名称

## 故障排除

### 错误：模型不存在
```
Error: Model 'xxx' not found in models.json
```
**解决**: 使用 `summarize model-switcher list` 查看可用模型名称

### 错误：配置文件损坏
```
Error: Failed to parse models.json
```
**解决**: 检查 JSON 格式是否正确，或重新创建配置文件

## 示例场景

```bash
# 准备写代码，切换到代码模式
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py switch coding

# 需要处理图片，切换到多模态模式
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py switch "帮我分析这张图片"

# 日常聊天，切换回常规模式
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py switch common

# 查看还有哪些模型可用
python ~/.nanobot/workspace/skills/model-switcher/model_switcher.py list
```

## 技术实现

切换模型的核心逻辑由 Python 脚本 `model_switcher.py` 实现：

1. **配置文件管理**: 读取和写入 `models.json` 配置文件
2. **命令解析**: 支持 `list`、`current`、`switch` 三个命令
3. **智能匹配**: 使用关键词匹配算法，根据用户描述自动选择最合适的模型
4. **持久化存储**: 模型选择保存在 `models.json` 中，重启后依然有效
5. **错误处理**: 完善的错误提示和默认值处理

### 智能匹配算法

当使用描述性语言切换时，系统会：
1. 首先尝试精确匹配模型名称
2. 如果失败，根据预定义的关键词映射表计算每个模型的匹配得分
3. 选择得分最高的模型
4. 如果所有匹配都失败，使用第一个模型作为默认值

关键词映射：
- **coding**: 代码、编程、开发、debug、函数、类等
- **multimodal**: 图片、图像、多模态、OCR、文档、PDF 等
- **common**: 日常、聊天、通用等
