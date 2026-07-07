# Agent 信息传递与图结构文档

## 一、Agent 图结构

### 1.1 节点（Nodes）

```
START → supervisor → [sql_tester | code_explorer | coverage_analyzer | summary]
         ↑              ↓              ↓                    ↓
         └──────────────┴──────────────┴────────────────────┘
         summary → END
```

**节点列表**：
- `supervisor`: 协调者节点，负责路由决策
- `sql_tester`: SQL 测试专家节点
- `code_explorer`: 代码探索专家节点
- `coverage_analyzer`: 覆盖率分析专家节点
- `summary`: 总结报告生成节点

### 1.2 边（Edges）

#### 固定边（Fixed Edges）

```python
# 起始边
START → supervisor

# 专家节点返回边（所有专家节点执行完后都返回 supervisor）
sql_tester → supervisor
code_explorer → supervisor
coverage_analyzer → supervisor

# 结束边
summary → END
```

#### 条件边（Conditional Edges）

```python
# Supervisor 的条件路由
supervisor → [sql_tester | code_explorer | coverage_analyzer | summary]
```

**路由映射**：
- `"sql_tester"` → `sql_tester` 节点
- `"code_explorer"` → `code_explorer` 节点
- `"coverage_analyzer"` → `coverage_analyzer` 节点
- `"summary"` → `summary` 节点（当 `next_agent == "__end__"` 时）

### 1.3 路由决策逻辑（`supervisor_node`）

Supervisor 按以下优先级顺序检查并路由：

1. **循环检测**：如果同一 Agent 连续派发 3 次，直接结束（`__end__`）

2. **Code Explorer 路由**（优先级最高）：
   - 条件：`not _has_code_explorer_tool_results(messages)`
   - 说明：缺少代码信息（Get_Code_Context 或 Traverse_Call_Graph 的结果）

3. **Coverage Analyzer 路由**（初始收集）：
   - 条件：`_user_asked_coverage_or_seed(messages) and not _has_coverage_or_seed_tool_results(messages)`
   - 说明：用户要求收集覆盖率或查找种子，但还没有结果

4. **Code Explorer 路由**（为 Coverage Analyzer 提供信息）：
   - 条件：`_has_coverage_or_seed_tool_results(messages) and not _has_sql_generated(messages) and _needs_more_code_info(messages)`
   - 说明：Coverage Analyzer 需要更多代码信息（宏定义、相关函数等）

5. **Coverage Analyzer 路由**（生成 SQL）：
   - 条件：`_has_coverage_or_seed_tool_results(messages) and _count_collect_coverage(messages) >= 1 and not _has_sql_generated(messages)`
   - 说明：已收集覆盖率但还未生成 SQL，必须继续派发 Coverage Analyzer

6. **SQL Tester 路由**（执行 SQL）：
   - 条件：`_has_sql_generated(messages) and not _has_sql_executed(messages)`
   - 说明：Coverage Analyzer 已生成 SQL 但未执行

7. **SQL Tester 路由**（验证覆盖率）：
   - 条件：`_has_sql_executed(messages) and not coverage_verified_after_sql`
   - 说明：SQL 已执行但未验证覆盖率

8. **迭代或结束**：
   - 如果 `_should_iterate(messages, agent_history)`：
     - 最近是 SQL Tester → 派发 Code Explorer
     - 最近是 Code Explorer → 派发 Coverage Analyzer
     - 默认 → 派发 Code Explorer
   - 否则：结束（`__end__`）

9. **LLM 判断**（兜底）：
   - 如果以上条件都不满足，使用 LLM 根据 `SUPERVISOR_PROMPT` 判断

---

## 二、每个 Agent 接收的信息

### 2.1 Supervisor（协调者）

**接收的消息**：
```python
# 在 supervisor_node 中
sys_msg = SystemMessage(content=SUPERVISOR_PROMPT)
recent = messages[-10:] if len(messages) > 10 else messages
inp = [sys_msg] + recent
```

**消息组成**：
1. **SystemMessage**: `SUPERVISOR_PROMPT`（包含三个专家 Agent 的职责、路由规则等）
2. **最近 10 条消息**（如果消息总数 > 10）或全部消息（如果 ≤ 10）

**System Prompt 内容**：
- 三个专家 Agent 及其职责
- 标准工作流程
- 路由规则（按顺序检查）
- 判断依据

**输出**：
- `next_agent`: 路由目标（`"sql_tester"` | `"code_explorer"` | `"coverage_analyzer"` | `"__end__"`）
- `agent_history`: Agent 派发历史（用于循环检测）

---

### 2.2 Code Explorer（代码探索专家）

**接收的消息**：
```python
# 在 _run_agent_loop 中
messages = list(state["messages"])  # 完整的对话历史
inp = [SystemMessage(content=CODE_EXPLORER_SYSTEM)] + messages
```

**消息组成**：
1. **SystemMessage**: `CODE_EXPLORER_SYSTEM`
2. **完整的对话历史**（`state["messages"]`）

**System Prompt 内容**：
- 工具列表：`Get_Code_Context`, `Traverse_Call_Graph`
- 职责：获取函数源代码、分析调用关系
- 重要提示：如何构造 `start_func_id`、文件路径格式等
- 不负责覆盖率分析、SQL 测试等任务

**可用工具**：
- `Get_Code_Context`: 获取函数源代码
- `Traverse_Call_Graph`: 分析调用关系

**输出**：
- `messages`: 新增的消息列表（AIMessage + ToolMessage）

---

### 2.3 Coverage Analyzer（覆盖率分析专家）

**接收的消息**：
```python
# 在 _run_agent_loop 中
messages = list(state["messages"])  # 完整的对话历史
inp = [SystemMessage(content=COVERAGE_ANALYZER_SYSTEM)] + messages
```

**消息组成**：
1. **SystemMessage**: `COVERAGE_ANALYZER_SYSTEM`
2. **完整的对话历史**（`state["messages"]`）

**System Prompt 内容**：
- 核心目标：生成 SQL 测试用例提高代码覆盖率
- 重要限制：
  - **只能使用**：`Collect_Coverage`, `Search_Nearest_Seed`
  - **严格禁止**：`Get_Code_Context`, `Traverse_Call_Graph`, `Run_SQL_Test`
  - 如果需要更多代码信息，在回复中说明，Supervisor 会派发 Code Explorer
- 工作流程：Collect_Coverage → Search_Nearest_Seed → 基于 seed 生成 SQL → 等待 SQL Tester 执行 → Collect_Coverage 验证

**可用工具**：
- `Collect_Coverage`: 收集覆盖率数据
- `Search_Nearest_Seed`: 查找相关 SQL 种子

**输出**：
- `messages`: 新增的消息列表（AIMessage + ToolMessage）
- **强制检查**：
  - 如果用户要求查找种子但未调用 `Search_Nearest_Seed`，强制调用
  - 如果已收集覆盖率但未调用 `Search_Nearest_Seed`（如果用户要求），强制调用
  - 如果已收集覆盖率和找到种子但未生成 SQL，强制生成

---

### 2.4 SQL Tester（SQL 测试专家）

**接收的消息**：
```python
# 在 _run_agent_loop 中
messages = list(state["messages"])  # 完整的对话历史
inp = [SystemMessage(content=SQL_TESTER_SYSTEM)] + messages
```

**消息组成**：
1. **SystemMessage**: `SQL_TESTER_SYSTEM`
2. **完整的对话历史**（`state["messages"]`）

**System Prompt 内容**：
- 核心职责：执行 SQL 测试用例
- 重要限制：
  - **只能使用**：`Run_SQL_Test`, `Collect_Coverage`
  - **严格禁止**：`Get_Code_Context`, `Traverse_Call_Graph`, `Search_Nearest_Seed`
- 关键要求：
  - 看到 SQL 代码块后，必须立即调用 `Run_SQL_Test`
  - 执行 SQL 后，必须调用 `Collect_Coverage` 验证覆盖率

**可用工具**：
- `Run_SQL_Test`: 执行 SQL 测试用例
- `Collect_Coverage`: 验证覆盖率是否提升

**输出**：
- `messages`: 新增的消息列表（AIMessage + ToolMessage）
- **强制检查**：
  - 如果检测到 SQL 但未执行，强制执行
  - 如果执行了 SQL 但未验证覆盖率，强制验证

---

### 2.5 Summary（总结报告生成）

**接收的消息**：
```python
# 在 summary_node 中
filtered_messages = []  # 过滤后的消息
# ... 过滤逻辑：确保 ToolMessage 前面有对应的 AIMessage（包含 tool_calls）
recent = filtered_messages[-30:] if len(filtered_messages) > 30 else filtered_messages
inp = [SystemMessage(content=SUMMARY_PROMPT)] + recent
```

**消息组成**：
1. **SystemMessage**: `SUMMARY_PROMPT`
2. **最近 30 条过滤后的消息**（如果消息总数 > 30）或全部过滤后的消息（如果 ≤ 30）

**消息过滤规则**：
- 只保留 `HumanMessage`, `SystemMessage`, `AIMessage` 和有效的 `ToolMessage`
- `ToolMessage` 必须是对应前面 `AIMessage` 的 `tool_calls` 的响应
- 跳过孤立的 `ToolMessage`（没有对应的 `AIMessage`）

**System Prompt 内容**：
- 重要要求：必须详细、完整、准确
- 报告结构：
  1. 测试目标
  2. 源代码分析（详细）
  3. 调用关系分析（详细）
  4. 覆盖率分析（详细）
  5. SQL 种子查找（详细）
  6. SQL 测试用例生成与执行（详细）
  7. 覆盖率提升分析
  8. 工作流程总结

**输出**：
- `messages`: 包含生成的测试报告的 `AIMessage`

---

## 三、消息传递流程

### 3.1 State 结构

```python
class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]  # 累积所有消息
    next_agent: Route  # Supervisor 的路由决策
    agent_history: Annotated[List[str], lambda x, y: y]  # Agent 派发历史
```

**关键点**：
- `messages` 使用 `add_messages` 函数累积，所有 Agent 的消息都会追加到同一个列表
- 每个 Agent 都能看到完整的对话历史
- `agent_history` 用于循环检测，只保留最近 10 次派发记录

### 3.2 消息累积机制

```python
def add_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    return left + right
```

**说明**：
- 每个 Agent 节点返回的 `messages` 会追加到 `state["messages"]`
- 下一个 Agent 节点会看到之前所有 Agent 的消息
- 这确保了上下文传递的连续性

### 3.3 工具调用流程

在 `_run_agent_loop` 中：

1. **LLM 调用**：
   ```python
   response = llm_with_tools.invoke(inp)  # 包含 SystemMessage + 完整对话历史
   ```

2. **工具调用检测**：
   ```python
   if not getattr(response, "tool_calls", None):
       break  # 没有工具调用，结束循环
   ```

3. **工具执行**：
   ```python
   for tc in response.tool_calls:
       tool_func = find_tool_by_name(tc["name"])
       result = tool_func.invoke(tc["args"])
       tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"], name=tc["name"])
   ```

4. **消息更新**：
   ```python
   inp = inp + [response] + tool_msgs  # 将 AIMessage 和 ToolMessage 添加到输入
   ```

5. **循环**：最多执行 `MAX_TOOL_ROUNDS = 5` 轮工具调用

---

## 四、关键辅助函数

### 4.1 路由判断函数

- `_has_code_explorer_tool_results(messages)`: 检查是否有 Code Explorer 的工具结果
- `_has_coverage_or_seed_tool_results(messages)`: 检查是否有 Coverage Analyzer 的工具结果
- `_has_sql_generated(messages)`: 检查是否生成了 SQL（且未被执行）
- `_has_sql_executed(messages)`: 检查 SQL 是否已被执行
- `_count_collect_coverage(messages)`: 统计 `Collect_Coverage` 的调用次数
- `_needs_more_code_info(messages)`: 判断 Coverage Analyzer 是否需要更多代码信息
- `_should_iterate(messages, agent_history)`: 判断是否应该继续迭代
- `_check_coverage_improvement(messages)`: 检查覆盖率是否提升

### 4.2 提取函数

- `_extract_target_func_id(messages)`: 从对话历史中提取目标函数 ID
- `_user_asked_coverage_or_seed(messages)`: 检查用户是否要求收集覆盖率或查找种子

---

## 五、执行流程图

```
START
  ↓
supervisor (检查路由条件)
  ↓
  ├─→ code_explorer (获取代码信息)
  │     ↓
  │     supervisor
  │
  ├─→ coverage_analyzer (收集覆盖率、查找种子、生成 SQL)
  │     ↓
  │     supervisor
  │
  └─→ sql_tester (执行 SQL、验证覆盖率)
        ↓
        supervisor
        ↓
        ├─→ 如果覆盖率未提升 → code_explorer / coverage_analyzer（迭代）
        └─→ 如果覆盖率已提升或达到限制 → summary → END
```

---

## 六、总结

### 6.1 信息传递特点

1. **完整上下文**：每个 Agent 都能看到完整的对话历史（除了 Summary 只看到最近 30 条过滤后的消息）
2. **System Prompt 隔离**：每个 Agent 有独立的 System Prompt，明确其职责和可用工具
3. **工具结果可见**：所有 Agent 的工具执行结果都会添加到 `state["messages"]`，后续 Agent 可以看到

### 6.2 路由特点

1. **优先级路由**：Supervisor 按固定优先级检查条件，确保工作流程的合理性
2. **循环检测**：通过 `agent_history` 检测同一 Agent 连续派发 3 次，避免无限循环
3. **强制检查**：Coverage Analyzer 和 SQL Tester 节点都有强制检查逻辑，确保关键步骤不遗漏

### 6.3 图结构特点

1. **星型结构**：所有专家节点都返回 Supervisor，由 Supervisor 统一路由
2. **条件路由**：Supervisor 根据消息状态动态决定下一个节点
3. **终止节点**：Summary 节点是唯一的终止节点（除了异常情况）
