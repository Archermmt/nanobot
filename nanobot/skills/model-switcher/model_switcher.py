#!/usr/bin/env python3
"""
Model Switcher - 切换和管理 nanobot 使用的 LLM 模型

Usage:
    python model_switcher.py list              # 列出所有可用模型
    python model_switcher.py current           # 查看当前模型
    python model_switcher.py switch <model>    # 切换到指定模型
"""

import json
import sys
from pathlib import Path

# 配置文件路径
MODELS_FILE = Path.home() / ".nanobot" / "workspace" / "models.json"


def load_models():
    """加载 models.json 文件"""
    if not MODELS_FILE.exists():
        print(f"错误：配置文件不存在：{MODELS_FILE}")
        sys.exit(1)

    with open(MODELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_models(data):
    """保存 models.json 文件"""
    with open(MODELS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def list_models():
    """列出所有可用模型"""
    data = load_models()
    current = data.get("current_model", "unknown")

    print("## 可用模型\n")
    print("| 模式 | 模型 | 描述 |")
    print("|------|------|------|")

    for model in data.get("models", []):
        name = model.get("name", "unknown")
        model_id = model.get("model", "unknown")
        desc = model.get("describe", "无描述")
        print(f"| {name} | {model_id} | {desc} |")

    current_model = next(
        (m for m in data.get("models", []) if m["name"] == current), None
    )
    if current_model:
        print(f"\n**当前使用**: {current} ({current_model['model']})")
    else:
        print(f"\n**当前使用**: {current} (模型未找到)")


def show_current():
    """显示当前使用的模型"""
    data = load_models()
    current = data.get("current_model", "unknown")

    current_model = next(
        (m for m in data.get("models", []) if m["name"] == current), None
    )
    if current_model:
        print(f"当前模型：{current} ({current_model['model']})")
        print(f"描述：{current_model.get('describe', '无描述')}")
    else:
        print(f"当前模型：{current} (模型未找到)")


def switch_model(target):
    """切换到指定模型"""
    data = load_models()
    models = data.get("models", [])

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
            "common": ["日常", "聊天", "通用", "default", "normal", "普通"],
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
                        match_scores[model["name"]] += 0.5  # 描述中的关键词权重较低

        # 选择得分最高的模型
        best_score = 0
        for model_name, score in match_scores.items():
            if score > best_score:
                best_score = score
                matched = model_name

    # 如果还是没有匹配，使用第一个模型作为默认
    if not matched and models:
        matched = models[0]["name"]
        print(f"未找到匹配的模型，使用默认模型：{matched}")

    if not matched:
        print(f"错误：找不到模型 '{target}'")
        sys.exit(1)

    # 更新当前模型
    old_current = data.get("current_model", "unknown")
    data["current_model"] = matched
    save_models(data)

    matched_model = next((m for m in models if m["name"] == matched), None)
    print(f"✓ 模型已切换：{old_current} → {matched}")
    print(f"  模型：{matched_model['model']}")
    print(f"  描述：{matched_model.get('describe', '无描述')}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        list_models()
    elif command == "current":
        show_current()
    elif command == "switch":
        if len(sys.argv) < 3:
            print("错误：请指定要切换的模型名称或描述")
            print("用法：python model_switcher.py switch <model>")
            sys.exit(1)
        target = " ".join(sys.argv[2:])
        switch_model(target)
    else:
        print(f"未知命令：{command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
