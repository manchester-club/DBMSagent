#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama智能体配置

用于配置Ollama模型和参数
"""

import subprocess
import json


def get_available_models():
    """获取可用的Ollama模型列表"""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]  # 跳过标题行
            models = []
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if parts:
                        model_name = parts[0]
                        models.append(model_name)
            return models
    except Exception as e:
        print(f"获取模型列表失败: {e}")
    return []


def get_default_model() -> str:
    """获取默认模型"""
    models = get_available_models()
    
    # 优先级：qwen2.5:7b > qwen2.5 > qwen > 第一个可用模型
    preferred = ["qwen2.5:7b", "qwen2.5", "qwen", "llama3", "llama2"]
    
    for pref in preferred:
        for model in models:
            if pref in model.lower():
                return model
    
    if models:
        return models[0]
    
    return "qwen2.5:7b"  # 默认值，如果不存在会回退到规则匹配


if __name__ == "__main__":
    print("可用模型:")
    models = get_available_models()
    if models:
        for model in models:
            print(f"  - {model}")
    else:
        print("  未找到可用模型")
    
    print(f"\n默认模型: {get_default_model()}")



