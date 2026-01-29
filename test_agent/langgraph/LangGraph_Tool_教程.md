# LangGraph 中使用 Tools 的完整教程

本教程将详细介绍如何在 LangGraph 中定义和使用工具（Tools），让 LLM 能够自主决定调用哪些工具来完成任务。

## 目录

1. [概述](#概述)
2. [定义工具](#定义工具)
3. [绑定工具到 LLM](#绑定工具到-llm)
4. [在 LangGraph 中集成工具](#在-langgraph-中集成工具)
5. [处理工具调用](#处理工具调用)
6. [完整示例](#完整示例)
7. [最佳实践](#最佳实践)

---

## 概述

在 LangGraph 中使用工具的核心流程：

```
用户输入 → LLM思考 → 决定调用工具 → 执行工具 → 返回结果 → LLM生成回复
```

关键组件：
- **@tool 装饰器**：将 Python 函数转换为 LangChain 工具
- **bind_tools()**：将工具绑定到 LLM，让 LLM 知道可用工具
- **tool_calls**：LLM 返回的工具调用请求
- **ToolMessage**：工具执行结果的封装

---

## 定义工具

### 1. 使用 @tool 装饰器

使用 `@tool` 装饰器将普通 Python 函数转换为 LangChain 工具：

```python
from langchain_core.tools import tool

@tool
def query_function_info(func_name: str) -> str:
    """查询函数的基本信息，包括名称、文件路径、行号和源代码。
    
    Args:
        func_name: 要查询的函数名称，例如 'date2timestamptz_opt_overflow'
    
    Returns:
        JSON格式的字符串，包含函数信息
    """
    # 工具实现逻辑
    return json.dumps({"name": func_name, ...})
```

**关键点**：
- 函数的文档字符串（docstring）会被自动解析为工具描述
- 参数类型注解用于生成工具的参数模式
- 返回类型注解用于说明工具的输出格式

### 2. 工具定义示例

参考 `ollama_agent_with_tools.py` 中的工具定义（第 68-234 行）：

```68:100:ollama_agent_with_tools.py
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
```

更多工具示例：

```103:130:ollama_agent_with_tools.py
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
```

### 3. 工具列表

将所有工具收集到一个列表中（第 237-244 行）：

```237:244:ollama_agent_with_tools.py
# 所有可用工具列表
TOOLS = [
    query_function_info,
    query_function_callers,
    query_function_callees,
    search_functions_by_keyword,
    get_call_graph
]
```

---

## 绑定工具到 LLM

### 1. 创建 LLM 实例

```python
from langchain_ollama import OllamaLLM

llm = OllamaLLM(model="qwen3:30b-a3b", temperature=0.7)
```

### 2. 绑定工具

使用 `bind_tools()` 方法将工具绑定到 LLM：

```python
llm_with_tools = llm.bind_tools(TOOLS)
```

**作用**：
- 让 LLM 知道有哪些可用工具
- LLM 可以根据用户查询自主决定调用哪些工具
- 工具的描述和参数会自动传递给 LLM

### 3. 调用 LLM

绑定工具后，正常调用 LLM：

```python
messages = [HumanMessage(content="查询函数 date2timestamptz_opt_overflow 的信息")]
response = llm_with_tools.invoke(messages)
```

**响应格式**：
- 如果 LLM 决定调用工具，`response` 会是 `AIMessage` 对象
- `response.tool_calls` 包含工具调用列表
- 如果不需要工具，`response.content` 包含直接回复

---

## 在 LangGraph 中集成工具

### 1. 定义状态

定义状态结构（第 247-249 行）：

```247:249:ollama_agent_with_tools.py
# 定义状态
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
```

**说明**：
- `TypedDict` 定义状态的数据结构
- `Annotated[list, add_messages]` 使用 `add_messages` 自动合并消息列表
- 这样在添加新消息时，会自动追加到现有消息列表

### 2. 创建 Agent 节点

Agent 节点负责调用 LLM（第 253-284 行）：

```253:284:ollama_agent_with_tools.py
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
        llm = OllamaLLM(model=default_model, temperature=0.7)
        # 绑定工具到LLM
        llm_with_tools = llm.bind_tools(TOOLS)
    except Exception as e:
        print(f"⚠️ 无法加载模型 {default_model}: {e}")
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
```

**关键点**：
- **第 271 行**：`llm.bind_tools(TOOLS)` 是关键，将工具绑定到 LLM
- **第 279 行**：调用 LLM，LLM 会根据上下文决定是否调用工具
- **第 280 行**：返回 LLM 的响应（可能是普通回复或工具调用请求）
- 每次调用都重新绑定工具（也可以缓存 `llm_with_tools` 提升性能）

### 3. 创建 Tools 节点

Tools 节点负责执行工具调用（第 287-361 行）：

```287:361:ollama_agent_with_tools.py
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
```

**关键点**：
- **第 297-300 行**：检查 `AIMessage.tool_calls` 属性，兼容不同格式
- **第 309-324 行**：处理不同的 `tool_call` 格式（字典或对象）
- **第 333-336 行**：根据工具名称在 `TOOLS` 列表中查找对应工具
- **第 341 行**：执行工具函数 `tool_func.invoke(tool_args)`
- **第 343-346 行**：创建 `ToolMessage` 封装工具执行结果
- **第 345 行**：`tool_call_id` 用于关联工具调用和结果，LLM 需要这个 ID 来匹配

### 4. 条件路由

决定下一步是继续调用工具还是结束（第 364-383 行）：

```364:383:ollama_agent_with_tools.py
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
```

**说明**：
- 检查最后一条消息是否是 `AIMessage` 且有 `tool_calls`
- 如果有工具调用，返回 `"tools"` 路由到工具节点
- 如果没有工具调用，返回 `"end"` 结束工作流

### 5. 构建工作流

构建完整的工作流（第 386-413 行）：

```386:413:ollama_agent_with_tools.py
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
```

**工作流图示**：
```
[入口] → [agent] → [条件判断]
                    ├─ 有工具调用 → [tools] → [agent] (循环)
                    └─ 无工具调用 → [END]
```

**关键点**：
- **第 392-393 行**：添加两个节点：`agent`（调用LLM）和 `tools`（执行工具）
- **第 396 行**：设置入口点为 `agent`
- **第 398-405 行**：从 `agent` 添加条件边，根据 `should_continue` 的结果路由
- **第 409 行**：工具执行后回到 `agent`，形成循环，让 LLM 基于工具结果生成回复

---

## 处理工具调用

### 1. 工具调用的数据结构

LLM 返回的 `tool_calls` 可能是以下格式之一：

**格式1（字典）**：
```python
{
    "name": "query_function_info",
    "args": {"func_name": "date2timestamptz_opt_overflow"},
    "id": "call_123"
}
```

**格式2（对象）**：
```python
tool_call.name  # "query_function_info"
tool_call.args  # {"func_name": "..."}
tool_call.id    # "call_123"
```

### 2. 工具执行结果

使用 `ToolMessage` 封装工具执行结果：

```python
from langchain_core.messages import ToolMessage

tool_message = ToolMessage(
    content=str(result),  # 工具返回的结果
    tool_call_id=str(tool_id)  # 关联的工具调用ID
)
```

### 3. 多轮工具调用

LLM 可以：
- 一次调用多个工具（并行）
- 根据工具结果决定是否继续调用其他工具
- 基于工具结果生成最终回复

---

## 完整示例

### 源代码位置

完整示例代码位于：`/public/home/rongyankai/test_agent/langgraph/ollama_agent_with_tools.py`

### 运行示例

```bash
cd /public/home/rongyankai/test_agent/langgraph
python3 ollama_agent_with_tools.py
```

### 交互示例

```
👤 您: 查询函数 date2timestamptz_opt_overflow 的调用关系

🤔 LLM思考中...
🔧 执行工具调用...
  📌 调用工具: query_function_info with args: {'func_name': 'date2timestamptz_opt_overflow'}
  📌 调用工具: query_function_callers with args: {'func_name': 'date2timestamptz_opt_overflow'}
🤔 LLM思考中...

🤖 智能体: [根据工具结果生成的回复]
```

### 关键代码片段总结

#### 1. 工具定义（第 68-234 行）

使用 `@tool` 装饰器定义工具函数，参考：
- `query_function_info`（第 68-100 行）
- `query_function_callers`（第 103-130 行）
- 其他工具类似

#### 2. 工具列表（第 237-244 行）

```237:244:ollama_agent_with_tools.py
# 所有可用工具列表
TOOLS = [
    query_function_info,
    query_function_callers,
    query_function_callees,
    search_functions_by_keyword,
    get_call_graph
]
```

#### 3. 工具绑定（第 253-284 行）

在 `call_model` 函数中绑定工具：
```253:271:ollama_agent_with_tools.py
def call_model(state: AgentState) -> AgentState:
    """调用LLM，LLM可以自主决定调用哪些工具"""
    print("🤔 LLM思考中...")
    
    # ... 省略错误处理 ...
    
    # 获取LLM实例并绑定工具
    default_model = get_default_model()
    try:
        llm = OllamaLLM(model=default_model, temperature=0.7)
        # 绑定工具到LLM
        llm_with_tools = llm.bind_tools(TOOLS)
```

#### 4. 工具执行（第 287-361 行）

在 `call_tool` 函数中执行工具，参考完整代码。

#### 5. 条件路由（第 364-383 行）

在 `should_continue` 函数中决定路由，参考完整代码。

#### 6. 工作流构建（第 386-413 行）

在 `create_agent_graph` 函数中构建工作流，参考完整代码。

---

## 最佳实践

### 1. 工具设计

- ✅ **单一职责**：每个工具只做一件事
- ✅ **清晰描述**：在 docstring 中详细说明工具的功能和参数
- ✅ **错误处理**：工具内部处理异常，返回错误信息而不是抛出异常
- ✅ **返回格式**：使用 JSON 字符串便于 LLM 解析

### 2. 工具调用处理

- ✅ **兼容性**：处理不同格式的 `tool_calls`
- ✅ **错误处理**：工具执行失败时返回 `ToolMessage` 说明错误
- ✅ **日志记录**：记录工具调用和执行情况，便于调试

### 3. 工作流设计

- ✅ **循环控制**：避免无限循环（可以添加最大迭代次数）
- ✅ **状态管理**：使用 `add_messages` 自动合并消息
- ✅ **系统提示**：在系统消息中说明可用工具

### 4. 性能优化

- ✅ **工具缓存**：可以缓存 `llm_with_tools` 实例
- ✅ **批量执行**：如果 LLM 调用多个工具，可以并行执行
- ✅ **结果限制**：工具返回结果不要过长，避免超出 LLM 上下文

### 5. 调试技巧

- ✅ **打印工具调用**：在 `call_tool` 中打印工具名称和参数
- ✅ **检查 tool_calls**：打印 `AIMessage.tool_calls` 查看格式
- ✅ **验证工具绑定**：确认 `bind_tools()` 成功执行

---

## 常见问题

### Q1: LLM 不调用工具怎么办？

**可能原因**：
- 工具描述不够清晰
- LLM 模型不支持工具调用
- 系统提示没有说明工具用途

**解决方案**：
- 改进工具 docstring
- 在系统提示中明确说明可用工具
- 使用支持工具调用的模型（如 GPT-4, Claude, Qwen 等）

### Q2: 工具调用格式不匹配？

**解决方案**：
- 检查 `tool_calls` 的实际格式
- 在 `call_tool` 中处理多种格式
- 打印 `tool_calls` 调试

### Q3: 工具执行失败？

**解决方案**：
- 在工具函数中添加异常处理
- 返回错误信息而不是抛出异常
- 使用 `ToolMessage` 返回错误

### Q4: 如何添加新工具？

**步骤**：
1. 使用 `@tool` 装饰器定义新函数
2. 将新工具添加到 `TOOLS` 列表
3. 更新系统提示说明新工具

---

## 总结

在 LangGraph 中使用工具的步骤：

1. **定义工具**：使用 `@tool` 装饰器
2. **绑定工具**：使用 `llm.bind_tools(TOOLS)`
3. **创建节点**：`call_model` 和 `call_tool`
4. **条件路由**：根据 `tool_calls` 决定下一步
5. **构建工作流**：连接节点形成循环

这样，LLM 就可以自主决定调用哪些工具来完成任务，实现真正的智能体行为。

---

## 参考资源

- [LangChain Tools 文档](https://python.langchain.com/docs/modules/tools/)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- 完整示例代码：`ollama_agent_with_tools.py`

