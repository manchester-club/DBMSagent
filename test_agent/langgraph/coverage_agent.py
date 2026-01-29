#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coverage Agent - 基于 LangGraph 的覆盖率测试 Agent

使用 LangGraph 框架实现，支持以下工具：
1. Run_SQL_Test - 执行SQL测试
2. Collect_Coverage - 收集函数覆盖率
3. Get_Code_Context - 获取源代码上下文
4. Search_Nearest_Seed - 查找SQL种子
5. Traverse_Call_Graph - 遍历调用图
"""

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, ToolMessage
from langchain_core.runnables import RunnableConfig
from typing import Annotated, List
from typing_extensions import TypedDict
import os
import json

# 导入自定义工具节点（从 nodes 文件夹）
from nodes import (
    Run_SQL_Test,
    Collect_Coverage,
    Get_Code_Context,
    Search_Nearest_Seed,
    Traverse_Call_Graph
)

# 创建记忆保存器
memory = MemorySaver()

class State(TypedDict):
    messages: Annotated[List, add_messages]

# 创建 Ollama 模型实例
llm = ChatOllama(model="qwen3:32b", temperature=0.7)

# 创建状态图构建器
graph_builder = StateGraph(State)

# 绑定工具到模型
tools = [
    Run_SQL_Test,
    Collect_Coverage,
    Get_Code_Context,
    Search_Nearest_Seed,
    Traverse_Call_Graph
]
llm_with_tools = llm.bind_tools(tools)

# 定义 chatbot 节点函数（流式版本）
def chatbot(state: State) -> State:
    """
    使用 Ollama 模型处理消息的节点（流式输出）
    
    Args:
        state: 当前状态，包含 messages 字段
    
    Returns:
        包含 AI 回复消息的新状态
    """
    # 获取当前的消息列表
    messages = state["messages"]
    
    # 使用流式调用，边生成边输出
    # 累积所有 chunk 来构建完整的消息
    accumulated_chunk = None
    has_content = False
    
    # 流式调用模型（使用绑定工具的模型）
    try:
        for chunk in llm_with_tools.stream(messages):  # type: ignore
            # 累积 chunk（AIMessageChunk 支持 + 操作符）
            if accumulated_chunk is None:
                accumulated_chunk = chunk
            else:
                accumulated_chunk = accumulated_chunk + chunk
            
            # 提取并输出增量内容
            if hasattr(chunk, 'content') and chunk.content:
                content = chunk.content
                if isinstance(content, str) and content:
                    if not has_content:
                        print("Assistant: ", end="", flush=True)
                        has_content = True
                    print(content, end="", flush=True)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, str) and item:
                            if not has_content:
                                print("Assistant: ", end="", flush=True)
                                has_content = True
                            print(item, end="", flush=True)
        
        if has_content:
            print()  # 最后换行
    except Exception as e:
        print(f"\n[ERROR] 流式调用出错: {e}", flush=True)
        import traceback
        traceback.print_exc()
        # 如果流式失败，回退到普通调用
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}
    
    # 将累积的 chunk 转换为完整的 AIMessage
    if accumulated_chunk:
        # AIMessageChunk 可以转换为 AIMessage
        if isinstance(accumulated_chunk, AIMessageChunk):
            # 创建完整的 AIMessage，保留所有属性
            response = AIMessage(
                content=accumulated_chunk.content if hasattr(accumulated_chunk, 'content') else "",
                tool_calls=getattr(accumulated_chunk, 'tool_calls', None),
                id=getattr(accumulated_chunk, 'id', None),
            )
        elif isinstance(accumulated_chunk, AIMessage):
            response = accumulated_chunk
        else:
            # 回退：创建新的 AIMessage
            response = AIMessage(content="")
    else:
        # 如果没有 chunk，创建空消息
        response = AIMessage(content="")
    
    # 输出工具调用信息
    if hasattr(response, 'tool_calls') and response.tool_calls:
        print("\n[工具调用]", flush=True)
        for i, tool_call in enumerate(response.tool_calls, 1):
            print(f"  {i}. 工具名称: {tool_call.get('name', 'unknown')}", flush=True)
            print(f"     参数: {json.dumps(tool_call.get('args', {}), ensure_ascii=False, indent=6)}", flush=True)
            if 'id' in tool_call:
                print(f"     调用ID: {tool_call['id']}", flush=True)
        print()
    
    # 返回新状态，包含 AI 的回复
    # add_messages 归约器会自动将新消息追加到现有消息列表
    return {"messages": [response]}

# 添加节点到图中
graph_builder.add_node("chatbot", chatbot)

# 使用预构建的 ToolNode（它会自动处理工具调用）
tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)

# 使用预构建的 tools_condition 进行条件路由
# tools_condition 返回 "__end__" 或 "tools"
graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
    {
        "tools": "tools",
        "__end__": END,
    },
)

# 工具调用后返回到 chatbot 节点继续处理
graph_builder.add_edge("tools", "chatbot")

# 设置入口点
graph_builder.add_edge(START, "chatbot")

# 编译图，传入 checkpointer 以启用记忆功能
app = graph_builder.compile(checkpointer=memory)

# 交互式聊天循环
def stream_graph_updates(user_input: str, thread_id: str = "default"):
    """流式处理用户输入并显示 AI 回复"""
    # 直接调用 app.invoke，流式输出在节点内部处理
    # 传入 config 以使用记忆功能
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    try:
        app.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
        )
    except Exception as e:
        print(f"\n[ERROR] 执行出错: {e}", flush=True)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 使用固定的 thread_id 来保持对话记忆
    thread_id = "coverage_agent_session_1"
    
    print("=" * 60)
    print("Coverage Agent - 基于 LangGraph 的覆盖率测试 Agent")
    print("=" * 60)
    print("\n可用工具：")
    print("  1. Run_SQL_Test - 执行SQL测试")
    print("  2. Collect_Coverage - 收集函数覆盖率")
    print("  3. Get_Code_Context - 获取源代码上下文")
    print("  4. Search_Nearest_Seed - 查找SQL种子")
    print("  5. Traverse_Call_Graph - 遍历调用图")
    print("\n输入 'quit' 或 'exit' 或 'q' 退出\n")
    
    while True:
        try:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            stream_graph_updates(user_input, thread_id=thread_id)
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception:
            # fallback if input() is not available
            user_input = "请帮我查找函数 date_pli 的代码上下文"
            print("User: " + user_input)
            stream_graph_updates(user_input, thread_id=thread_id)
            break
