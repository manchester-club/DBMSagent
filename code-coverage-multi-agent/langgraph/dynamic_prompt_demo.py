#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态提示（Dynamic Prompt）实现机制演示

展示如何使用 prompt 函数参数来实现动态系统提示，
基于运行时配置（RunnableConfig）来定制化 agent 的行为。
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama

# 定义工具函数
@tool
def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


# ============================================================================
# 动态提示实现机制详解
# ============================================================================

print("=" * 70)
print("动态提示（Dynamic Prompt）实现机制")
print("=" * 70)

print("""
1. prompt 参数的类型
   - 可以是字符串（静态提示）
   - 可以是函数（动态提示）
   - 函数签名: prompt(state: AgentState, config: RunnableConfig) -> list[AnyMessage]

2. prompt 函数的调用时机
   - 在每次模型调用之前
   - 每次都会传入当前的 state 和 config
   - 返回的消息列表会被添加到模型调用的上下文中

3. AgentState 结构
   - state["messages"]: 当前对话的消息列表
   - 包含所有历史消息（用户消息、AI回复、工具调用等）

4. RunnableConfig 结构
   - config["configurable"]: 可配置的参数字典
   - 可以在 invoke() 时通过 config 参数传入
   - 用于传递运行时配置（如用户信息、会话ID等）

5. 返回值的处理
   - 返回的消息列表会与 state["messages"] 合并
   - 系统消息通常放在最前面
   - 然后才是历史对话消息
""")

print("\n" + "=" * 70)
print("示例 1: 基础动态提示（基于用户名称）")
print("=" * 70)


def prompt_with_user_name(state: dict, config: RunnableConfig) -> list[AnyMessage]:
    """
    动态提示函数 - 根据配置中的用户名称定制系统提示
    
    Args:
        state: AgentState，包含 messages 等状态信息
        config: RunnableConfig，包含可配置参数
    
    Returns:
        消息列表，包含动态生成的系统消息
    """
    print("\n[DEBUG] prompt 函数被调用")
    print(f"  - state keys: {state.keys()}")
    print(f"  - state messages count: {len(state.get('messages', []))}")
    print(f"  - config type: {type(config)}")
    
    # 从 config 中获取用户名称（如果存在）
    user_name = None
    if config and "configurable" in config:
        user_name = config["configurable"].get("user_name")
        print(f"  - user_name from config: {user_name}")
    
    # 动态生成系统消息
    if user_name:
        system_content = f"You are a helpful assistant. Address the user as {user_name}."
    else:
        system_content = "You are a helpful assistant."
    
    print(f"  - 生成的系统消息: {system_content}")
    
    # 返回消息列表
    # 注意：这里返回的是消息对象，不是字典
    return [SystemMessage(content=system_content)]


# 创建模型
llm = ChatOllama(model="qwen3:32b", temperature=0.7)


class AgentWithDynamicPrompt:
    """包装器：在每次 invoke 前用 prompt 函数生成系统消息并注入 state。"""

    def __init__(self, base_agent, prompt_func):
        self._agent = base_agent
        self._prompt_fn = prompt_func

    def invoke(self, state, config=None):
        cfg = config or {}
        system_messages = self._prompt_fn(state, cfg)
        new_messages = system_messages + state.get("messages", [])
        new_state = {**state, "messages": new_messages}
        return self._agent.invoke(new_state, config=config)


# 创建带动态提示的 agent（create_agent 仅支持 str | SystemMessage | None，故用包装器）
_base1 = create_agent(model=llm, tools=[get_weather], system_prompt=None)
agent1 = AgentWithDynamicPrompt(_base1, prompt_with_user_name)

print("\n✅ Agent 创建成功（使用动态提示函数）")
print("\n测试 1: 不带用户名称配置")
print("-" * 70)

result1 = agent1.invoke(
    {"messages": [HumanMessage(content="what is the weather in sf")]}
)
print(f"回复: {result1['messages'][-1].content if result1.get('messages') else 'N/A'}")

print("\n测试 2: 带用户名称配置")
print("-" * 70)

result2 = agent1.invoke(
    {"messages": [HumanMessage(content="what is the weather in sf")]},
    config={"configurable": {"user_name": "John Smith"}}  # 传入配置
)
print(f"回复: {result2['messages'][-1].content if result2.get('messages') else 'N/A'}")


print("\n" + "=" * 70)
print("示例 2: 更复杂的动态提示（基于会话上下文）")
print("=" * 70)


def prompt_with_context(state: dict, config: RunnableConfig) -> list[AnyMessage]:
    """
    更复杂的动态提示 - 基于会话上下文和配置
    """
    # 获取配置参数
    user_name = config.get("configurable", {}).get("user_name", "User")
    language = config.get("configurable", {}).get("language", "English")
    session_id = config.get("configurable", {}).get("session_id", "default")
    
    # 分析当前对话历史
    messages = state.get("messages", [])
    message_count = len(messages)
    
    # 动态生成系统提示
    system_parts = [
        f"You are a helpful assistant.",
        f"Address the user as {user_name}.",
        f"Respond in {language}.",
        f"Current session: {session_id}.",
        f"Conversation has {message_count} messages so far."
    ]
    
    system_content = " ".join(system_parts)
    
    return [SystemMessage(content=system_content)]


_base2 = create_agent(model=llm, tools=[get_weather], system_prompt=None)
agent2 = AgentWithDynamicPrompt(_base2, prompt_with_context)

print("\n✅ Agent 创建成功（使用复杂动态提示）")

result3 = agent2.invoke(
    {"messages": [HumanMessage(content="Hello")]},
    config={
        "configurable": {
            "user_name": "Alice",
            "language": "Chinese",
            "session_id": "session_123"
        }
    }
)
print(f"回复: {result3['messages'][-1].content if result3.get('messages') else 'N/A'}")


print("\n" + "=" * 70)
print("示例 3: 动态提示的执行流程")
print("=" * 70)

print("""
当调用 agent.invoke() 时，执行流程如下：

1. 用户调用: agent.invoke(state, config)
   ↓
2. Agent 内部处理流程:
   a. 准备调用模型
   b. 检查是否有 prompt 函数（而不是字符串）
   c. 如果有 prompt 函数，调用它:
      prompt(state, config) -> list[AnyMessage]
   d. 将返回的消息添加到模型调用的上下文中
   e. 调用模型生成响应
   ↓
3. 模型收到:
   - 动态生成的系统消息（来自 prompt 函数）
   - 历史对话消息（来自 state["messages"]）
   - 工具定义（来自 bind_tools）
   ↓
4. 模型生成响应
   ↓
5. 返回结果

关键点：
- prompt 函数在每次模型调用前都会执行
- 可以访问完整的 state 和 config
- 返回的消息会与 state["messages"] 合并
- 系统消息通常放在最前面
""")


print("\n" + "=" * 70)
print("示例 4: 对比静态提示和动态提示")
print("=" * 70)

# 静态提示
agent_static = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt="You are a helpful assistant."  # 静态字符串
)

# 动态提示（通过包装器实现，因 create_agent 的 system_prompt 仅接受 str | SystemMessage | None）
_base_dyn = create_agent(model=llm, tools=[get_weather], system_prompt=None)
agent_dynamic = AgentWithDynamicPrompt(_base_dyn, prompt_with_user_name)

print("""
静态提示 vs 动态提示：

静态提示（字符串）:
- 固定不变
- 无法根据运行时信息调整
- 简单直接

动态提示（函数）:
- 可以根据 state 和 config 动态生成
- 可以访问对话历史
- 可以实现个性化、上下文感知
- 更灵活，适合复杂场景
""")


print("\n" + "=" * 70)
print("示例 5: 替代方案 - 在 invoke 时动态添加系统消息")
print("=" * 70)

# create_agent 的 system_prompt 仅接受 str | SystemMessage | None，故用 AgentWithDynamicPrompt 包装
base_agent = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt=None,
)
agent_wrapper = AgentWithDynamicPrompt(base_agent, prompt_with_user_name)

print("✅ 使用包装器方式实现动态提示")
print("\n这种方式的工作原理：")
print("""
1. 创建基础 agent（不使用系统提示）
2. 创建包装器函数，在每次调用时：
   - 调用 prompt 函数生成系统消息
   - 将系统消息添加到 messages 前面
   - 调用原始 agent
3. 这样可以在运行时动态生成系统提示
""")


print("\n" + "=" * 70)
print("总结")
print("=" * 70)
print("""
动态提示的实现机制：

1. **函数签名**:
   prompt(state: AgentState, config: RunnableConfig) -> list[AnyMessage]

2. **调用时机**:
   - 每次模型调用前
   - 在消息准备阶段

3. **参数说明**:
   - state: 包含当前对话状态（messages 等）
   - config: 包含运行时配置（configurable 字典）

4. **返回值**:
   - 返回消息列表（通常是 SystemMessage）
   - 这些消息会被添加到模型调用的上下文中

5. **使用场景**:
   - 个性化提示（基于用户信息）
   - 上下文感知提示（基于对话历史）
   - 多语言支持（基于语言配置）
   - 会话管理（基于会话ID）

6. **优势**:
   - 灵活性高
   - 可以实现复杂的定制化逻辑
   - 支持运行时配置
   - 可以访问完整的状态信息
""")
