#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph + Neo4j 集成示例

演示如何使用LangGraph创建一个与Neo4j交互的智能体
"""

from typing import TypedDict, Annotated, List
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from neo4j import GraphDatabase
import json


# 定义状态
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    query: str
    neo4j_result: dict
    step_count: int


class Neo4jAgent:
    """Neo4j智能体"""
    
    def __init__(self, uri: str = "bolt://173.0.69.2:7687", 
                 user: str = "neo4j", password: str = "neo4j123"):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        """关闭连接"""
        self.driver.close()
    
    def query_functions(self, func_name: str) -> dict:
        """查询函数信息"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (f:Function {name: $func_name})
                RETURN f.name as name, 
                       f.file_path as file_path,
                       f.line_number as line_number,
                       substring(f.raw_source, 0, 500) as source_preview
                LIMIT 1
            """, func_name=func_name)
            record = result.single()
            if record:
                return {
                    "name": record["name"],
                    "file_path": record["file_path"],
                    "line_number": record["line_number"],
                    "source_preview": record["source_preview"]
                }
            return {}
    
    def query_callers(self, func_name: str, limit: int = 5) -> List[dict]:
        """查询函数的调用者"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (caller:Function)-[:CALLS]->(callee:Function {name: $func_name})
                RETURN caller.name as name, caller.file_path as file_path
                LIMIT $limit
            """, func_name=func_name, limit=limit)
            return [{"name": record["name"], "file_path": record["file_path"]} 
                   for record in result]
    
    def query_callees(self, func_name: str, limit: int = 5) -> List[dict]:
        """查询函数的被调用者"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (caller:Function {name: $func_name})-[:CALLS]->(callee:Function)
                RETURN callee.name as name, callee.file_path as file_path
                LIMIT $limit
            """, func_name=func_name, limit=limit)
            return [{"name": record["name"], "file_path": record["file_path"]} 
                   for record in result]


# 创建智能体实例（全局）
neo4j_agent = Neo4jAgent()


# 定义节点函数
def parse_query(state: AgentState) -> AgentState:
    """解析用户查询"""
    print("📝 解析查询...")
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    
    if isinstance(last_message, HumanMessage):
        query = last_message.content
    else:
        query = state.get("query", "")
    
    # 简单的查询解析（实际应该使用LLM）
    func_name = None
    if "函数" in query or "function" in query.lower():
        # 尝试提取函数名
        words = query.split()
        for i, word in enumerate(words):
            if word in ["函数", "function"] and i + 1 < len(words):
                func_name = words[i + 1]
                break
    
    return {
        **state,
        "query": query,
        "step_count": state.get("step_count", 0) + 1
    }


def query_neo4j(state: AgentState) -> AgentState:
    """查询Neo4j数据库"""
    print("🔍 查询Neo4j...")
    query = state.get("query", "")
    
    # 简单的函数名提取（实际应该使用LLM）
    func_name = None
    if "date2timestamptz" in query:
        func_name = "date2timestamptz_opt_overflow"
    elif "函数" in query:
        # 尝试提取函数名
        parts = query.split()
        for part in parts:
            if part and not part in ["查询", "函数", "的", "调用"]:
                func_name = part
                break
    
    result = {}
    if func_name:
        # 查询函数信息
        func_info = neo4j_agent.query_functions(func_name)
        if func_info:
            result["function_info"] = func_info
            result["callers"] = neo4j_agent.query_callers(func_name)
            result["callees"] = neo4j_agent.query_callees(func_name)
    
    return {
        **state,
        "neo4j_result": result,
        "step_count": state.get("step_count", 0) + 1
    }


def generate_response(state: AgentState) -> AgentState:
    """生成回复"""
    print("💬 生成回复...")
    result = state.get("neo4j_result", {})
    query = state.get("query", "")
    
    response_parts = []
    
    if "function_info" in result:
        func_info = result["function_info"]
        response_parts.append(f"找到函数: {func_info['name']}")
        response_parts.append(f"文件路径: {func_info['file_path']}")
        
        if result.get("callers"):
            response_parts.append(f"\n调用者 ({len(result['callers'])} 个):")
            for caller in result["callers"][:3]:
                response_parts.append(f"  - {caller['name']}")
        
        if result.get("callees"):
            response_parts.append(f"\n被调用者 ({len(result['callees'])} 个):")
            for callee in result["callees"][:3]:
                response_parts.append(f"  - {callee['name']}")
    else:
        response_parts.append("未找到相关信息")
    
    response = "\n".join(response_parts)
    
    new_messages = state["messages"] + [AIMessage(content=response)]
    
    return {
        **state,
        "messages": new_messages,
        "step_count": state.get("step_count", 0) + 1
    }


def should_continue(state: AgentState) -> str:
    """决定下一步"""
    step_count = state.get("step_count", 0)
    neo4j_result = state.get("neo4j_result", {})
    
    if step_count == 1:
        return "query_neo4j"
    elif step_count == 2:
        return "generate_response"
    else:
        return "end"


# 创建图
def create_neo4j_agent_graph():
    """创建Neo4j智能体工作流"""
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("parse_query", parse_query)
    workflow.add_node("query_neo4j", query_neo4j)
    workflow.add_node("generate_response", generate_response)
    
    # 设置入口点
    workflow.set_entry_point("parse_query")
    
    # 添加条件边
    workflow.add_conditional_edges(
        "parse_query",
        should_continue,
        {
            "query_neo4j": "query_neo4j",
            "generate_response": "generate_response",
            "end": END
        }
    )
    
    workflow.add_conditional_edges(
        "query_neo4j",
        should_continue,
        {
            "generate_response": "generate_response",
            "end": END
        }
    )
    
    workflow.add_edge("generate_response", END)
    
    # 编译图
    app = workflow.compile()
    return app


def main():
    """主函数"""
    print("=" * 60)
    print("LangGraph + Neo4j 集成示例")
    print("=" * 60)
    
    try:
        # 创建图
        app = create_neo4j_agent_graph()
        
        # 测试查询
        test_queries = [
            "查询函数 date2timestamptz_opt_overflow",
            "查找 date2timestamptz 函数的调用关系"
        ]
        
        for query in test_queries[:1]:  # 只测试第一个
            print(f"\n📋 用户查询: {query}")
            print("-" * 60)
            
            # 初始状态
            initial_state = {
                "messages": [HumanMessage(content=query)],
                "query": "",
                "neo4j_result": {},
                "step_count": 0
            }
            
            # 执行工作流
            result = app.invoke(initial_state)
            
            print("\n" + "=" * 60)
            print("执行结果:")
            print("=" * 60)
            print(f"步骤数: {result['step_count']}")
            print(f"\n最终回复:")
            for msg in result["messages"]:
                if isinstance(msg, AIMessage):
                    print(f"  {msg.content}")
        
    finally:
        # 关闭Neo4j连接
        neo4j_agent.close()


if __name__ == "__main__":
    main()



