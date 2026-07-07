#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph 记忆机制（Checkpoint/Memory）演示

展示如何使用 checkpointer 来维护对话状态和记忆。
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver

# 定义工具函数
@tool
def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


# ============================================================================
# 记忆机制详解
# ============================================================================

print("=" * 70)
print("LangGraph 记忆机制（Checkpoint/Memory）详解")
print("=" * 70)

print("""
1. 什么是 Checkpointer（检查点保存器）？
   - Checkpointer 用于保存和恢复 agent 的状态
   - 它会在每次调用后保存对话状态（messages、中间结果等）
   - 下次调用时可以从保存的状态恢复，实现对话连续性

2. InMemorySaver 的作用：
   - 内存中的检查点保存器
   - 将状态保存在内存中（程序重启后丢失）
   - 适合开发、测试和短期会话

3. thread_id 的作用：
   - 用于区分不同的对话线程/会话
   - 同一个 thread_id 的调用会共享状态
   - 不同的 thread_id 对应不同的对话上下文

4. 工作流程：
   a. 创建 checkpointer
   b. 创建 agent 时传入 checkpointer
   c. 调用时指定 thread_id
   d. Agent 自动保存和恢复状态
""")

# 创建模型
llm = ChatOllama(model="qwen3:32b", temperature=0.7)

# ============================================================================
# 示例 1: 不使用 checkpointer（无记忆）
# ============================================================================

print("\n" + "=" * 70)
print("示例 1: 不使用 checkpointer（无记忆）")
print("=" * 70)

agent_no_memory = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt="You are a helpful assistant"
)

print("\n第一次调用:")
result1 = agent_no_memory.invoke(
    {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
)
if result1.get("messages"):
    print(f"回复: {result1['messages'][-1].content}")

print("\n第二次调用（询问 'what about new york?'）:")
result2 = agent_no_memory.invoke(
    {"messages": [{"role": "user", "content": "what about new york?"}]}
)
if result2.get("messages"):
    print(f"回复: {result2['messages'][-1].content}")
    print("\n⚠️  注意：Agent 不知道之前问过 SF，因为没有记忆！")

# ============================================================================
# 示例 2: 使用 checkpointer（有记忆）
# ============================================================================

print("\n" + "=" * 70)
print("示例 2: 使用 checkpointer（有记忆）")
print("=" * 70)

# 创建 checkpointer
checkpointer = InMemorySaver()

print("\n✅ 创建 InMemorySaver checkpointer")
print("   - 类型: 内存检查点保存器")
print("   - 存储位置: 内存（程序重启后丢失）")
print("   - 用途: 维护对话状态和记忆")

# 创建带 checkpointer 的 agent
agent_with_memory = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
    checkpointer=checkpointer  # 传入 checkpointer
)

print("\n✅ Agent 创建成功（带 checkpointer）")

# 使用相同的 thread_id 来维护对话上下文
config = {"configurable": {"thread_id": "conversation_1"}}

print("\n" + "-" * 70)
print("第一次调用（thread_id: conversation_1）")
print("-" * 70)
print("用户: what is the weather in sf")

sf_response = agent_with_memory.invoke(
    {"messages": [{"role": "user", "content": "what is the weather in sf"}]},
    config  # type: ignore  # 指定 thread_id
)

if sf_response.get("messages"):
    print(f"Agent: {sf_response['messages'][-1].content}")
    print(f"\n📝 状态已保存到 checkpointer（thread_id: conversation_1）")
    print(f"   保存的消息数: {len(sf_response['messages'])}")

print("\n" + "-" * 70)
print("第二次调用（相同的 thread_id: conversation_1）")
print("-" * 70)
print("用户: what about new york?")

ny_response = agent_with_memory.invoke(
    {"messages": [{"role": "user", "content": "what about new york?"}]},
    config  # type: ignore  # 使用相同的 thread_id，会恢复之前的对话状态
)

if ny_response.get("messages"):
    print(f"Agent: {ny_response['messages'][-1].content}")
    print(f"\n✅ Agent 记住了之前的对话！")
    print(f"   总消息数: {len(ny_response['messages'])}")
    print(f"   （包括之前关于 SF 的对话）")

# ============================================================================
# 示例 3: 不同 thread_id 的独立对话
# ============================================================================

print("\n" + "=" * 70)
print("示例 3: 不同 thread_id 的独立对话")
print("=" * 70)

print("\n创建新的对话线程（thread_id: conversation_2）")
config2 = {"configurable": {"thread_id": "conversation_2"}}

result3 = agent_with_memory.invoke(
    {"messages": [{"role": "user", "content": "Hello, I'm a new user"}]},
    config2  # type: ignore
)

if result3.get("messages"):
    print(f"Agent: {result3['messages'][-1].content}")
    print(f"\n✅ 新对话线程创建成功")
    print(f"   - conversation_1: 包含 SF 和 NY 的对话")
    print(f"   - conversation_2: 全新的对话，不包含之前的消息")

# ============================================================================
# 示例 4: 查看保存的状态
# ============================================================================

print("\n" + "=" * 70)
print("示例 4: 查看 checkpointer 中保存的状态")
print("=" * 70)

try:
    # 获取保存的状态
    saved_state = checkpointer.get({"configurable": {"thread_id": "conversation_1"}})
    if saved_state:
        print("\n✅ 成功获取保存的状态")
        print(f"   线程 ID: conversation_1")
        if "channel_values" in saved_state:
            messages = saved_state["channel_values"].get("messages", [])
            print(f"   保存的消息数: {len(messages)}")
            print("\n   消息历史:")
            for i, msg in enumerate(messages[-5:], 1):  # 只显示最后5条
                content = msg.content if hasattr(msg, 'content') else str(msg)
                role = msg.__class__.__name__ if hasattr(msg, '__class__') else 'Unknown'
                print(f"     {i}. [{role}] {content[:50]}...")
except Exception as e:
    print(f"⚠️  无法获取状态: {e}")

# ============================================================================
# 示例 5: 记忆机制的工作原理
# ============================================================================

print("\n" + "=" * 70)
print("记忆机制的工作原理")
print("=" * 70)

print("""
1. 状态保存流程：
   agent.invoke(state, config)
     ↓
   Agent 处理请求
     ↓
   生成响应
     ↓
   自动调用 checkpointer.put(thread_id, new_state)
     ↓
   状态保存到内存

2. 状态恢复流程：
   agent.invoke(state, config)
     ↓
   Agent 检查 config 中的 thread_id
     ↓
   调用 checkpointer.get(thread_id) 获取之前的状态
     ↓
   合并之前的状态和新的输入
     ↓
   处理请求

3. thread_id 的作用：
   - 每个 thread_id 对应一个独立的对话上下文
   - 相同的 thread_id 会共享状态
   - 不同的 thread_id 互不影响

4. 状态包含的内容：
   - messages: 所有对话消息
   - 中间计算结果
   - 工具调用历史
   - 其他 agent 状态

5. 使用场景：
   - 多轮对话：维护对话上下文
   - 多用户系统：每个用户一个 thread_id
   - 会话管理：区分不同的对话会话
   - 状态持久化：可以保存到数据库（使用其他 checkpointer）
""")

# ============================================================================
# 示例 6: 对比有无记忆的区别
# ============================================================================

print("\n" + "=" * 70)
print("对比：有无记忆的区别")
print("=" * 70)

print("""
无 checkpointer（无记忆）:
  - 每次调用都是独立的
  - 不知道之前的对话内容
  - 无法引用之前的消息
  - 适合单次问答场景

有 checkpointer（有记忆）:
  - 维护对话历史
  - 可以引用之前的对话
  - 支持上下文理解
  - 适合多轮对话场景

示例对比：

无记忆：
  用户: "what is the weather in sf"
  Agent: "It's always sunny in sf!"
  
  用户: "what about new york?"
  Agent: "It's always sunny in new york!"
  （不知道用户之前问过 SF）

有记忆：
  用户: "what is the weather in sf"
  Agent: "It's always sunny in sf!"
  
  用户: "what about new york?"
  Agent: "It's always sunny in new york! 
          (Previously you asked about SF, which is also sunny)"
  （知道用户之前问过 SF）
""")

print("\n" + "=" * 70)
print("总结")
print("=" * 70)
print("""
Checkpointer 是 LangGraph 中实现记忆机制的核心组件：

1. **作用**: 保存和恢复 agent 的状态，实现对话连续性

2. **类型**:
   - InMemorySaver: 内存存储（开发/测试）
   - SqliteSaver: SQLite 数据库存储（生产环境）
   - 其他自定义 checkpointer

3. **关键概念**:
   - thread_id: 对话线程标识，用于区分不同的对话上下文
   - 状态保存: 每次调用后自动保存
   - 状态恢复: 下次调用时自动恢复

4. **使用方式**:
   - 创建 checkpointer
   - 在 create_agent 时传入 checkpointer
   - 在 invoke 时指定 thread_id

5. **优势**:
   - 自动管理对话状态
   - 支持多用户/多会话
   - 简化状态管理代码
   - 支持状态持久化
""")
