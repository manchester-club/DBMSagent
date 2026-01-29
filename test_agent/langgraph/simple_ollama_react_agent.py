#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的 LangGraph ReAct Agent 示例 - 使用 Ollama

这是对原始代码的最小修改版本，将 Anthropic 模型替换为本地 Ollama。
包含静态提示和动态提示两种示例。
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver

# 定义工具函数
@tool
def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"

# 创建 Ollama 模型实例
llm = ChatOllama(model="qwen3:32b", temperature=0.7)

# ============================================================================
# 示例 1: 静态提示（字符串）
# ============================================================================
agent_static = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt="You are a helpful assistant"  # 静态字符串提示
)

# ============================================================================
# 示例 2: 动态提示（函数）
# ============================================================================
def prompt(state: dict, config: RunnableConfig) -> list[AnyMessage]:
    """
    动态提示函数
    
    这个函数在每次模型调用前都会被调用，用于动态生成系统提示。
    
    参数:
        state: AgentState，包含当前对话状态
            - state["messages"]: 当前对话的消息列表
        config: RunnableConfig，包含运行时配置
            - config["configurable"]: 可配置参数字典，可以在 invoke() 时传入
    
    返回:
        list[AnyMessage]: 消息列表，通常是包含系统消息的列表
    """
    # 从 config 中获取用户名称（如果存在）
    user_name = config.get("configurable", {}).get("user_name")
    
    # 动态生成系统消息
    if user_name:
        system_content = f"You are a helpful assistant. Address the user as {user_name}."
    else:
        system_content = "You are a helpful assistant."
    
    # 返回系统消息列表
    # 注意：返回的是消息对象（SystemMessage），不是字典
    return [SystemMessage(content=system_content)]

# 创建带动态提示的 agent
# 注意：create_agent 的 system_prompt 参数理论上只接受字符串或 SystemMessage
# 但某些版本可能支持函数，如果运行时报错，需要使用其他方式实现动态提示
# 例如：在 invoke 时动态修改 messages，或使用自定义的 agent 构建方式
agent_dynamic = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt=prompt  # type: ignore  # 传入函数而不是字符串
)

# ============================================================================
# 示例 3: 使用 checkpointer 实现记忆
# ============================================================================

# 创建 checkpointer（检查点保存器）
# InMemorySaver 将状态保存在内存中，用于维护对话记忆
checkpointer = InMemorySaver()

# 创建带记忆的 agent
agent_with_memory = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
    checkpointer=checkpointer  # 传入 checkpointer 以启用记忆功能
)

# ============================================================================
# 运行示例
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("示例 1: 静态提示")
    print("=" * 70)
    
    result1 = agent_static.invoke(
        {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
    )
    
    if "messages" in result1:
        last_message = result1["messages"][-1]
        if hasattr(last_message, 'content'):
            print(f"Agent 回复: {last_message.content}")
    
    print("\n" + "=" * 70)
    print("示例 2: 动态提示（不带用户名称）")
    print("=" * 70)
    
    result2 = agent_dynamic.invoke(
        {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
    )
    
    if "messages" in result2:
        last_message = result2["messages"][-1]
        if hasattr(last_message, 'content'):
            print(f"Agent 回复: {last_message.content}")
    
    print("\n" + "=" * 70)
    print("示例 3: 动态提示（带用户名称配置）")
    print("=" * 70)
    
    # 通过 config 参数传入用户名称
    result3 = agent_dynamic.invoke(
        {"messages": [{"role": "user", "content": "what is the weather in sf"}]},
        config={"configurable": {"user_name": "John Smith"}}  # 传入配置
    )
    
    if "messages" in result3:
        last_message = result3["messages"][-1]
        if hasattr(last_message, 'content'):
            print(f"Agent 回复: {last_message.content}")
    
    print("\n" + "=" * 70)
    print("动态提示机制说明")
    print("=" * 70)
    print("""
动态提示的工作原理（基于 create_react_agent 的 prompt 参数）：

1. prompt 参数可以是函数，而不是字符串
   - 在 create_react_agent 中，prompt 参数支持函数
   - 在 create_agent 中，system_prompt 参数可能不支持函数（需要验证）

2. 函数签名: prompt(state: dict, config: RunnableConfig) -> list[AnyMessage]
   - state: 包含当前对话状态（messages 等）
   - config: 包含运行时配置，可以通过 invoke() 的 config 参数传入
   - 返回: 消息列表（通常是 SystemMessage）

3. 调用时机: 每次模型调用前，agent 会调用这个函数

4. 执行流程：
     agent.invoke(state, config)
       ↓
     Agent 准备调用模型
       ↓
     调用 prompt(state, config) 生成系统消息
       ↓
     将系统消息添加到模型调用的上下文
       ↓
     调用模型生成响应
       ↓
     返回结果

5. 如果 create_agent 不支持函数形式的 system_prompt，替代方案：
   - 在 invoke 时手动添加 SystemMessage 到 messages
   - 使用自定义的 agent 构建方式
   - 使用 create_react_agent（已弃用但可能仍可用）

注意：当前代码中的动态提示示例可能需要根据实际 API 调整。
详细示例请参考 dynamic_prompt_demo.py
""")
    
    print("\n" + "=" * 70)
    print("示例 4: 使用 checkpointer 实现对话记忆")
    print("=" * 70)
    
    # 使用相同的 thread_id 来维护对话上下文
    config = {"configurable": {"thread_id": "1"}}
    
    print("\n第一次调用（询问 SF 天气）:")
    sf_response = agent_with_memory.invoke(
        {"messages": [{"role": "user", "content": "what is the weather in sf"}]},
        config  # type: ignore  # 指定 thread_id
    )
    if sf_response.get("messages"):
        print(f"Agent: {sf_response['messages'][-1].content}")
        print(f"✅ 状态已保存（thread_id: 1）")
    
    print("\n第二次调用（询问 NY 天气，使用相同的 thread_id）:")
    ny_response = agent_with_memory.invoke(
        {"messages": [{"role": "user", "content": "what about new york?"}]},
        config  # type: ignore  # 使用相同的 thread_id，会恢复之前的对话状态
    )
    if ny_response.get("messages"):
        print(f"Agent: {ny_response['messages'][-1].content}")
        print(f"✅ Agent 记住了之前的对话！")
        print(f"   总消息数: {len(ny_response['messages'])}（包括之前的对话）")
    
    print("\n" + "=" * 70)
    print("记忆机制说明")
    print("=" * 70)
    print("""
Checkpointer（检查点保存器）的作用：

1. **什么是 checkpointer？**
   - 用于保存和恢复 agent 的状态
   - 实现对话的连续性和记忆功能

2. **InMemorySaver：**
   - 内存中的检查点保存器
   - 将状态保存在内存中（程序重启后丢失）
   - 适合开发、测试和短期会话

3. **thread_id 的作用：**
   - 用于区分不同的对话线程/会话
   - 同一个 thread_id 的调用会共享状态
   - 不同的 thread_id 对应不同的对话上下文

4. **工作流程：**
   a. 创建 checkpointer: checkpointer = InMemorySaver()
   b. 创建 agent 时传入: create_agent(..., checkpointer=checkpointer)
   c. 调用时指定 thread_id: config = {"configurable": {"thread_id": "1"}}
   d. Agent 自动保存和恢复状态

5. **状态保存和恢复：**
   - 每次调用后，agent 自动保存状态到 checkpointer
   - 下次调用时，使用相同的 thread_id 会恢复之前的状态
   - 状态包括：messages、工具调用历史等

6. **使用场景：**
   - 多轮对话：维护对话上下文
   - 多用户系统：每个用户一个 thread_id
   - 会话管理：区分不同的对话会话

详细示例请参考 memory_checkpoint_demo.py
""")
