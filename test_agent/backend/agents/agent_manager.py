#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能体管理器
统一管理所有智能体，提供流式执行接口
"""

import sys
import os
from typing import Dict, Any, Optional, AsyncGenerator
from pathlib import Path
from typing_extensions import Protocol

# 添加 langgraph 目录到路径
langgraph_path = Path(__file__).parent.parent.parent / "langgraph"
sys.path.insert(0, str(langgraph_path))

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, ToolMessage
from langgraph.graph import StateGraph
from typing import Any, Union


class AgentWrapper:
    """智能体包装器基类"""
    
    def __init__(self, agent_id: str, name: str, description: str, tools: list):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.tools = tools
        self.app: Optional[Any] = None  # CompiledGraph 类型，但类型检查器无法识别
    
    def initialize(self):
        """初始化智能体（延迟加载）"""
        raise NotImplementedError
    
    async def stream_chat(
        self, 
        message: str, 
        thread_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:  # type: ignore[override]
        """流式执行对话"""
        raise NotImplementedError


class OllamaAgentWithToolsWrapper(AgentWrapper):
    """ollama_agent_with_tools 包装器"""
    
    def __init__(self):
        super().__init__(
            agent_id="ollama_agent_with_tools",
            name="PostgreSQL代码分析智能体",
            description="使用Tool机制，LLM自主决定工具调用",
            tools=[
                "query_function_info",
                "query_function_callers", 
                "query_function_callees",
                "search_functions_by_keyword",
                "get_call_graph"
            ]
        )
    
    def initialize(self):
        """初始化智能体"""
        if self.app is None:
            from ollama_agent_with_tools import create_agent_graph
            self.app = create_agent_graph()
    
    async def stream_chat(self, message: str, thread_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:  # type: ignore[override]
        """流式执行对话"""
        if self.app is None:
            self.initialize()
        
        from langchain_core.messages import SystemMessage
        from ollama_agent_with_tools import AgentState
        
        system_message = SystemMessage(content="""你是一个PostgreSQL代码分析助手。你可以使用以下工具来查询代码信息：
1. query_function_info - 查询函数基本信息
2. query_function_callers - 查询函数的调用者
3. query_function_callees - 查询函数的被调用者
4. search_functions_by_keyword - 根据关键词搜索函数
5. get_call_graph - 获取函数的调用图

根据用户的查询，自主决定调用哪些工具来获取信息，然后生成清晰的回复。
使用中文回复。""")
        
        initial_state: AgentState = {
            "messages": [system_message, HumanMessage(content=message)]
        }
        
        # 流式执行（提供空配置，避免配置错误）
        try:
            # 使用空配置，因为工具节点是自定义的，不需要额外配置
            config = {"configurable": {}}
            async for chunk in self.app.astream(initial_state, config=config):  # type: ignore[attr-defined]
                # 处理每个节点的输出
                for node_name, node_output in chunk.items():
                    if node_name == "agent":
                        # LLM 响应
                        messages = node_output.get("messages", [])
                        for msg in messages:
                            if isinstance(msg, AIMessage):
                                # 检查是否有工具调用
                                tool_calls = getattr(msg, 'tool_calls', None)
                                if tool_calls:
                                    # 工具调用开始
                                    for tool_call in tool_calls:
                                        if isinstance(tool_call, dict):
                                            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
                                            tool_args = tool_call.get("args") or tool_call.get("function", {}).get("arguments", {})
                                        else:
                                            tool_name = getattr(tool_call, "name", None)
                                            tool_args = getattr(tool_call, "args", {})
                                        
                                        if tool_name:
                                            yield {
                                                "type": "tool_call_start",
                                                "tool_name": tool_name,
                                                "args": tool_args if isinstance(tool_args, dict) else {}
                                            }
                                else:
                                    # 普通文本回复 - 逐字符流式输出
                                    content = msg.content or ""
                                    if content:
                                        # 如果内容很长，分块发送
                                        chunk_size = 10
                                        for i in range(0, len(content), chunk_size):
                                            yield {
                                                "type": "text_chunk",
                                                "content": content[i:i+chunk_size]
                                            }
                    
                    elif node_name == "tools":
                        # 工具执行结果
                        messages = node_output.get("messages", [])
                        for msg in messages:
                            if isinstance(msg, ToolMessage):
                                yield {
                                    "type": "tool_call_result",
                                    "tool_name": getattr(msg, "name", "unknown"),
                                    "result": msg.content
                                }
        except Exception as e:
            yield {
                "type": "error",
                "message": f"执行错误: {str(e)}"
            }
        
        yield {"type": "done"}


class CoverageMultiAgentWrapper(AgentWrapper):
    """coverage_multi_agent 包装器"""
    
    def __init__(self):
        super().__init__(
            agent_id="coverage_multi_agent",
            name="Coverage Multi-Agent",
            description="Supervisor协调多个专家Agent（SQL Tester、Code Explorer、Coverage Analyzer）",
            tools=[
                "Run_SQL_Test",
                "Collect_Coverage",
                "Get_Code_Context",
                "Search_Nearest_Seed",
                "Traverse_Call_Graph"
            ]
        )
    
    def initialize(self):
        """初始化智能体"""
        if self.app is None:
            # coverage_multi_agent 的 app 是在模块级别创建的
            from coverage_multi_agent import app
            self.app = app
    
    async def stream_chat(self, message: str, thread_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:  # type: ignore[override]
        """流式执行对话"""
        if self.app is None:
            self.initialize()
        
        from coverage_multi_agent import State
        from langchain_core.messages import HumanMessage
        config = {
            "configurable": {
                "thread_id": thread_id or "default_thread"
            }
        }
        
        initial: State = {
            "messages": [HumanMessage(content=message)],
            "next_agent": "__end__",
        }
        
        # 流式执行
        try:
            import time
            node_start_times = {}  # 记录每个节点的开始时间
            tool_args_cache = {}  # 缓存工具调用的参数
            
            async for chunk in self.app.astream(initial, config=config):  # type: ignore[attr-defined]
                for node_name, node_output in chunk.items():
                    current_time = time.time()
                    
                    if node_name == "supervisor":
                        # DISPATCH 事件：Supervisor 派发任务
                        next_agent = node_output.get("next_agent", "")
                        if next_agent and next_agent != "__end__":
                            agent_labels = {
                                "sql_tester": "SQL Tester",
                                "code_explorer": "Code Explorer",
                                "coverage_analyzer": "Coverage Analyzer"
                            }
                            agent_label = agent_labels.get(next_agent, next_agent)
                            yield {
                                "type": "dispatch",
                                "timestamp": int(current_time * 1000),
                                "orchestrator": "ORCHESTRATOR",
                                "agent": agent_label,
                                "content": f"派发 → {agent_label}"
                            }
                            node_start_times[next_agent] = current_time
                    
                    elif node_name in ["sql_tester", "code_explorer", "coverage_analyzer"]:
                        # 专家 Agent 响应
                        messages = node_output.get("messages", [])
                        agent_labels = {
                            "sql_tester": "SQL TESTER",
                            "code_explorer": "CODE EXPLORER",
                            "coverage_analyzer": "COVERAGE ANALYZER"
                        }
                        agent_tag = agent_labels.get(node_name, node_name.upper())
                        
                        for msg in messages:
                            if isinstance(msg, AIMessage):
                                content = msg.content or ""
                                if content:
                                    # THINK 事件：Agent 思考/回复
                                    yield {
                                        "type": "think",
                                        "timestamp": int(current_time * 1000),
                                        "agent": agent_tag,
                                        "content": content
                                    }
                            
                            # 检测工具调用开始（AIMessage 包含 tool_calls）
                            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tool_name = tc.get("name", "unknown")
                                    tool_args = tc.get("args", {})
                                    tool_id = tc.get("id", "unknown")
                                    # 缓存工具参数
                                    tool_key = f"{node_name}_{tool_name}_{tool_id}"
                                    tool_args_cache[tool_key] = tool_args
                                    # TOOL 事件：工具调用开始
                                    yield {
                                        "type": "tool",
                                        "timestamp": int(current_time * 1000),
                                        "agent": agent_tag,
                                        "tool_name": tool_name,
                                        "tool_id": tool_id,
                                        "args": tool_args,
                                        "status": "RUNNING",
                                    }
                                    # 记录工具开始时间
                                    node_start_times[tool_key] = current_time
                            
                            # 检测工具调用完成（ToolMessage）
                            elif isinstance(msg, ToolMessage):
                                tool_name = getattr(msg, "name", "unknown")
                                tool_call_id = getattr(msg, "tool_call_id", "unknown")
                                # 计算持续时间
                                duration = None
                                tool_key = f"{node_name}_{tool_name}_{tool_call_id}"
                                if tool_key in node_start_times:
                                    elapsed = (current_time - node_start_times[tool_key]) * 1000
                                    duration = f"{int(elapsed)}ms"
                                    del node_start_times[tool_key]
                                
                                # 获取缓存的参数
                                cached_args = tool_args_cache.get(tool_key, {})
                                
                                # TOOL 事件：工具执行完成
                                yield {
                                    "type": "tool",
                                    "timestamp": int(current_time * 1000),
                                    "agent": agent_tag,
                                    "tool_name": tool_name,
                                    "tool_id": tool_call_id,
                                    "args": cached_args,  # 包含参数
                                    "status": "COMPLETED",
                                    "duration": duration,
                                    "result": msg.content
                                }
                                
                                # 清理缓存
                                if tool_key in tool_args_cache:
                                    del tool_args_cache[tool_key]
        except Exception as e:
            yield {
                "type": "error",
                "message": f"执行错误: {str(e)}"
            }
        
        yield {"type": "done"}


class AgentManager:
    """智能体管理器"""
    
    def __init__(self):
        self.agents: Dict[str, AgentWrapper] = {}
        self._register_agents()
    
    def _register_agents(self):
        """注册所有智能体"""
        # 注册 coverage_multi_agent
        self.agents["coverage_multi_agent"] = CoverageMultiAgentWrapper()
        
        # TODO: 可以继续添加其他智能体
        # self.agents["ollama_agent_with_tools"] = OllamaAgentWithToolsWrapper()  # 已禁用
        # self.agents["coverage_agent"] = CoverageAgentWrapper()
        # self.agents["chat_bot"] = ChatBotWrapper()
    
    def get_agent(self, agent_id: str) -> Optional[AgentWrapper]:
        """获取智能体"""
        return self.agents.get(agent_id)
    
    def list_agents(self) -> list:
        """列出所有智能体"""
        return [
            {
                "id": agent.agent_id,
                "name": agent.name,
                "description": agent.description,
                "tools": agent.tools
            }
            for agent in self.agents.values()
        ]
    
    async def stream_chat(
        self, 
        agent_id: str, 
        message: str, 
        thread_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式执行对话"""
        agent = self.get_agent(agent_id)
        if agent is None:
            yield {
                "type": "error",
                "message": f"智能体 {agent_id} 不存在"
            }
            return
        
        try:
            agent.initialize()
            async for event in agent.stream_chat(message, thread_id):  # type: ignore[misc]
                yield event
        except Exception as e:
            yield {
                "type": "error",
                "message": str(e)
            }
