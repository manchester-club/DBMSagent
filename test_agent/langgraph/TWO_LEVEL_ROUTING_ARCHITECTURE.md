# 两层路由架构说明

本文档描述基于 LangGraph 的**两层路由架构**，支持多个独立的测试子图（Coverage Subgraph 和 Unit Test Subgraph）。

---

## 1. 架构概述

### 1.1 设计理念

- **顶层 Supervisor**：根据用户请求决定使用哪个测试子图
- **子图路由器**：每个子图有独立的路由器，负责子图内部的 Agent 调度
- **完全独立的子图**：Coverage Subgraph 和 Unit Test Subgraph 完全分离，互不干扰
- **共享 Agent**：Code Explorer 可以被多个子图使用

### 1.2 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         START                                     │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            ▼
                  ┌───────────────────┐
                  │  Top Supervisor   │  (顶层路由：决定子图)
                  │  (top_supervisor) │
                  └─────────┬─────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Coverage      │   │ Unit Test     │   │    Summary    │
│ Subgraph      │   │ Subgraph      │   │   (summary)   │
│ Router        │   │ Router        │   │               │
│(coverage_     │   │(unit_test_    │   └───────┬───────┘
│ subgraph)     │   │ subgraph)     │           │
└───────┬───────┘   └───────┬───────┘           │
        │                   │                   │
        │  ┌────────────────┼────────────────┐ │
        │  │                │                │ │
        ▼  ▼                ▼                ▼ ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Code Explorer │   │ Code Explorer │   │               │
│(code_explorer)│   │(code_explorer)│   │               │
└───────┬───────┘   └───────┬───────┘   │               │
        │                   │           │               │
        │                   │           │               │
        ▼                   ▼           │               │
┌───────────────┐   ┌───────────────┐   │               │
│ SQL Tester    │   │ Unit Test     │   │               │
│(sql_tester)   │   │ Agent         │   │               │
└───────┬───────┘   │(unit_test_    │   │               │
        │           │ agent)         │   │               │
        │           └───────┬───────┘   │               │
        │                   │           │               │
        ▼                   ▼           │               │
┌───────────────┐   ┌───────────────┐   │               │
│ Coverage      │   │ (回到子图路由) │   │               │
│ Analyzer      │   │               │   │               │
│(coverage_     │   │               │   │               │
│ analyzer)     │   │               │   │               │
└───────┬───────┘   └───────┬───────┘   │               │
        │                   │           │               │
        │                   │           │               │
        └───────────────────┴───────────┴───────────────┘
                            │
                            ▼
                  ┌───────────────────┐
                  │    Top Supervisor │  (所有 Agent 执行完后回到顶层)
                  └─────────┬─────────┘
                            │
                            ▼
                  ┌───────────────────┐
                  │     Summary       │
                  └─────────┬─────────┘
                            │
                            ▼
                           END
```

---

## 2. 状态（State）定义

```python
# 顶层路由：决定使用哪个子图
TopLevelRoute = Literal["coverage_subgraph", "unit_test_subgraph", "__end__"]

# 覆盖率子图内部路由
CoverageRoute = Literal["sql_tester", "code_explorer", "coverage_analyzer", "__back_to_top__"]

# 单元测试子图内部路由
UnitTestRoute = Literal["unit_test_agent", "code_explorer", "__back_to_top__"]

class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]  # 对话历史
    top_level_route: TopLevelRoute  # 顶层路由结果
    subgraph_route: CoverageRoute | UnitTestRoute | Literal["__end__"]  # 子图内部路由结果
```

---

## 3. 节点说明

### 3.1 顶层节点

#### `top_supervisor_node`
- **职责**：根据用户请求决定使用哪个测试子图
- **输入**：`state["messages"]`
- **输出**：`{"top_level_route": TopLevelRoute}`
- **路由选项**：
  - `coverage_subgraph`：用户要求覆盖率测试、SQL 测试
  - `unit_test_subgraph`：用户要求单元测试、测试用例生成
  - `__end__`：任务完成，路由到 Summary

**判断逻辑**：
```python
def top_supervisor_node(state: State) -> dict:
    messages = state["messages"]
    
    # 程序化判断
    if _user_asked_unit_test(messages):
        return {"top_level_route": "unit_test_subgraph"}
    elif _user_asked_coverage(messages):
        return {"top_level_route": "coverage_subgraph"}
    
    # LLM 判断（如果程序化判断无法确定）
    # 使用 LLM 分析用户意图
    # ...
```

### 3.2 子图路由器节点

#### `coverage_subgraph_router`
- **职责**：覆盖率子图内部的路由决策
- **输入**：`state["messages"]`
- **输出**：`{"subgraph_route": CoverageRoute}`
- **路由选项**：
  - `sql_tester`：需要执行 SQL 测试
  - `code_explorer`：需要探索代码和调用图
  - `coverage_analyzer`：需要分析覆盖率、生成 SQL、查找种子
  - `__back_to_top__`：子图任务完成，回到顶层 Supervisor

**特点**：
- 类似原来的 `supervisor_node`，但只负责覆盖率相关的 Agent
- 可以多轮调用不同的 Agent，直到任务完成

#### `unit_test_subgraph_router`
- **职责**：单元测试子图内部的路由决策
- **输入**：`state["messages"]`
- **输出**：`{"subgraph_route": UnitTestRoute}`
- **路由选项**：
  - `unit_test_agent`：生成和执行单元测试
  - `code_explorer`：需要探索代码（共享 Agent）
  - `__back_to_top__`：子图任务完成，回到顶层 Supervisor

**特点**：
- 完全独立于覆盖率子图
- 有自己的路由逻辑和 Agent 集合

### 3.3 专家 Agent 节点

#### Coverage Subgraph 的 Agent
- **`code_explorer_node`**：`[Get_Code_Context, Traverse_Call_Graph]`
- **`sql_tester_node`**：`[Run_SQL_Test]`
- **`coverage_analyzer_node`**：`[Collect_Coverage, Search_Nearest_Seed, Run_SQL_Test]`

#### Unit Test Subgraph 的 Agent
- **`code_explorer_node`**：`[Get_Code_Context, Traverse_Call_Graph]`（共享）
- **`unit_test_agent_node`**：`[Get_Code_Context, Generate_Unit_Test, Run_Unit_Test]`

### 3.4 汇总节点

#### `summary_node`
- **职责**：汇总所有子图的执行结果，生成最终报告
- **输入**：`state["messages"]`（完整对话历史）
- **输出**：`{"messages": [AIMessage(...)]}`
- **特点**：接收所有子图的消息，生成统一的测试报告

---

## 4. 图结构（LangGraph）

### 4.1 节点添加

```python
# 顶层节点
builder.add_node("top_supervisor", top_supervisor_node)
builder.add_node("summary", summary_node)

# 子图路由器节点
builder.add_node("coverage_subgraph", coverage_subgraph_router)
builder.add_node("unit_test_subgraph", unit_test_subgraph_router)

# 专家 Agent 节点
builder.add_node("code_explorer", code_explorer_node)
builder.add_node("sql_tester", sql_tester_node)
builder.add_node("coverage_analyzer", coverage_analyzer_node)
builder.add_node("unit_test_agent", unit_test_agent_node)
```

### 4.2 边和路由

```python
# START → Top Supervisor
builder.add_edge(START, "top_supervisor")

# Top Supervisor → 子图路由
builder.add_conditional_edges(
    "top_supervisor",
    route_after_top_supervisor,
    {
        "coverage_subgraph": "coverage_subgraph",
        "unit_test_subgraph": "unit_test_subgraph",
        "summary": "summary",
    }
)

# Coverage Subgraph 内部路由
builder.add_conditional_edges(
    "coverage_subgraph",
    route_after_coverage_subgraph,
    {
        "sql_tester": "sql_tester",
        "code_explorer": "code_explorer",
        "coverage_analyzer": "coverage_analyzer",
        "top_supervisor": "top_supervisor",  # 回到顶层
    }
)

# Unit Test Subgraph 内部路由
builder.add_conditional_edges(
    "unit_test_subgraph",
    route_after_unit_test_subgraph,
    {
        "unit_test_agent": "unit_test_agent",
        "code_explorer": "code_explorer",
        "top_supervisor": "top_supervisor",  # 回到顶层
    }
)

# Agent 执行完后回到各自的子图路由器
builder.add_edge("sql_tester", "coverage_subgraph")
builder.add_edge("coverage_analyzer", "coverage_subgraph")
builder.add_edge("unit_test_agent", "unit_test_subgraph")

# Code Explorer 是共享的，执行完后回到顶层 Supervisor
builder.add_edge("code_explorer", "top_supervisor")

# Summary 后结束
builder.add_edge("summary", END)
```

---

## 5. 路由函数

### 5.1 顶层路由函数

```python
def route_after_top_supervisor(state: State) -> str:
    """顶层 Supervisor 的路由决策"""
    route = state.get("top_level_route", "__end__")
    if route == "__end__":
        return "summary"
    return route  # coverage_subgraph 或 unit_test_subgraph
```

### 5.2 Coverage Subgraph 路由函数

```python
def route_after_coverage_subgraph(state: State) -> str:
    """Coverage Subgraph 内部路由决策"""
    route = state.get("subgraph_route", "__back_to_top__")
    if route == "__back_to_top__":
        return "top_supervisor"
    return route  # sql_tester, code_explorer, coverage_analyzer
```

### 5.3 Unit Test Subgraph 路由函数

```python
def route_after_unit_test_subgraph(state: State) -> str:
    """Unit Test Subgraph 内部路由决策"""
    route = state.get("subgraph_route", "__back_to_top__")
    if route == "__back_to_top__":
        return "top_supervisor"
    return route  # unit_test_agent, code_explorer
```

---

## 6. 消息流向

### 6.1 Coverage Subgraph 完整流程

```
START
  ↓
Top Supervisor (决定使用 coverage_subgraph)
  ↓
Coverage Subgraph Router
  ↓
Code Explorer (探索代码)
  ↓
Top Supervisor (Code Explorer 执行完后回到顶层)
  ↓
Top Supervisor (再次路由到 coverage_subgraph)
  ↓
Coverage Subgraph Router
  ↓
Coverage Analyzer (分析覆盖率、生成 SQL)
  ↓
Coverage Subgraph Router
  ↓
SQL Tester (执行 SQL)
  ↓
Coverage Subgraph Router
  ↓
Coverage Analyzer (重新收集覆盖率)
  ↓
Coverage Subgraph Router (判断任务完成)
  ↓
Top Supervisor (__back_to_top__)
  ↓
Top Supervisor (判断所有任务完成)
  ↓
Summary
  ↓
END
```

### 6.2 Unit Test Subgraph 完整流程

```
START
  ↓
Top Supervisor (决定使用 unit_test_subgraph)
  ↓
Unit Test Subgraph Router
  ↓
Code Explorer (探索代码)
  ↓
Top Supervisor (Code Explorer 执行完后回到顶层)
  ↓
Top Supervisor (再次路由到 unit_test_subgraph)
  ↓
Unit Test Subgraph Router
  ↓
Unit Test Agent (生成单元测试)
  ↓
Unit Test Subgraph Router
  ↓
Unit Test Agent (执行单元测试)
  ↓
Unit Test Subgraph Router (判断任务完成)
  ↓
Top Supervisor (__back_to_top__)
  ↓
Top Supervisor (判断所有任务完成)
  ↓
Summary
  ↓
END
```

### 6.3 混合流程（两个子图都执行）

```
START
  ↓
Top Supervisor → Unit Test Subgraph → ... → Top Supervisor
  ↓
Top Supervisor → Coverage Subgraph → ... → Top Supervisor
  ↓
Top Supervisor (判断所有任务完成)
  ↓
Summary
  ↓
END
```

---

## 7. 关键设计点

### 7.1 子图完全独立

- **Coverage Subgraph** 和 **Unit Test Subgraph** 是完全独立的
- 每个子图有自己的路由器、Agent 集合和路由逻辑
- 子图之间不直接通信，所有通信都通过 Top Supervisor

### 7.2 Code Explorer 共享机制

- **Code Explorer** 可以被多个子图使用
- 执行完后回到 **Top Supervisor**，而不是回到各自的子图路由器
- Top Supervisor 根据上下文决定下一步路由到哪个子图

### 7.3 消息传递

- 所有消息都存储在 `state["messages"]` 中
- 子图之间的消息通过 Top Supervisor 传递
- Summary 节点可以访问所有子图的消息，生成统一报告

### 7.4 路由决策

- **顶层路由**：基于用户意图（覆盖率测试 vs 单元测试）
- **子图路由**：基于子图内部的任务状态（需要哪个 Agent）
- **结束条件**：子图路由器返回 `__back_to_top__`，Top Supervisor 判断是否所有任务完成

---

## 8. 扩展性

### 8.1 添加新子图

要添加新的子图（如 Integration Test Subgraph），需要：

1. **定义新的路由类型**：
   ```python
   IntegrationTestRoute = Literal["integration_test_agent", "code_explorer", "__back_to_top__"]
   ```

2. **更新 State**：
   ```python
   TopLevelRoute = Literal["coverage_subgraph", "unit_test_subgraph", "integration_test_subgraph", "__end__"]
   ```

3. **添加子图路由器节点**：
   ```python
   builder.add_node("integration_test_subgraph", integration_test_subgraph_router)
   ```

4. **更新顶层路由**：
   ```python
   builder.add_conditional_edges(
       "top_supervisor",
       route_after_top_supervisor,
       {
           "coverage_subgraph": "coverage_subgraph",
           "unit_test_subgraph": "unit_test_subgraph",
           "integration_test_subgraph": "integration_test_subgraph",  # 新增
           "summary": "summary",
       }
   )
   ```

5. **添加子图内部路由和 Agent**：
   ```python
   builder.add_conditional_edges(
       "integration_test_subgraph",
       route_after_integration_test_subgraph,
       {...}
   )
   builder.add_node("integration_test_agent", integration_test_agent_node)
   builder.add_edge("integration_test_agent", "integration_test_subgraph")
   ```

### 8.2 添加新 Agent

在现有子图中添加新 Agent：

1. 实现 Agent 节点函数
2. 在子图路由器中添加路由选项
3. 添加节点和边到图结构

---

## 9. 优势总结

1. **清晰的职责分离**：顶层决定策略，子图负责执行
2. **完全独立的子图**：不同测试类型互不干扰
3. **灵活的扩展性**：易于添加新的子图和 Agent
4. **共享资源**：Code Explorer 等共享 Agent 可以被多个子图使用
5. **统一的消息流**：所有消息通过 Top Supervisor 传递，便于追踪和调试
6. **统一的报告**：Summary 节点可以汇总所有子图的结果

---

## 10. 实现注意事项

1. **状态管理**：确保 `top_level_route` 和 `subgraph_route` 正确更新
2. **路由逻辑**：子图路由器需要正确判断何时返回 `__back_to_top__`
3. **消息传递**：确保所有 Agent 的消息都正确追加到 `state["messages"]`
4. **结束条件**：Top Supervisor 需要正确判断所有任务是否完成
5. **错误处理**：子图内部错误不应影响其他子图的执行

---

以上即两层路由架构的完整说明。该架构支持多个独立的测试子图，每个子图有自己独立的路由逻辑和 Agent 集合，同时通过顶层 Supervisor 实现统一协调。
