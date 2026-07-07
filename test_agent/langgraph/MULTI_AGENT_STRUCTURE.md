# Coverage Multi-Agent 框架说明（结合代码）

本文档描述基于 LangGraph 的 **Coverage Multi-Agent** 架构，并对照 `coverage_multi_agent.py` 与 `nodes/` 中的具体实现。

---

## 1. 概述

- **主入口**：`coverage_multi_agent.py`
- **工具实现**：`nodes/` 下各工具模块，经 `nodes/__init__.py` 统一导出
- **能力**：Supervisor 协调三个专家 Agent（SQL Tester、Code Explorer、Coverage Analyzer），按需调用工具，多轮对话后由 Summary 节点收尾

---

## 2. 文件与目录结构

```
test_agent/langgraph/
├── coverage_multi_agent.py      # Multi-Agent 图、节点、路由、run_test、main
├── coverage_agent.py            # 单 Agent（chatbot + tools），无 Supervisor
├── chat_bot.py                  # 通用聊天 + Tavily 示例
├── nodes/
│   ├── __init__.py              # 导出 Run_SQL_Test, Collect_Coverage, Get_Code_Context, Search_Nearest_Seed, Traverse_Call_Graph
│   ├── utils.py                 # load_nodes, load_edges, normalize_func_id, get_call_graphs, get_seed_indices；默认路径、缓存
│   ├── run_sql_test.py          # Run_SQL_Test
│   ├── collect_coverage.py      # Collect_Coverage
│   ├── get_code_context.py      # Get_Code_Context
│   ├── search_nearest_seed.py   # Search_Nearest_Seed
│   └── traverse_call_graph.py   # Traverse_Call_Graph
└── MULTI_AGENT_STRUCTURE.md     # 本说明
```

---

## 3. 状态（State）

**定义**（`coverage_multi_agent.py`）：

```python
Route = Literal["sql_tester", "code_explorer", "coverage_analyzer", "__end__"]

class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]  # 对话历史，add_messages 归约
    next_agent: Route   # Supervisor 的本次路由结果
```

- `messages`：`HumanMessage`、`AIMessage`、`ToolMessage` 等，由 `add_messages` 归约，新消息**追加**。
- `next_agent`：仅 Supervisor 写入；取值为 `sql_tester` | `code_explorer` | `coverage_analyzer` | `__end__`。

---

## 4. 图结构（LangGraph）

### 4.1 节点与边（对应代码）

图在 `coverage_multi_agent.py` 中构建：

```python
builder.add_node("supervisor", supervisor_node)
builder.add_node("summary", summary_node)
builder.add_node("sql_tester", sql_tester_node)
builder.add_node("code_explorer", code_explorer_node)
builder.add_node("coverage_analyzer", coverage_analyzer_node)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", route_after_supervisor, {
    "sql_tester": "sql_tester",
    "code_explorer": "code_explorer",
    "coverage_analyzer": "coverage_analyzer",
    "summary": "summary",
})
builder.add_edge("sql_tester", "supervisor")
builder.add_edge("code_explorer", "supervisor")
builder.add_edge("coverage_analyzer", "supervisor")
builder.add_edge("summary", END)
```

### 4.2 流程图

```
                    START
                       │
                       ▼
                 ┌─────────────┐
                 │  supervisor │
                 └──────┬──────┘
                        │
    ┌───────────────────┼───────────────────┬────────────┐
    ▼                   ▼                   ▼            ▼
sql_tester      code_explorer     coverage_analyzer   summary
    │                   │                   │              │
    └───────────────────┴───────────────────┘              │
                        │                                  │
                        │  ( 回到 supervisor )               ▼
                        └────────────────────────────►   END
```

### 4.3 路由逻辑

- **`route_after_supervisor`**（约 L284–286）：  
  - 读 `state["next_agent"]`，若为 `__end__` 则返回 `"summary"`，否则返回对应专家节点名。  
- **条件边**：  
  - `sql_tester` / `code_explorer` / `coverage_analyzer` / `summary` 四个出口，由 `route_after_supervisor` 的返回值决定。  
- **固定边**：  
  - 三个专家执行完后**一律**回到 `supervisor`；`summary` 后到 `END`。

---

## 5. Supervisor 节点（`supervisor_node`）

### 5.1 职责

- 根据当前 `messages` 决定下一步：派发某个专家，或结束（`__end__` → summary）。
- 输出 `next_agent`，并打印 `[Supervisor] 派发 → ...`。

### 5.2 程序化强制规则（先于 LLM）

在调用 LLM 前，有如下**硬编码**判断（约 L164–178）：

```python
if (
    _user_asked_coverage_or_seed(messages)           # 用户提到 覆盖率/种子/Collect_Coverage/Search_Nearest_Seed
    and _has_code_explorer_tool_results(messages)    # 已有 Get_Code_Context / Traverse_Call_Graph 的 ToolMessage
    and not _has_coverage_or_seed_tool_results(messages)  # 尚未有 Collect_Coverage / Search_Nearest_Seed 的 ToolMessage
):
    route = "coverage_analyzer"   # 强制派 Coverage Analyzer
```

- **目的**：用户明确要求覆盖率/种子时，在已有代码探索结果的前提下，**必须**先跑 Coverage Analyzer，再考虑 FINISH，避免漏跑。
- **辅助函数**：  
  - `_user_asked_coverage_or_seed`：扫 `HumanMessage` 内容。  
  - `_has_code_explorer_tool_results` / `_has_coverage_or_seed_tool_results`：扫 `ToolMessage` 的 `name`。

### 5.3 LLM 路由（未触发强制时）

- 使用 `llm_supervisor`（无 bind_tools），prompt 为 `SUPERVISOR_PROMPT`。  
- 输入：`[SystemMessage(SUPERVISOR_PROMPT)] + messages[-10:]`。  
- 输出解析：`_parse_route(content)` 从回复中匹配 `SQL_TESTER` | `CODE_EXPLORER` | `COVERAGE_ANALYZER` | `FINISH`，映射为 `next_agent`。

### 5.4 返回值

```python
return {"next_agent": route}
```

仅更新 `next_agent`；`messages` 不变。

---

## 6. 专家节点与 `_run_agent_loop`

### 6.1 三个专家节点

| 节点             | 实现函数           | 绑定工具                                                                 |
|------------------|--------------------|--------------------------------------------------------------------------|
| `sql_tester`     | `sql_tester_node`  | `[Run_SQL_Test]`                                                        |
| `code_explorer`  | `code_explorer_node`| `[Get_Code_Context, Traverse_Call_Graph]`                               |
| `coverage_analyzer` | `coverage_analyzer_node` | `[Collect_Coverage, Search_Nearest_Seed, Run_SQL_Test]`          |

均通过 `_run_agent_loop` 实现，仅 `llm`、`tools`、`agent_name`、`system_prompt` 不同。

### 6.2 `_run_agent_loop` 逻辑（约 L193–246）

1. **输入**：`state`（含 `messages`）、`llm_with_tools`、`tools`、`agent_name`、可选 `system_prompt`。  
2. **初始化**：  
   - `inp = [SystemMessage(system_prompt)] + messages`（有 system_prompt 时），否则 `inp = messages`。  
   - `to_append` 用于收集本专家产生的 **新增** 消息。  
3. **多轮循环**（最多 `MAX_TOOL_ROUNDS = 5`）：  
   - `response = llm_with_tools.invoke(inp)`。  
   - 若 **无** `tool_calls`：`to_append.append(response)` 后 **跳出**。  
   - 若有 `tool_calls`：  
     - 打印 `[<agent_name>] 工具调用` 及各工具名、参数。  
     - `ToolNode(tools).invoke(...)` 执行，得到 `tool_msgs`。  
     - `to_append += [response] + tool_msgs`。  
     - 对每个 `ToolMessage` 打印 `[<agent_name>] <tool_name> 返回:` 及**完整内容**（不截断）。  
     - `inp = inp + [response] + tool_msgs`，继续下一轮。  
4. **最后一条 AIMessage**：若存在且 `content` 非空，打印 `[<agent_name>] 回复:` 及**完整文本**（不截断，保留 `</think>` 等标签）。  
5. **返回**：`{"messages": to_append}`，由 `add_messages` 追加到全局 `messages`。

### 6.3 Coverage Analyzer 的程序化强制机制

**问题**：LLM 可能生成 SQL 但忘记调用 `Run_SQL_Test`。

**解决方案**（约 L416–435）：
- 在 `coverage_analyzer_node` 中，`_run_agent_loop` 返回后检查：
  - 最后一条 `AIMessage` 的 `content` 是否包含 SQL 关键词（如 ````sql`、`select`）
  - 整个对话历史中是否**没有** `Run_SQL_Test` 的 `ToolMessage`
- 如果满足条件，**自动注入**一个 `HumanMessage` 强制要求调用 `Run_SQL_Test`，并重新调用 `_run_agent_loop`。
- 这确保了 SQL 一定会被执行，从而创建 SQL 节点。

### 6.3 专家系统提示

- **Code Explorer**（`CODE_EXPLORER_SYSTEM`）：  
  - `Get_Code_Context` 只传 `query_name`、`query_type`。  
  - `Traverse_Call_Graph` 的 `start_func_id` 必须用 `Get_Code_Context` 返回的 `name`、`file_path`、`line_number` 构造 `function:{name}@{file_path}:{line_number}`，且 `file_path` 与返回值完全一致。  
- **Coverage Analyzer**（`COVERAGE_ANALYZER_SYSTEM`）：  
  - 只传 `target_func_id` 等必要参数，不传 `nodes_file`。  
  - `target_func_id` 同样用 `Get_Code_Context` 的 name/file_path/line_number 构造。  
  - **重要流程**：必须按顺序执行：
    1. `Collect_Coverage`（初始收集）
    2. 根据覆盖率分析生成 SQL（LLM 生成）
    3. `Run_SQL_Test`（执行 SQL，参数为 `sql_script`，这会创建 SQL 节点）
    4. `Collect_Coverage`（立即重新收集以验证改进）
    5. `Search_Nearest_Seed`（查找已创建的 SQL 节点）
  - **程序化强制**：如果 LLM 生成了 SQL 但未调用 `Run_SQL_Test`，系统会自动注入提示强制执行。

---

## 7. Summary 节点（`summary_node`）

- **输入**：`state["messages"]`，取最近 `messages[-30:]`（完整对话历史）。  
- **调用**：`llm_supervisor` + `SUMMARY_PROMPT`，要求根据完整对话历史生成**结构化测试报告**。  
- **报告结构**（`SUMMARY_PROMPT` 要求）：
  - 测试目标
  - 源代码分析
  - 调用关系分析
  - 覆盖率分析
  - SQL 种子查找
  - 覆盖率改进方案
- **输出格式**：报告内容用 `========` 分隔，便于阅读。  
- **返回**：`{"messages": [AIMessage(content=...)]}`。  
- **打印**：`[Summary] ...`（在 `coverage_multi_agent.py` 的 `summary_node` 内已实现）。

---

## 8. 运行入口与 `run_test`

### 8.1 `run_test`（约 L329–348）

```python
def run_test(
    user_input: str,
    thread_id: str = "multi_agent_test",
    config: Optional[RunnableConfig] = None,
    recursion_limit: int = 25,
) -> List[BaseMessage]:
```

- **config 构建**：  
  - `cfg = dict(config) if config else {}`。  
  - `cfg["recursion_limit"] = recursion_limit`。  
  - `configurable = cfg.get("configurable")`；若非常 dict，则 `configurable = {}` 并 `cfg["configurable"] = configurable`。  
  - `configurable["thread_id"] = thread_id`。  
- **初始状态**：  
  - `initial = {"messages": [HumanMessage(content=user_input)], "next_agent": "__end__"}`。  
- **调用**：`app.invoke(initial, config=cast(RunnableConfig, cfg))`。  
- **返回**：`final["messages"]`。

### 8.2 `main`（`if __name__ == "__main__"`）

- **默认**：跑 EncodeSpecialDate 测试；  
  - `test_prompt` 要求对 `EncodeSpecialDate` 做 Get_Code_Context、Traverse_Call_Graph、Collect_Coverage、Search_Nearest_Seed。  
  - 先打印 `[User]` + 提示，再 `run_test(test_prompt, thread_id="encode_special_date_test")`，最后打印 **对话记录 (Messages)**：每条带 `[User]` / `[Assistant]` / `[Tool: <name>]` 前缀。  
- **交互模式**（`--interactive`）：  
  - 循环 `input("\n[User] ")`，`run_test(line, thread_id="multi_agent_interactive")`；`q`/`quit`/`exit` 退出。

---

## 9. 输出格式约定

- **`[Supervisor] 派发 → <目标>`**：Supervisor 每次路由时打印。  
- **`[<Agent>] 工具调用`** + **`· <tool> 参数: {...}`**：专家发起工具调用时。  
- **`[<Agent>] <tool> 返回:`** + 内容：每个 ToolMessage 的反馈（**完整输出，不截断**）。  
- **`[<Agent>] 回复:`** + 文本：专家最后一轮无工具调用的 AIMessage 文本（**完整输出，不截断，保留所有标签如 `</think>`**）。  
- **`[Summary] ...`**：Summary 节点输出的结构化测试报告（用 `========` 分隔）。  
- **`[User]`**：用户输入（main / 交互模式）。

**注意**：所有输出都不截断，确保完整信息可见。

---

## 10. `nodes/` 工具与 `utils`

### 10.1 工具一览

| 工具                  | 模块                    | 主要用途 |
|-----------------------|-------------------------|----------|
| `Run_SQL_Test`        | `nodes.run_sql_test`    | 执行 SQL，依赖 `ai_sql_validator.DatabaseExecutor` |
| `Get_Code_Context`    | `nodes.get_code_context`| 按名称/类型查函数或宏源码 |
| `Traverse_Call_Graph` | `nodes.traverse_call_graph` | 按方向/深度遍历调用图 |
| `Collect_Coverage`    | `nodes.collect_coverage`| gcov 收集覆盖率，更新节点等 |
| `Search_Nearest_Seed` | `nodes.search_nearest_seed` | BFS 找最近种子 SQL |

### 10.2 `utils`（`nodes/utils.py`）

- **路径**：`DEFAULT_NODES_FILE`、`DEFAULT_RELATIONS_FILE`、`DEFAULT_POSTGRESQL_SRC_DIR`、`DEFAULT_PIN_LOG_DIR`。  
- **加载与缓存**：`load_nodes`、`load_edges`；`get_call_graphs`（构建 call/reverse_call/uses_macro/includes）；`get_seed_indices`（构建 reverse_call、function_paths、path_sqls）。  
- **通用**：`normalize_func_id` 等。  
- 各工具在调用图/种子相关逻辑时，对可能为 `None` 的 dict 使用 `x or {}`，避免类型错误。

### 10.3 SQL 节点创建机制与数据流

#### 10.3.1 SQL 节点的动态创建

**重要**：SQL 节点不是预先存在的，而是通过工具动态创建的。

1. **数据源**：
   - `postgresql_relations.json` 包含 `sql_executes_path` 边（约 18998 条），这些边引用了 SQL ID（如 `sql:847a9658@partition_join#009658`）
   - 这些 SQL ID 表示“某个执行路径关联了某个 SQL”，但**对应的 SQL 节点尚未创建**

2. **SQL 节点创建时机**：
   - `Collect_Coverage` 在分析覆盖率改进时，会调用 `create_or_update_sql_node` 创建 SQL 节点
   - `Run_SQL_Test` 执行 SQL 后也可能创建 SQL 节点
   - SQL 节点创建后会被写入到 `postgresql_nodes.json` 文件中

3. **`Search_Nearest_Seed` 的行为**：
   - 该工具从 `path_sqls`（由 `sql_executes_path` 边构建）中查找 SQL ID
   - 然后尝试在 `postgresql_nodes.json` 和 `pin_log_nodes.json` 中查找对应的 SQL 节点
   - **如果 SQL 节点尚未创建**，工具会返回错误，并提示需要先通过 `Collect_Coverage` 或 `Run_SQL_Test` 创建 SQL 节点

#### 10.3.2 数据流示例

```
1. relations 文件中有引用：
   sql_executes_path: sql:abc123@FunctionName#001 → path:000001

2. 但 nodes 文件中没有对应的 SQL 节点：
   postgresql_nodes.json: { "nodes": { ... } }  # 没有 sql:abc123@FunctionName#001

3. 当 Coverage Analyzer 执行时：
   - Collect_Coverage 分析覆盖率
   - 生成 SQL 来改进覆盖率
   - Run_SQL_Test 执行 SQL
   - create_or_update_sql_node 创建 SQL 节点并写入 nodes 文件

4. 之后 Search_Nearest_Seed 才能找到这些 SQL 节点
```

#### 10.3.3 注意事项

- **`Search_Nearest_Seed` 主要用于查找已创建的 SQL 节点**：如果 relations 中引用的 SQL ID 对应的节点尚未创建，工具会返回错误
- **SQL 节点的创建是覆盖率改进流程的一部分**：Coverage Analyzer 应该先收集覆盖率，生成 SQL，执行 SQL，然后 SQL 节点会被创建
- **多文件支持**：`Search_Nearest_Seed` 会同时检查 `postgresql_nodes.json` 和 `pin_log_nodes.json` 两个文件

---

## 11. 运行方式

```bash
cd /path/to/test_agent/langgraph

# 默认：EncodeSpecialDate 测试
python coverage_multi_agent.py

# 交互式多轮
python coverage_multi_agent.py --interactive
```

---

## 12. 流程小结（EncodeSpecialDate 示例）

1. **START** → **supervisor**：根据用户请求决策；若未触发强制规则，则用 LLM 路由。  
2. **code_explorer**：  
   - Get_Code_Context("EncodeSpecialDate", "FUNCTION") → 取 `file_path`、`line_number`、`name`。  
   - Traverse_Call_Graph(Upstream, …) 使用 `function:...@file_path:line_number`。  
   - 多轮工具后可再产生一段回复。  
3. **supervisor**：  
   - 若用户要求覆盖率/种子、已有代码探索结果、尚无覆盖率/种子结果 → **强制** `coverage_analyzer`。  
   - 否则由 LLM 决定下一步。  
4. **coverage_analyzer**：  
   - Collect_Coverage（收集覆盖率）  
   - 根据覆盖率分析生成 SQL（LLM 生成）  
   - Run_SQL_Test（执行生成的 SQL，这会创建 SQL 节点）  
   - Collect_Coverage（重新收集覆盖率以验证改进）  
   - Search_Nearest_Seed（查找已创建的 SQL 节点作为种子）  
5. **supervisor**：  
   - 若任务已满足 → `__end__` → **summary**。  
6. **summary**：  
   - 生成结构化测试报告（包含测试目标、源代码分析、调用关系分析、覆盖率分析、SQL 种子查找、覆盖率改进方案等） → **END**。

以上即当前 Coverage Multi-Agent 框架的结构与实现要点，均对应 `coverage_multi_agent.py` 及 `nodes/` 中的实际代码。
