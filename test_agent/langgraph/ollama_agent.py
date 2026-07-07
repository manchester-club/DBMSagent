#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph + Ollama + Neo4j 智能体

使用LangGraph构建智能体工作流，集成Ollama进行自然语言处理，
并与Neo4j知识图谱交互。
"""

from typing import TypedDict, Annotated, List, Literal
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
try:
    from langchain_ollama import OllamaLLM
    OLLAMA_AVAILABLE = True
except ImportError:
    try:
        from langchain_community.llms import Ollama as OllamaLLM
        OLLAMA_AVAILABLE = True
    except ImportError:
        OLLAMA_AVAILABLE = False
        print("⚠️ 警告: 未安装Ollama集成，请运行: pip install langchain-ollama")
from neo4j import GraphDatabase
import json
import re
try:
    from ollama_agent_config import get_default_model
except ImportError:
    def get_default_model():
        return "qwen3:30b-a3b"  # 默认模型


# 定义状态
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    query: str
    intent: str  # 查询意图：query_function, query_call_graph, query_code, general
    function_name: str
    neo4j_result: dict
    step_count: int
    error: str


class Neo4jTool:
    """Neo4j工具类"""
    
    def __init__(self, uri: str = "bolt://173.0.69.2:7687", 
                 user: str = "neo4j", password: str = "neo4j123"):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        """关闭连接"""
        self.driver.close()
    
    def query_function_info(self, func_name: str) -> dict:
        """查询函数基本信息"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (f:Function {name: $func_name})
                RETURN f.name as name, 
                       f.file_path as file_path,
                       f.line_number as line_number,
                       f.raw_source as source
                LIMIT 1
            """, func_name=func_name)
            record = result.single()
            if record:
                return {
                    "name": record["name"],
                    "file_path": record["file_path"],
                    "line_number": record["line_number"],
                    "source": record["source"] or ""
                }
            return {}
    
    def query_callers(self, func_name: str, limit: int = 10) -> List[dict]:
        """查询函数的调用者"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (caller:Function)-[:CALLS]->(callee:Function {name: $func_name})
                RETURN caller.name as name, 
                       caller.file_path as file_path,
                       caller.line_number as line_number
                LIMIT $limit
            """, func_name=func_name, limit=limit)
            return [{
                "name": record["name"],
                "file_path": record["file_path"],
                "line_number": record["line_number"]
            } for record in result]
    
    def query_callees(self, func_name: str, limit: int = 10) -> List[dict]:
        """查询函数的被调用者"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (caller:Function {name: $func_name})-[:CALLS]->(callee:Function)
                RETURN callee.name as name, 
                       callee.file_path as file_path,
                       callee.line_number as line_number
                LIMIT $limit
            """, func_name=func_name, limit=limit)
            return [{
                "name": record["name"],
                "file_path": record["file_path"],
                "line_number": record["line_number"]
            } for record in result]
    
    def search_functions_by_keyword(self, keyword: str, limit: int = 10) -> List[dict]:
        """根据关键词搜索函数"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (f:Function)
                WHERE f.name CONTAINS $keyword
                RETURN f.name as name, 
                       f.file_path as file_path,
                       f.line_number as line_number
                LIMIT $limit
            """, keyword=keyword, limit=limit)
            return [{
                "name": record["name"],
                "file_path": record["file_path"],
                "line_number": record["line_number"]
            } for record in result]
    
    def get_call_graph(self, func_name: str, depth: int = 2) -> dict:
        """获取函数的调用图"""
        with self.driver.session() as session:
            # 查询调用者（向上）
            callers_result = session.run("""
                MATCH path = (caller:Function)-[:CALLS*1..$depth]->(target:Function {name: $func_name})
                RETURN DISTINCT caller.name as name, 
                       length(path) as depth
                LIMIT 20
            """, func_name=func_name, depth=depth)
            callers = [{"name": record["name"], "depth": record["depth"]} 
                      for record in callers_result]
            
            # 查询被调用者（向下）
            callees_result = session.run("""
                MATCH path = (target:Function {name: $func_name})-[:CALLS*1..$depth]->(callee:Function)
                RETURN DISTINCT callee.name as name, 
                       length(path) as depth
                LIMIT 20
            """, func_name=func_name, depth=depth)
            callees = [{"name": record["name"], "depth": record["depth"]} 
                      for record in callees_result]
            
            return {
                "callers": callers,
                "callees": callees
            }


# 全局工具实例
neo4j_tool = Neo4jTool()


# 定义节点函数
def parse_intent(state: AgentState) -> AgentState:
    """使用Ollama解析用户意图"""
    print("🤔 解析用户意图...")
    
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    
    if not isinstance(last_message, HumanMessage):
        return {**state, "intent": "general", "step_count": state.get("step_count", 0) + 1}
    
    query = last_message.content
    
    # 使用Ollama进行意图识别
    if not OLLAMA_AVAILABLE:
        # 回退到简单规则匹配
        intent = "general"
        function_name = ""
        if "函数" in query or "function" in query.lower():
            words = query.split()
            for i, word in enumerate(words):
                if word in ["函数", "function"] and i + 1 < len(words):
                    function_name = words[i + 1]
                    break
            if function_name:
                intent = "query_function"
        return {
            **state,
            "query": query,
            "intent": intent,
            "function_name": function_name,
            "step_count": state.get("step_count", 0) + 1
        }
    
    # 尝试使用Ollama，如果失败则回退
    default_model = get_default_model()
    llm = None
    try:
        llm = OllamaLLM(model=default_model, temperature=0.1)
    except Exception as e:
        print(f"⚠️ 无法加载模型 {default_model}: {e}")
        llm = None
    
    prompt = f"""分析以下用户查询的意图，并提取关键信息。

用户查询: {query}

请判断查询意图，并提取函数名（如果有）：
1. 如果查询关于特定函数的信息，意图为 "query_function"，提取函数名
2. 如果查询函数的调用关系或调用图，意图为 "query_call_graph"，提取函数名
3. 如果查询函数的源代码，意图为 "query_code"，提取函数名
4. 其他情况，意图为 "general"

请以JSON格式回复，格式：
{{
    "intent": "query_function|query_call_graph|query_code|general",
    "function_name": "函数名或空字符串"
}}

只返回JSON，不要其他内容。"""
    
    try:
        if llm is None:
            # 回退到规则匹配
            intent = "general"
            function_name = ""
            if "函数" in query or "function" in query.lower():
                words = query.split()
                for i, word in enumerate(words):
                    if word in ["函数", "function"] and i + 1 < len(words):
                        function_name = words[i + 1]
                        break
                if function_name:
                    intent = "query_function"
            return {
                **state,
                "query": query,
                "intent": intent,
                "function_name": function_name,
                "step_count": state.get("step_count", 0) + 1
            }
        response = llm.invoke(prompt)
        # 尝试提取JSON
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            intent = result.get("intent", "general")
            function_name = result.get("function_name", "").strip()
        else:
            # 简单规则匹配
            intent = "general"
            function_name = ""
            if "函数" in query or "function" in query.lower():
                # 尝试提取函数名
                words = query.split()
                for i, word in enumerate(words):
                    if word in ["函数", "function"] and i + 1 < len(words):
                        function_name = words[i + 1]
                        break
                if function_name:
                    intent = "query_function"
    except Exception as e:
        print(f"⚠️ 意图解析失败: {e}")
        intent = "general"
        function_name = ""
    
    return {
        **state,
        "query": query,
        "intent": intent,
        "function_name": function_name,
        "step_count": state.get("step_count", 0) + 1
    }


def query_neo4j(state: AgentState) -> AgentState:
    """查询Neo4j数据库"""
    print("🔍 查询Neo4j知识图谱...")
    
    intent = state.get("intent", "general")
    function_name = state.get("function_name", "")
    
    result = {}
    
    if intent == "query_function" and function_name:
        # 查询函数信息
        func_info = neo4j_tool.query_function_info(function_name)
        if func_info:
            result["function_info"] = func_info
            result["callers"] = neo4j_tool.query_callers(function_name)
            result["callees"] = neo4j_tool.query_callees(function_name)
        else:
            # 尝试搜索相似函数
            similar = neo4j_tool.search_functions_by_keyword(function_name)
            result["similar_functions"] = similar
    
    elif intent == "query_call_graph" and function_name:
        # 查询调用图
        call_graph = neo4j_tool.get_call_graph(function_name)
        result["call_graph"] = call_graph
        func_info = neo4j_tool.query_function_info(function_name)
        if func_info:
            result["function_info"] = func_info
    
    elif intent == "query_code" and function_name:
        # 查询源代码
        func_info = neo4j_tool.query_function_info(function_name)
        if func_info:
            result["function_info"] = func_info
            result["source_code"] = func_info.get("source", "")
    
    elif intent == "general":
        # 通用查询，尝试搜索关键词
        query = state.get("query", "")
        # 提取可能的函数名关键词
        keywords = re.findall(r'\b\w+\b', query)
        for keyword in keywords:
            if len(keyword) > 3:  # 过滤太短的词
                similar = neo4j_tool.search_functions_by_keyword(keyword, limit=5)
                if similar:
                    result["search_results"] = similar
                    break
    
    return {
        **state,
        "neo4j_result": result,
        "step_count": state.get("step_count", 0) + 1
    }


def generate_response(state: AgentState) -> AgentState:
    """使用Ollama生成回复"""
    print("💬 生成智能回复...")
    
    query = state.get("query", "")
    intent = state.get("intent", "general")
    result = state.get("neo4j_result", {})
    
    # 构建上下文
    context_parts = []
    
    if "function_info" in result:
        func_info = result["function_info"]
        context_parts.append(f"函数信息:")
        context_parts.append(f"- 名称: {func_info['name']}")
        context_parts.append(f"- 文件: {func_info['file_path']}")
        context_parts.append(f"- 行号: {func_info['line_number']}")
        
        if "source_code" in result:
            source = result["source_code"][:1000]  # 限制长度
            context_parts.append(f"\n源代码预览:\n{source}")
    
    if "callers" in result:
        callers = result["callers"]
        context_parts.append(f"\n调用者 ({len(callers)} 个):")
        for caller in callers[:5]:
            context_parts.append(f"- {caller['name']} ({caller.get('file_path', '')})")
    
    if "callees" in result:
        callees = result["callees"]
        context_parts.append(f"\n被调用者 ({len(callees)} 个):")
        for callee in callees[:5]:
            context_parts.append(f"- {callee['name']} ({callee.get('file_path', '')})")
    
    if "call_graph" in result:
        call_graph = result["call_graph"]
        context_parts.append(f"\n调用图:")
        if call_graph.get("callers"):
            context_parts.append(f"调用者链 ({len(call_graph['callers'])} 个):")
            for item in call_graph["callers"][:5]:
                context_parts.append(f"- {item['name']} (深度: {item['depth']})")
        if call_graph.get("callees"):
            context_parts.append(f"被调用者链 ({len(call_graph['callees'])} 个):")
            for item in call_graph["callees"][:5]:
                context_parts.append(f"- {item['name']} (深度: {item['depth']})")
    
    if "similar_functions" in result:
        similar = result["similar_functions"]
        context_parts.append(f"\n未找到精确匹配，相似函数 ({len(similar)} 个):")
        for func in similar[:5]:
            context_parts.append(f"- {func['name']} ({func.get('file_path', '')})")
    
    if "search_results" in result:
        search_results = result["search_results"]
        context_parts.append(f"\n搜索结果 ({len(search_results)} 个):")
        for func in search_results[:5]:
            context_parts.append(f"- {func['name']} ({func.get('file_path', '')})")
    
    context = "\n".join(context_parts) if context_parts else "未找到相关信息"
    
    # 使用Ollama生成回复
    if not OLLAMA_AVAILABLE:
        # 回退到简单格式化回复
        response = f"根据您的查询，我找到了以下信息：\n\n{context}"
        new_messages = state["messages"] + [AIMessage(content=response)]
        return {
            **state,
            "messages": new_messages,
            "step_count": state.get("step_count", 0) + 1
        }
    
    # 尝试使用Ollama，如果失败则回退
    default_model = get_default_model()
    llm = None
    try:
        llm = OllamaLLM(model=default_model, temperature=0.7)
    except Exception as e:
        print(f"⚠️ 无法加载模型 {default_model}: {e}")
        llm = None
    
    system_prompt = """你是一个PostgreSQL代码分析助手。根据用户查询和提供的代码信息，生成清晰、有用的回复。
- 如果找到了相关信息，详细说明
- 如果未找到，提供建议
- 使用中文回复
- 保持专业和友好"""
    
    user_prompt = f"""用户查询: {query}

查询意图: {intent}

查询结果:
{context}

请根据以上信息生成回复。"""
    
    try:
        if llm is None:
            # 回退到简单格式化回复
            response = f"根据您的查询，我找到了以下信息：\n\n{context}"
        else:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            response = llm.invoke([msg.content for msg in messages])
        
        new_messages = state["messages"] + [AIMessage(content=response)]
        
        return {
            **state,
            "messages": new_messages,
            "step_count": state.get("step_count", 0) + 1
        }
    except Exception as e:
        error_msg = f"生成回复时出错: {str(e)}"
        print(f"⚠️ {error_msg}")
        fallback_response = f"抱歉，处理您的查询时遇到问题。\n\n查询结果:\n{context}"
        new_messages = state["messages"] + [AIMessage(content=fallback_response)]
        return {
            **state,
            "messages": new_messages,
            "error": error_msg,
            "step_count": state.get("step_count", 0) + 1
        }


def should_continue(state: AgentState) -> str:
    """决定下一步"""
    step_count = state.get("step_count", 0)
    intent = state.get("intent", "general")
    
    if step_count == 1:
        # 解析意图后，根据意图决定
        if intent in ["query_function", "query_call_graph", "query_code"]:
            return "query_neo4j"
        else:
            return "generate_response"
    elif step_count == 2:
        return "generate_response"
    else:
        return "end"


# 创建图
def create_agent_graph():
    """创建智能体工作流"""
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("parse_intent", parse_intent)
    workflow.add_node("query_neo4j", query_neo4j)
    workflow.add_node("generate_response", generate_response)
    
    # 设置入口点
    workflow.set_entry_point("parse_intent")
    
    # 添加条件边
    workflow.add_conditional_edges(
        "parse_intent",
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
    """主函数 - 交互式智能体"""
    print("=" * 70)
    print("🤖 PostgreSQL代码分析智能体 (LangGraph + Ollama + Neo4j)")
    print("=" * 70)
    print("\n提示: 输入 'quit' 或 'exit' 退出\n")
    
    try:
        # 创建图
        app = create_agent_graph()
        
        while True:
            # 获取用户输入
            user_input = input("\n👤 您: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["quit", "exit", "退出"]:
                print("\n👋 再见！")
                break
            
            print("\n" + "-" * 70)
            
            # 初始状态
            initial_state = {
                "messages": [HumanMessage(content=user_input)],
                "query": "",
                "intent": "",
                "function_name": "",
                "neo4j_result": {},
                "step_count": 0,
                "error": ""
            }
            
            # 执行工作流
            try:
                result = app.invoke(initial_state)
                
                # 显示回复
                print("\n🤖 智能体:")
                for msg in result["messages"]:
                    if isinstance(msg, AIMessage):
                        print(msg.content)
                
                # 显示统计信息
                if result.get("step_count", 0) > 0:
                    print(f"\n[执行了 {result['step_count']} 个步骤]")
                
            except Exception as e:
                print(f"\n❌ 错误: {str(e)}")
        
    except KeyboardInterrupt:
        print("\n\n👋 再见！")
    finally:
        # 关闭Neo4j连接
        neo4j_tool.close()


if __name__ == "__main__":
    main()

