#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph + Ollama + Neo4j 智能体 (使用Tool机制)

使用LangGraph构建智能体工作流，集成Ollama进行自然语言处理，
通过@tool装饰器让LLM自主决定调用哪些工具。
"""

from typing import TypedDict, Annotated, List, Literal, Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from neo4j import GraphDatabase, Driver
import json
import re
try:
    from langchain_ollama import ChatOllama
    OLLAMA_AVAILABLE = True
except ImportError:
    try:
        from langchain_community.chat_models import ChatOllama
        OLLAMA_AVAILABLE = True
    except ImportError:
        OLLAMA_AVAILABLE = False
        ChatOllama = None  # 设置为 None 以避免未绑定错误
        print("⚠️ 警告: 未安装Ollama集成，请运行: pip install langchain-ollama")
try:
    from ollama_agent_config import get_default_model
except ImportError:
    def get_default_model() -> str:
        return "qwen3:30b-a3b"  # 默认模型


# Neo4j连接管理
class Neo4jConnection:
    """Neo4j连接管理器"""
    
    _instance: Optional['Neo4jConnection'] = None
    _driver: Optional[Driver] = None
    
    def __new__(cls, uri: str = "bolt://173.0.69.2:7687", 
                user: str = "neo4j", password: str = "neo4j123"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, uri: str = "bolt://173.0.69.2:7687", 
                 user: str = "neo4j", password: str = "neo4j123"):
        if self._driver is None:
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
    
    @property
    def driver(self) -> Driver:
        """获取 Neo4j driver，如果未初始化则抛出异常"""
        if self._driver is None:
            raise RuntimeError("Neo4j driver 未初始化")
        return self._driver
    
    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


# 全局Neo4j连接
neo4j_conn = Neo4jConnection()


# 定义工具函数（使用@tool装饰器）
@tool
def query_function_info(func_name: str) -> str:
    """查询函数的基本信息，包括名称、文件路径、行号和源代码。
    
    Args:
        func_name: 要查询的函数名称，例如 'date2timestamptz_opt_overflow'
    
    Returns:
        JSON格式的字符串，包含函数信息
    """
    try:
        with neo4j_conn.driver.session() as session:
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
                info = {
                    "name": record["name"],
                    "file_path": record["file_path"],
                    "line_number": record["line_number"],
                    "source": (record["source"] or "")[:500]  # 限制长度
                }
                return json.dumps(info, ensure_ascii=False, indent=2)
            else:
                return json.dumps({"error": f"未找到函数: {func_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"查询失败: {str(e)}"}, ensure_ascii=False)


@tool
def query_function_callers(func_name: str, limit: int = 10) -> str:
    """查询函数的调用者，即哪些函数调用了指定的函数。
    
    Args:
        func_name: 要查询的函数名称
        limit: 返回结果的最大数量，默认10
    
    Returns:
        JSON格式的字符串，包含调用者列表
    """
    try:
        with neo4j_conn.driver.session() as session:
            result = session.run("""
                MATCH (caller:Function)-[:CALLS]->(callee:Function {name: $func_name})
                RETURN caller.name as name, 
                       caller.file_path as file_path,
                       caller.line_number as line_number
                LIMIT $limit
            """, func_name=func_name, limit=limit)
            callers = [{
                "name": record["name"],
                "file_path": record["file_path"],
                "line_number": record["line_number"]
            } for record in result]
            return json.dumps({"callers": callers, "count": len(callers)}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"查询失败: {str(e)}"}, ensure_ascii=False)


@tool
def query_function_callees(func_name: str, limit: int = 10) -> str:
    """查询函数的被调用者，即指定函数调用了哪些其他函数。
    
    Args:
        func_name: 要查询的函数名称
        limit: 返回结果的最大数量，默认10
    
    Returns:
        JSON格式的字符串，包含被调用者列表
    """
    try:
        with neo4j_conn.driver.session() as session:
            result = session.run("""
                MATCH (caller:Function {name: $func_name})-[:CALLS]->(callee:Function)
                RETURN callee.name as name, 
                       callee.file_path as file_path,
                       callee.line_number as line_number
                LIMIT $limit
            """, func_name=func_name, limit=limit)
            callees = [{
                "name": record["name"],
                "file_path": record["file_path"],
                "line_number": record["line_number"]
            } for record in result]
            return json.dumps({"callees": callees, "count": len(callees)}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"查询失败: {str(e)}"}, ensure_ascii=False)


@tool
def search_functions_by_keyword(keyword: str, limit: int = 10) -> str:
    """根据关键词搜索函数名称。
    
    Args:
        keyword: 搜索关键词，会在函数名中查找包含该关键词的函数
        limit: 返回结果的最大数量，默认10
    
    Returns:
        JSON格式的字符串，包含匹配的函数列表
    """
    try:
        with neo4j_conn.driver.session() as session:
            result = session.run("""
                MATCH (f:Function)
                WHERE f.name CONTAINS $keyword
                RETURN f.name as name, 
                       f.file_path as file_path,
                       f.line_number as line_number
                LIMIT $limit
            """, keyword=keyword, limit=limit)
            functions = [{
                "name": record["name"],
                "file_path": record["file_path"],
                "line_number": record["line_number"]
            } for record in result]
            return json.dumps({"functions": functions, "count": len(functions)}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"搜索失败: {str(e)}"}, ensure_ascii=False)


@tool
def get_call_graph(func_name: str, depth: int = 2) -> str:
    """获取函数的调用图，包括调用者链和被调用者链。
    
    Args:
        func_name: 要查询的函数名称
        depth: 调用图的深度，默认2层
    
    Returns:
        JSON格式的字符串，包含调用图信息
    """
    try:
        with neo4j_conn.driver.session() as session:
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
            
            return json.dumps({
                "callers": callers,
                "callees": callees,
                "callers_count": len(callers),
                "callees_count": len(callees)
            }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"查询失败: {str(e)}"}, ensure_ascii=False)


# 所有可用工具列表
TOOLS = [
    query_function_info,
    query_function_callers,
    query_function_callees,
    search_functions_by_keyword,
    get_call_graph
]


# 定义状态
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# 定义节点函数
def call_model(state: AgentState) -> AgentState:
    """调用LLM，LLM可以自主决定调用哪些工具"""
    print("🤔 LLM思考中...")
    
    if not OLLAMA_AVAILABLE:
        # 回退模式：直接生成回复
        messages = state["messages"]
        last_message = messages[-1] if messages else None
        if isinstance(last_message, HumanMessage):
            response = f"抱歉，Ollama不可用。您的查询是: {last_message.content}"
            return {"messages": [AIMessage(content=response)]}
        return state
    
    # 获取LLM实例并绑定工具
    default_model = get_default_model()
    try:
        # 使用 ChatOllama 而不是 OllamaLLM，因为工具调用需要 ChatModel 接口
        # ChatOllama 的参数：model_name 或 model
        if not OLLAMA_AVAILABLE or ChatOllama is None:
            raise ImportError("ChatOllama 不可用")
        llm = ChatOllama(model=default_model, temperature=0.7)
        # 绑定工具到LLM
        llm_with_tools = llm.bind_tools(TOOLS)
    except Exception as e:
        print(f"⚠️ 无法加载模型 {default_model}: {e}")
        import traceback
        traceback.print_exc()
        # 回退到简单回复
        messages = state["messages"]
        last_message = messages[-1] if messages else None
        if isinstance(last_message, HumanMessage):
            error_response = f"抱歉，无法加载模型。错误: {str(e)}"
            return {"messages": [AIMessage(content=error_response)]}
        return state
    
    # 调用LLM
    messages = state["messages"]
    try:
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}
    except Exception as e:
        print(f"⚠️ LLM调用失败: {e}")
        error_msg = AIMessage(content=f"处理查询时出错: {str(e)}")
        return {"messages": [error_msg]}


def call_tool(state: AgentState) -> AgentState:
    """执行工具调用"""
    print("🔧 执行工具调用...")
    
    messages = state["messages"]
    last_message = messages[-1]
    
    # 检查是否有工具调用
    # Ollama可能返回不同的格式，需要兼容处理
    tool_calls = None
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        tool_calls = last_message.tool_calls
    elif hasattr(last_message, 'tool_calls') and isinstance(last_message.tool_calls, list):
        tool_calls = last_message.tool_calls
    
    if not tool_calls:
        return state
    
    # 执行所有工具调用
    tool_messages = []
    for tool_call in tool_calls:
        # 处理不同的tool_call格式
        if isinstance(tool_call, dict):
            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
            tool_args = tool_call.get("args") or tool_call.get("function", {}).get("arguments", {})
            tool_id = tool_call.get("id") or tool_call.get("function", {}).get("name", "unknown")
            
            # 如果args是字符串，尝试解析为JSON
            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except:
                    tool_args = {}
        else:
            # 如果是对象，尝试获取属性
            tool_name = getattr(tool_call, "name", None)
            tool_args = getattr(tool_call, "args", {})
            tool_id = getattr(tool_call, "id", "unknown")
        
        if not tool_name:
            continue
        
        print(f"  📌 调用工具: {tool_name} with args: {tool_args}")
        
        # 查找对应的工具函数
        tool_func = None
        for tool in TOOLS:
            if tool.name == tool_name:
                tool_func = tool
                break
        
        if tool_func:
            try:
                # 执行工具
                result = tool_func.invoke(tool_args)
                # 创建ToolMessage
                tool_message = ToolMessage(
                    content=str(result),
                    tool_call_id=str(tool_id)
                )
                tool_messages.append(tool_message)
            except Exception as e:
                error_msg = ToolMessage(
                    content=f"工具执行失败: {str(e)}",
                    tool_call_id=str(tool_id)
                )
                tool_messages.append(error_msg)
        else:
            error_msg = ToolMessage(
                content=f"未找到工具: {tool_name}",
                tool_call_id=str(tool_id)
            )
            tool_messages.append(error_msg)
    
    return {"messages": tool_messages}


def should_continue(state: AgentState) -> str:
    """决定下一步：继续调用工具还是结束"""
    messages = state["messages"]
    last_message = messages[-1]
    
    # 如果最后一条消息是AIMessage且有tool_calls，需要调用工具
    if isinstance(last_message, AIMessage):
        tool_calls = None
        if hasattr(last_message, 'tool_calls'):
            tool_calls = last_message.tool_calls
        
        # 检查是否有有效的工具调用
        if tool_calls:
            if isinstance(tool_calls, list) and len(tool_calls) > 0:
                return "tools"
            elif tool_calls:  # 非空非列表的情况
                return "tools"
    
    # 否则结束
    return "end"


# 创建图
def create_agent_graph():
    """创建智能体工作流"""
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", call_tool)
    
    # 设置入口点
    workflow.set_entry_point("agent")
    
    # 添加条件边
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )
    
    # 工具调用后继续回到agent
    workflow.add_edge("tools", "agent")
    
    # 编译图
    app = workflow.compile()
    return app


def main():
    """主函数 - 交互式智能体"""
    print("=" * 70)
    print("🤖 PostgreSQL代码分析智能体 (LangGraph + Ollama + Tool机制)")
    print("=" * 70)
    print("\n可用工具:")
    for i, tool in enumerate(TOOLS, 1):
        print(f"  {i}. {tool.name}: {tool.description.split('.')[0]}")
    print("\n提示: 输入 'quit' 或 'exit' 退出\n")
    
    try:
        # 创建图
        app = create_agent_graph()
        
        # 系统提示
        system_message = SystemMessage(content="""你是一个PostgreSQL代码分析助手。你可以使用以下工具来查询代码信息：
1. query_function_info - 查询函数基本信息
2. query_function_callers - 查询函数的调用者
3. query_function_callees - 查询函数的被调用者
4. search_functions_by_keyword - 根据关键词搜索函数
5. get_call_graph - 获取函数的调用图

根据用户的查询，自主决定调用哪些工具来获取信息，然后生成清晰的回复。
使用中文回复。""")
        
        while True:
            # 获取用户输入
            user_input = input("\n👤 您: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["quit", "exit", "退出"]:
                print("\n👋 再见！")
                break
            
            print("\n" + "-" * 70)
            
            # 初始状态（包含系统消息）
            initial_state: AgentState = {
                "messages": [system_message, HumanMessage(content=user_input)]
            }
            
            # 执行工作流
            try:
                result = app.invoke(initial_state)
                
                # 显示回复（只显示最后的AIMessage）
                print("\n🤖 智能体:")
                # 找到最后一条AIMessage
                for msg in reversed(result["messages"]):
                    if isinstance(msg, AIMessage):
                        # 显示工具调用信息
                        tool_calls = getattr(msg, 'tool_calls', None)
                        if tool_calls:
                            if isinstance(tool_calls, list):
                                print(f"[调用了 {len(tool_calls)} 个工具]")
                            else:
                                print("[调用了工具]")
                        # 显示回复内容
                        if msg.content:
                            print(msg.content)
                        break  # 只显示最后一条
                
            except Exception as e:
                print(f"\n❌ 错误: {str(e)}")
                import traceback
                traceback.print_exc()
        
    except KeyboardInterrupt:
        print("\n\n👋 再见！")
    finally:
        # 关闭Neo4j连接
        neo4j_conn.close()


if __name__ == "__main__":
    main()

