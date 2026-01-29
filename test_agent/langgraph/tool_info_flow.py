#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具信息流向演示 - 展示工具参数和描述如何传递给模型

这个脚本详细展示了工具信息从定义到传递给模型的完整流程。
"""

from langchain_core.tools import tool
from langchain_ollama import ChatOllama
import json

# 步骤1: 定义工具
print("=" * 70)
print("步骤 1: 工具定义")
print("=" * 70)

@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """获取指定城市的天气信息。
    
    Args:
        city: 城市名称，例如 '北京'、'上海'
        unit: 温度单位，'celsius' 或 'fahrenheit'，默认为 'celsius'
    
    Returns:
        该城市的天气描述
    """
    return f"{city} 的天气是 25 度 ({unit})"

print("✅ 工具已定义")
print(f"   函数名: get_weather")
print(f"   参数: city (str), unit (str, 默认='celsius')")
print(f"   文档字符串: {get_weather.__doc__}")
print()

# 步骤2: @tool 装饰器提取的信息
print("=" * 70)
print("步骤 2: @tool 装饰器提取的信息")
print("=" * 70)

print(f"工具名称 (name): {get_weather.name}")
print(f"工具描述 (description): {get_weather.description}")
print(f"参数模式 (args_schema): {get_weather.args_schema}")
print()

if get_weather.args_schema:
    schema = get_weather.args_schema.schema()
    print("参数模式详情 (JSON Schema 格式):")
    print(json.dumps(schema, ensure_ascii=False, indent=2))
print()

# 步骤3: 工具信息如何被转换为模型可理解的格式
print("=" * 70)
print("步骤 3: 工具绑定到模型")
print("=" * 70)

llm = ChatOllama(model="qwen3:32b", temperature=0.7)

# bind_tools 会将工具转换为模型可以理解的格式
print("调用 llm.bind_tools([get_weather])...")
llm_with_tools = llm.bind_tools([get_weather])

print("✅ 工具已绑定到模型")
print()
print("工具信息现在以以下格式传递给模型:")
print("""
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "获取指定城市的天气信息。",
    "parameters": {
      "type": "object",
      "properties": {
        "city": {
          "type": "string",
          "description": "城市名称，例如 '北京'、'上海'"
        },
        "unit": {
          "type": "string",
          "description": "温度单位，'celsius' 或 'fahrenheit'，默认为 'celsius'",
          "default": "celsius"
        }
      },
      "required": ["city"]
    }
  }
}
""")
print()

# 步骤4: 展示实际的消息格式
print("=" * 70)
print("步骤 4: 模型调用时的消息格式")
print("=" * 70)

from langchain_core.messages import HumanMessage, SystemMessage

# 系统消息（包含工具信息）
system_msg = SystemMessage(content="你是一个有用的助手。你可以使用工具来获取信息。")
# 用户消息
user_msg = HumanMessage(content="北京天气怎么样？")

print("发送给模型的消息序列:")
print(f"1. SystemMessage: {system_msg.content}")
print(f"2. HumanMessage: {user_msg.content}")
print()
print("工具信息会被包含在:")
print("  - 模型的工具绑定信息中（通过 bind_tools）")
print("  - 或者作为系统提示的一部分")
print()

# 步骤5: 模型如何决定调用工具
print("=" * 70)
print("步骤 5: 模型如何决定调用工具")
print("=" * 70)

print("""
当模型看到用户查询 "北京天气怎么样？" 时：

1. 模型分析查询，识别需要获取天气信息
2. 模型查看可用工具列表，找到 get_weather 工具
3. 模型查看工具描述和参数：
   - 工具名: get_weather
   - 描述: 获取指定城市的天气信息
   - 参数: city (必需), unit (可选)
4. 模型决定调用工具，生成 tool_calls:
   {
     "name": "get_weather",
     "arguments": {"city": "北京"}
   }
5. Agent 执行工具，返回结果
6. 模型基于工具结果生成最终回复
""")

# 步骤6: 实际测试
print("=" * 70)
print("步骤 6: 实际测试（可选）")
print("=" * 70)

print("""
要查看实际运行效果，可以：

1. 使用 create_agent 创建 agent
2. 调用 agent.invoke() 并观察：
   - 模型如何识别需要调用工具
   - tool_calls 的格式
   - 工具执行后的结果
   - 模型的最终回复

运行 simple_ollama_react_agent.py 可以看到完整流程。
""")

print("\n" + "=" * 70)
print("总结")
print("=" * 70)
print("""
工具信息传递流程：

1. 函数定义 + @tool 装饰器
   ↓
2. 工具对象 (name, description, args_schema)
   ↓
3. model.bind_tools(tools) 或 create_agent(tools=...)
   ↓
4. 工具信息转换为 JSON Schema 格式
   ↓
5. 工具信息包含在模型上下文中
   ↓
6. 模型可以看到工具列表、描述、参数
   ↓
7. 模型决定调用工具时生成 tool_calls
   ↓
8. Agent 执行工具并返回结果
   ↓
9. 模型基于结果生成最终回复
""")
