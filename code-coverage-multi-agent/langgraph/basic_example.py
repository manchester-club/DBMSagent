#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph 基础示例

演示如何使用LangGraph创建简单的状态机和工作流
"""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage


# 定义状态
class State(TypedDict):
    messages: Annotated[list, add_messages]
    counter: int


# 定义节点函数
def node_a(state: State) -> State:
    """节点A：处理消息并增加计数器"""
    print("执行节点A")
    new_messages = state["messages"] + [AIMessage(content="这是节点A的回复")]
    return {
        "messages": new_messages,
        "counter": state["counter"] + 1
    }


def node_b(state: State) -> State:
    """节点B：处理消息并增加计数器"""
    print("执行节点B")
    new_messages = state["messages"] + [AIMessage(content="这是节点B的回复")]
    return {
        "messages": new_messages,
        "counter": state["counter"] + 1
    }


def should_continue(state: State) -> str:
    """条件判断：决定下一步"""
    counter = state["counter"]
    if counter < 3:
        return "node_b"
    else:
        return "end"


# 创建图
def create_graph():
    """创建并返回LangGraph工作流"""
    workflow = StateGraph(State)
    
    # 添加节点
    workflow.add_node("node_a", node_a)
    workflow.add_node("node_b", node_b)
    
    # 设置入口点
    workflow.set_entry_point("node_a")
    
    # 添加条件边
    workflow.add_conditional_edges(
        "node_a",
        should_continue,
        {
            "node_b": "node_b",
            "end": END
        }
    )
    
    # 添加边
    workflow.add_edge("node_b", "node_a")
    
    # 编译图
    app = workflow.compile()
    return app


def main():
    """主函数"""
    print("=" * 60)
    print("LangGraph 基础示例")
    print("=" * 60)
    
    # 创建图
    app = create_graph()
    
    # 初始状态
    initial_state = {
        "messages": [HumanMessage(content="开始工作流")],
        "counter": 0
    }
    
    print("\n开始执行工作流...")
    print("-" * 60)
    
    # 执行工作流
    result = app.invoke(initial_state)
    
    print("\n" + "=" * 60)
    print("执行结果:")
    print("=" * 60)
    print(f"计数器值: {result['counter']}")
    print(f"消息数量: {len(result['messages'])}")
    print("\n所有消息:")
    for i, msg in enumerate(result['messages'], 1):
        print(f"  {i}. {type(msg).__name__}: {msg.content}")


if __name__ == "__main__":
    main()



