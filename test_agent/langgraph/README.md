# LangGraph 实现目录

本目录用于实现基于 LangGraph 的代码，包括工作流编排和智能体开发。

## 目录结构

```
langgraph/
├── README.md                  # 本文件
├── requirements.txt           # Python依赖
├── basic_example.py          # LangGraph基础示例
└── neo4j_agent_example.py    # LangGraph + Neo4j集成示例
```

## 依赖安装

```bash
pip install -r requirements.txt
```

## 示例代码

### 1. 基础示例 (`basic_example.py`)

演示LangGraph的基本用法：
- 创建状态机
- 定义节点和边
- 条件分支
- 工作流执行

运行方式：
```bash
python3 basic_example.py
```

### 2. Neo4j智能体示例 (`neo4j_agent_example.py`)

演示如何将LangGraph与Neo4j集成：
- 创建智能体工作流
- 查询Neo4j知识图谱
- 处理函数调用关系
- 生成结构化回复

运行方式：
```bash
python3 neo4j_agent_example.py
```

**注意**: 需要确保Neo4j服务正在运行（默认地址: `bolt://173.0.69.2:7687`）

### 3. Ollama智能体 (`ollama_agent.py`)

基础智能体实现，使用硬编码的工具调用：
- **自然语言理解**: 使用Ollama解析用户意图
- **知识图谱查询**: 根据意图查询Neo4j获取代码信息
- **智能回复生成**: 使用Ollama生成自然语言回复
- **固定工作流**: 工具调用由代码逻辑决定

运行方式：
```bash
python3 ollama_agent.py
```

### 4. Ollama智能体 - Tool机制版 (`ollama_agent_with_tools.py`) ⭐

**推荐使用** - 使用LangChain的@tool装饰器机制：
- **LLM自主决策**: LLM根据用户查询自主决定调用哪些工具
- **工具装饰器**: 使用`@tool`装饰器定义工具函数
- **灵活组合**: 支持一次查询调用多个工具
- **标准化**: 符合LangChain的tool calling规范

**工具列表**:
1. `query_function_info` - 查询函数基本信息
2. `query_function_callers` - 查询函数的调用者
3. `query_function_callees` - 查询函数的被调用者
4. `search_functions_by_keyword` - 根据关键词搜索函数
5. `get_call_graph` - 获取函数的调用图

**工作流程**:
```
用户输入 → LLM思考 → 决定调用工具 → 执行工具 → LLM生成回复
```

运行方式：
```bash
python3 ollama_agent_with_tools.py
```

**配置要求**:
- Neo4j服务运行中（默认: `bolt://173.0.69.2:7687`）
- Ollama服务运行中，并已安装模型（如 `qwen3:30b-a3b`）
- 模型会自动检测，优先使用 `qwen3:30b-a3b` 或 `qwen3:32b`

**使用示例**:
```
👤 您: 查询函数 date2timestamptz_opt_overflow 的调用关系
👤 您: date2timestamptz 函数在哪里定义？它调用了哪些函数？
👤 您: 查找包含 timestamp 的函数，并显示它们的调用图
```

**优势**:
- ✅ LLM自主决定工具调用，无需预定义意图
- ✅ 支持多工具组合使用
- ✅ 更灵活，适应各种查询场景
- ✅ 符合LangChain最佳实践

## 核心概念

### StateGraph
LangGraph的核心是状态图（StateGraph），它允许你：
- 定义状态结构（TypedDict）
- 添加节点（处理函数）
- 连接节点（边和条件边）
- 编译并执行工作流

### 状态管理
使用 `Annotated` 和 `add_messages` 来管理消息列表：
```python
from typing import Annotated
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]
```

### 节点函数
每个节点函数接收状态并返回更新后的状态：
```python
def my_node(state: State) -> State:
    # 处理逻辑
    return {"key": "value"}
```

### 条件边
使用条件函数决定下一步：
```python
def should_continue(state: State) -> str:
    if condition:
        return "next_node"
    return "end"
```

## 教程文档

### LangGraph Tool 使用教程 (`LangGraph_Tool_教程.md`) 📚

详细教程，介绍如何在 LangGraph 中定义和使用工具：
- 使用 `@tool` 装饰器定义工具
- 绑定工具到 LLM
- 在 LangGraph 工作流中集成工具
- 处理工具调用和结果
- 完整代码示例和最佳实践

阅读教程：
```bash
cat LangGraph_Tool_教程.md
```

## 下一步

- 集成LLM（如Ollama）进行自然语言处理
- 实现更复杂的智能体工作流
- 添加持久化检查点
- 实现流式输出

