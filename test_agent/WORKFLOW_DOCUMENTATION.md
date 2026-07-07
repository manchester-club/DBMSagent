# Coverage Multi-Agent 系统完整流程文档

## 系统架构

### Agent 组成

1. **Supervisor（协调者）**
   - 职责：解析用户请求，路由到合适的专家 Agent
   - 工具：无（仅负责路由决策）

2. **Code Explorer（代码探索者）**
   - 职责：获取源代码和调用关系
   - 工具：
     - `Get_Code_Context`：获取函数源代码
     - `Traverse_Call_Graph`：遍历函数调用关系

3. **Coverage Analyzer（覆盖率分析者）**
   - 职责：收集覆盖率、查找 SQL 种子、生成 SQL 测试用例
   - 工具：
     - `Collect_Coverage`：收集函数覆盖率
     - `Search_Nearest_Seed`：查找相关的 SQL 种子

4. **SQL Tester（SQL 测试者）**
   - 职责：执行 SQL 测试用例
   - 工具：
     - `Run_SQL_Test`：执行 SQL 测试用例

## 完整工作流程

### 1. 初始化阶段

```
用户输入 → Supervisor 接收 → 创建初始状态
```

**初始状态：**
```python
{
    "messages": [HumanMessage(content=user_input)],
    "next_agent": "__end__",
    "agent_history": []
}
```

### 2. Supervisor 路由决策

Supervisor 按照以下优先级顺序检查并路由：

#### 路由逻辑（优先级从高到低）

**优先级 1：Code Explorer**
- **条件**：`not _has_code_explorer_tool_results(messages)`
- **说明**：如果还没有 Code Explorer 的工具调用结果，派发到 Code Explorer

**优先级 2：Coverage Analyzer（第一次）**
- **条件**：`_user_asked_coverage_or_seed(messages) and not _has_coverage_or_seed_tool_results(messages)`
- **说明**：如果用户要求了覆盖率或种子查找，但还没有 Coverage Analyzer 的工具调用结果，派发到 Coverage Analyzer

**优先级 3：SQL Tester**
- **条件**：`_has_sql_generated(messages) and not _has_sql_executed(messages)`
- **说明**：如果 Coverage Analyzer 生成了 SQL 但还没有执行，派发到 SQL Tester

**优先级 4：Coverage Analyzer（第二次）**
- **条件**：`_has_sql_executed(messages) and _count_collect_coverage(messages) < 2`
- **说明**：如果 SQL 已经执行，但还没有验证覆盖率（Collect_Coverage 调用次数 < 2），派发到 Coverage Analyzer

**优先级 5：结束检查**
- **条件**：Coverage Analyzer 已经完成了基本任务（收集覆盖率、查找种子）但没有生成 SQL，且最近已经派发过 Coverage Analyzer
- **说明**：如果已经尝试过但没有生成 SQL，直接结束流程

**优先级 6：LLM 判断**
- **条件**：其他所有情况
- **说明**：使用 LLM 根据对话历史判断下一步应该派发到哪个 Agent

### 3. 循环检测机制

**检测逻辑：**
- 使用 `agent_history` 记录 Agent 派发历史
- 如果同一个 Agent 连续派发 3 次，自动结束流程，避免无限循环

**实现：**
```python
if len(agent_history) >= 3:
    last_three = agent_history[-3:]
    if last_three[0] == last_three[1] == last_three[2]:
        route = "__end__"  # 结束流程
```

### 4. Code Explorer 工作流程

```
Supervisor 派发 → Code Explorer
    ↓
调用 Get_Code_Context 获取源代码
    ↓
调用 Traverse_Call_Graph 遍历调用关系
    ↓
返回分析结果
    ↓
回到 Supervisor
```

**工具调用规则：**
- 最多调用 5 轮工具（`MAX_TOOL_ROUNDS = 5`）
- 如果没有工具调用，结束当前 Agent 的执行

### 5. Coverage Analyzer 工作流程

#### 第一次调用（收集覆盖率 + 查找种子 + 生成 SQL）

```
Supervisor 派发 → Coverage Analyzer
    ↓
调用 Collect_Coverage 收集覆盖率
    ↓
（如果用户要求）调用 Search_Nearest_Seed 查找 SQL 种子
    ↓
分析覆盖率数据，生成 SQL 测试用例（文本形式）
    ↓
返回结果（包含 SQL 代码块）
    ↓
回到 Supervisor
```

**强制检查：**
- 如果用户要求了 `Search_Nearest_Seed` 但没有调用，强制要求调用
- 如果 SQL 已经执行但还没有验证覆盖率，强制要求验证

#### 第二次调用（验证覆盖率）

```
Supervisor 派发 → Coverage Analyzer
    ↓
调用 Collect_Coverage 验证覆盖率提升
    ↓
返回验证结果
    ↓
回到 Supervisor
```

### 6. SQL Tester 工作流程

```
Supervisor 派发 → SQL Tester
    ↓
从对话历史中提取 SQL 测试用例（查找 ```sql 代码块）
    ↓
调用 Run_SQL_Test 执行 SQL
    ↓
返回执行结果（成功/失败/错误信息）
    ↓
回到 Supervisor
```

**重要限制：**
- **只执行 SQL，不生成 SQL**
- **不要分析或改进 SQL**
- **只从对话历史中提取并执行已有的 SQL**

**强制检查：**
- 如果检测到 SQL 但未执行，强制要求执行

### 7. 状态转换图

```
START
  ↓
Supervisor
  ↓
  ├─→ Code Explorer ──┐
  │                    │
  ├─→ Coverage Analyzer (第一次) ──┐
  │                                 │
  ├─→ SQL Tester ──────────────────┤
  │                                 │
  ├─→ Coverage Analyzer (第二次) ──┤
  │                                 │
  └─→ END ←─────────────────────────┘
```

### 8. 完整执行示例

**用户输入：**
```
请分析 EncodeSpecialDate 函数：
1) 用 Get_Code_Context 获取其源代码
2) 用 Traverse_Call_Graph 向上遍历调用关系
3) 用 Collect_Coverage 收集覆盖率、用 Search_Nearest_Seed 查找相关 SQL 种子
```

**执行流程：**

```
1. Supervisor → Code Explorer
   - Get_Code_Context: 获取源代码
   - Traverse_Call_Graph: 遍历调用关系
   - 返回分析结果

2. Supervisor → Coverage Analyzer (第一次)
   - Collect_Coverage: 收集覆盖率（85.71%）
   - Search_Nearest_Seed: 查找 SQL 种子
   - 生成 SQL 测试用例（文本形式）
   - 返回结果（包含 SQL 代码块）

3. Supervisor → SQL Tester
   - 从对话历史中提取 SQL
   - Run_SQL_Test: 执行 SQL
   - 返回执行结果

4. Supervisor → Coverage Analyzer (第二次)
   - Collect_Coverage: 验证覆盖率提升
   - 返回验证结果

5. Supervisor → END
   - 生成最终报告
```

## 关键函数说明

### 辅助函数

1. **`_has_code_explorer_tool_results(messages)`**
   - 检查是否有 Code Explorer 的工具调用结果
   - 检查 `Get_Code_Context` 或 `Traverse_Call_Graph` 的 ToolMessage

2. **`_user_asked_coverage_or_seed(messages)`**
   - 检查用户是否要求了覆盖率或种子查找
   - 检查消息中是否包含相关关键词

3. **`_has_coverage_or_seed_tool_results(messages)`**
   - 检查是否有 Coverage Analyzer 的工具调用结果
   - 检查 `Collect_Coverage` 或 `Search_Nearest_Seed` 的 ToolMessage

4. **`_has_sql_generated(messages)`**
   - 检查 Coverage Analyzer 是否生成了 SQL 测试用例
   - 检查消息中是否包含 SQL 代码块（```sql）
   - 排除 SQL Tester 的分析内容

5. **`_has_sql_executed(messages)`**
   - 检查 SQL 是否已被执行
   - 检查是否有 `Run_SQL_Test` 的 ToolMessage

6. **`_count_collect_coverage(messages)`**
   - 统计 `Collect_Coverage` 的调用次数
   - 用于判断是否需要第二次验证覆盖率

## 错误处理

### 1. 循环检测
- 如果同一个 Agent 连续派发 3 次，自动结束流程
- 避免无限循环

### 2. 工具调用失败
- 每个 Agent 最多调用 5 轮工具
- 如果工具调用失败，继续执行下一轮或结束当前 Agent

### 3. 强制检查
- Code Explorer：无强制检查
- Coverage Analyzer：强制调用 `Search_Nearest_Seed`（如果用户要求），强制验证覆盖率（如果 SQL 已执行）
- SQL Tester：强制执行 SQL（如果检测到 SQL 但未执行）

## 状态管理

### State 结构

```python
class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]  # 对话消息列表
    next_agent: Route  # 下一个要派发的 Agent
    agent_history: Annotated[List[str], lambda x, y: y]  # Agent 派发历史
```

### 状态更新

- **messages**：每次 Agent 执行后，添加新的消息（AIMessage、ToolMessage）
- **next_agent**：Supervisor 根据路由逻辑决定下一个 Agent
- **agent_history**：每次派发 Agent 时，添加到历史记录中（最多保留 10 次）

## 工具说明

### Get_Code_Context
- **功能**：获取函数或文件的源代码
- **参数**：`query_name`（函数名或文件名）、`query_type`（FUNCTION 或 FILE）
- **返回**：源代码、文件路径、行号等信息

### Traverse_Call_Graph
- **功能**：遍历函数调用关系
- **参数**：`start_func_id`（起始函数 ID）、`direction`（Upstream/Downstream）、`max_depth`（最大深度）
- **返回**：调用关系树、总函数数、最大深度等

### Collect_Coverage
- **功能**：收集函数的代码覆盖率
- **参数**：`target_func_id`（目标函数 ID）
- **返回**：覆盖率百分比、已覆盖行数、总行数、gcov 内容等

### Search_Nearest_Seed
- **功能**：查找距离目标函数最近的 SQL 种子
- **参数**：`target_func_id`（目标函数 ID）
- **返回**：种子 SQL、调用链、距离、最近函数等

### Run_SQL_Test
- **功能**：执行 SQL 测试用例
- **参数**：`sql_script`（SQL 脚本）
- **返回**：执行状态、错误信息、原始结果等

## 优化点

1. **循环检测**：基于 Agent 派发历史，而不是工具调用次数
2. **强制检查**：确保关键步骤（如 Search_Nearest_Seed、覆盖率验证）不会遗漏
3. **错误处理**：添加 None 检查，避免 `TypeError`
4. **路由逻辑**：按优先级顺序检查，确保流程正确执行

## 注意事项

1. **SQL 生成和执行分离**：Coverage Analyzer 只生成 SQL（文本形式），SQL Tester 只执行 SQL
2. **工具调用限制**：每个 Agent 最多调用 5 轮工具，避免无限循环
3. **状态持久化**：使用 LangGraph 的 checkpointer 保存对话状态
4. **错误恢复**：如果工具调用失败，继续执行或结束当前 Agent
