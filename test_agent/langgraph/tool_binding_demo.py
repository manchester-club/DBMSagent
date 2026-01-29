#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具绑定机制演示 - 展示工具参数和描述如何传递给模型

这个示例详细展示了：
1. 工具对象的内部结构
2. 工具如何被转换为模型可以理解的格式
3. 工具描述如何嵌入到系统提示中
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
import json

# 定义几个示例工具
@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气信息。
    
    Args:
        city: 城市名称，例如 '北京'、'上海'、'San Francisco'
    
    Returns:
        该城市的天气描述
    """
    return f"{city} 的天气总是阳光明媚！"


@tool
def calculate(expression: str) -> str:
    """计算数学表达式。
    
    Args:
        expression: 要计算的数学表达式，例如 '2 + 2' 或 '10 * 5'
    
    Returns:
        计算结果
    """
    try:
        result = eval(expression)
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"


@tool
def search_database(query: str, limit: int = 10) -> str:
    """在数据库中搜索信息。
    
    Args:
        query: 搜索关键词
        limit: 返回结果的最大数量，默认为 10
    
    Returns:
        搜索结果
    """
    return f"搜索 '{query}' 的结果（限制 {limit} 条）"


def print_tool_info(tool_obj):
    """打印工具的详细信息"""
    print("=" * 70)
    print(f"工具名称: {tool_obj.name}")
    print(f"工具描述: {tool_obj.description}")
    print(f"工具参数模式: {tool_obj.args_schema}")
    if tool_obj.args_schema:
        print(f"参数字段:")
        if hasattr(tool_obj.args_schema, 'schema'):
            schema = tool_obj.args_schema.schema()
            print(json.dumps(schema, ensure_ascii=False, indent=2))
    print("=" * 70)


def demonstrate_tool_binding():
    """演示工具绑定过程"""
    print("\n" + "=" * 70)
    print("📋 第一步：查看工具对象的原始信息")
    print("=" * 70)
    
    tools = [get_weather, calculate, search_database]
    
    for tool_obj in tools:
        print_tool_info(tool_obj)
        print()
    
    print("\n" + "=" * 70)
    print("📋 第二步：查看工具如何被转换为模型可理解的格式")
    print("=" * 70)
    
    # 创建模型实例
    llm = ChatOllama(model="qwen3:32b", temperature=0.7)
    
    # 绑定工具到模型 - 这一步会将工具转换为模型可以理解的格式
    llm_with_tools = llm.bind_tools(tools)
    
    print("\n🔍 工具绑定后的格式（通过 inspect_tools 查看）:")
    print("-" * 70)
    
    # 查看绑定后的工具信息
    if hasattr(llm_with_tools, 'bound_tools'):
        print("绑定工具列表:", llm_with_tools.bound_tools)
    
    # 尝试获取工具的结构化描述
    print("\n📝 工具的结构化描述（JSON Schema 格式）:")
    for tool_obj in tools:
        if hasattr(tool_obj, 'args_schema') and tool_obj.args_schema:
            schema = tool_obj.args_schema.schema()
            tool_schema = {
                "name": tool_obj.name,
                "description": tool_obj.description,
                "parameters": schema
            }
            print(f"\n工具: {tool_obj.name}")
            print(json.dumps(tool_schema, ensure_ascii=False, indent=2))
    
    print("\n" + "=" * 70)
    print("📋 第三步：查看实际传递给模型的消息格式")
    print("=" * 70)
    
    # 创建一个测试消息来查看工具是如何被包含的
    from langchain_core.messages import HumanMessage
    
    test_message = HumanMessage(content="你好，你可以使用哪些工具？")
    messages = [test_message]
    
    print("\n原始消息:")
    print(f"  {test_message}")
    
    print("\n当模型处理消息时，工具信息会被包含在:")
    print("  1. 系统提示中（工具描述）")
    print("  2. 模型调用时的工具绑定信息中")
    print("  3. 模型响应的 tool_calls 字段中（如果决定调用工具）")
    
    print("\n" + "=" * 70)
    print("📋 第四步：使用 create_agent 查看完整流程")
    print("=" * 70)
    
    # 创建 agent
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="你是一个有用的助手，可以使用以下工具来帮助用户。"
    )
    
    print("\n✅ Agent 已创建，工具信息已嵌入到 agent 的工作流中")
    print("\n工具信息传递流程:")
    print("  1. @tool 装饰器提取函数签名和文档字符串")
    print("  2. 工具对象包含 name, description, args_schema")
    print("  3. create_agent 内部调用 model.bind_tools(tools)")
    print("  4. 工具信息被转换为 JSON Schema 格式")
    print("  5. 工具描述被添加到系统提示或模型上下文中")
    print("  6. 模型在生成响应时可以看到所有可用工具")
    print("  7. 模型决定调用工具时，会在 tool_calls 中指定工具名和参数")
    
    return agent


def test_agent_with_tool_inspection():
    """测试 agent 并展示工具调用过程"""
    print("\n" + "=" * 70)
    print("🧪 测试：让 agent 列出可用工具")
    print("=" * 70)
    
    tools = [get_weather, calculate, search_database]
    llm = ChatOllama(model="qwen3:32b", temperature=0.7)
    
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="你是一个有用的助手。当用户询问可用工具时，请详细说明每个工具的名称、描述和参数。"
    )
    
    result = agent.invoke({
        "messages": [{"role": "user", "content": "你现在可以使用的工具有哪些？请详细说明每个工具的名称、描述和参数。"}]
    })
    
    print("\n🤖 Agent 回复:")
    print("-" * 70)
    if "messages" in result:
        for msg in result["messages"]:
            if hasattr(msg, 'content') and msg.content:
                print(msg.content)
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                print(f"\n[调用了工具: {msg.tool_calls}]")


if __name__ == "__main__":
    print("🔍 工具绑定机制深度解析")
    print("=" * 70)
    
    # 演示工具绑定过程
    agent = demonstrate_tool_binding()
    
    # 测试 agent
    test_agent_with_tool_inspection()
    
    print("\n" + "=" * 70)
    print("💡 总结")
    print("=" * 70)
    print("""
工具信息传递给模型的机制：

1. **工具定义阶段**：
   - @tool 装饰器解析函数签名（参数名、类型）
   - 提取文档字符串作为工具描述
   - 生成 args_schema（Pydantic 模型）

2. **工具绑定阶段**：
   - model.bind_tools(tools) 将工具转换为模型可理解的格式
   - 工具信息被序列化为 JSON Schema
   - 包含：工具名、描述、参数定义（类型、必需性、描述）

3. **模型调用阶段**：
   - 工具信息被包含在系统提示或模型上下文中
   - 模型可以看到所有可用工具及其参数
   - 模型根据用户查询决定是否调用工具

4. **工具调用阶段**：
   - 模型在响应中生成 tool_calls
   - 包含：工具名、参数值、调用ID
   - Agent 执行工具并返回结果给模型

5. **结果处理阶段**：
   - 工具执行结果作为 ToolMessage 返回
   - 模型基于工具结果生成最终回复
    """)
