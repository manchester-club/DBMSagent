# Agent 工作流程优化方案

## 一、当前流程的问题

### 1.1 当前流程
```
START
  ↓
Supervisor → Code Explorer (立即获取代码信息)
  ↓
Supervisor → Coverage Analyzer (收集覆盖率 + 查找种子 + 生成SQL)
  ↓
Supervisor → SQL Tester (执行SQL + 验证覆盖率)
  ↓
如果覆盖率未提升 → Code Explorer (获取更多代码信息)
  ↓
Supervisor → Coverage Analyzer (重新生成SQL)
  ↓
Supervisor → SQL Tester (执行SQL + 验证覆盖率)
```

**问题**：
- ❌ **过早探索**：一开始就派发 Code Explorer 获取代码信息（包括宏定义、调用关系等）
- ❌ **资源浪费**：即使基于种子SQL就能成功，也会先获取所有代码信息
- ❌ **效率低下**：对于简单的情况，不必要的代码探索增加了执行时间

### 1.2 优化后的流程（基于日志）
```
START
  ↓
Supervisor → Coverage Analyzer (收集覆盖率 + 查找种子)
  ↓
Supervisor → Coverage Analyzer (基于种子生成简单SQL)
  ↓
Supervisor → SQL Tester (执行SQL + 验证覆盖率)
  ↓
如果覆盖率未提升 → Code Explorer (按需获取代码信息)
  ↓
Supervisor → Coverage Analyzer (基于代码分析生成精确SQL)
  ↓
Supervisor → SQL Tester (执行SQL + 验证覆盖率)
```

**优势**：
- ✅ **先试后查**：先基于种子快速测试，失败后再深入分析
- ✅ **按需探索**：只在需要时获取代码信息
- ✅ **提高效率**：避免不必要的代码探索

---

## 二、优化方案

### 2.1 核心原则

1. **延迟代码探索**：不在初始阶段就获取代码信息
2. **快速失败**：先尝试基于种子的简单测试用例
3. **按需深入**：只有在覆盖率未提升时才获取代码信息
4. **智能路由**：Supervisor 根据覆盖率提升情况决定是否需要 Code Explorer

### 2.2 新的路由逻辑

#### 阶段1：初始快速尝试（无代码探索）

**路由规则**：
1. **首次派发**：`Coverage Analyzer`
   - 条件：`not _has_coverage_or_seed_tool_results(messages)`
   - 操作：收集覆盖率 + 查找种子

2. **生成SQL**：`Coverage Analyzer`
   - 条件：`_has_coverage_or_seed_tool_results(messages) and not _has_sql_generated(messages)`
   - 操作：基于种子生成简单SQL测试用例

3. **执行SQL**：`SQL Tester`
   - 条件：`_has_sql_generated(messages) and not _has_sql_executed(messages)`
   - 操作：执行SQL测试用例

4. **验证覆盖率**：`SQL Tester`
   - 条件：`_has_sql_executed(messages) and not coverage_verified_after_sql`
   - 操作：验证覆盖率是否提升

#### 阶段2：按需深入分析（覆盖率未提升时）

**路由规则**：
5. **检查覆盖率提升**：
   - 条件：`coverage_verified_after_sql and _should_iterate(messages, agent_history)`
   - 判断：如果覆盖率未提升，进入深入分析阶段

6. **获取代码信息**：`Code Explorer`
   - 条件：覆盖率未提升 且 未获取代码信息
   - 操作：获取函数源代码、宏定义、调用关系等

7. **重新生成SQL**：`Coverage Analyzer`
   - 条件：已获取代码信息 且 覆盖率未提升
   - 操作：基于代码分析生成精确的SQL测试用例

8. **重新执行SQL**：`SQL Tester`
   - 条件：已生成新的SQL
   - 操作：执行SQL测试用例并验证覆盖率

### 2.3 关键判断函数

#### 2.3.1 是否需要代码信息

```python
def _needs_code_exploration(messages: List[BaseMessage]) -> bool:
    """
    判断是否需要代码探索
    
    条件：
    1. 已经执行过SQL测试
    2. 已经验证过覆盖率
    3. 覆盖率未提升（_should_iterate 返回 True）
    4. 还没有获取过代码信息（_has_code_explorer_tool_results 返回 False）
    """
    # 检查是否已执行SQL
    has_sql_executed = _has_sql_executed(messages)
    
    # 检查是否已验证覆盖率
    coverage_verified = _has_coverage_verified_after_sql(messages)
    
    # 检查覆盖率是否未提升
    should_iterate = _should_iterate(messages, agent_history)
    
    # 检查是否已获取代码信息
    has_code_info = _has_code_explorer_tool_results(messages)
    
    return (has_sql_executed and 
            coverage_verified and 
            should_iterate and 
            not has_code_info)
```

#### 2.3.2 覆盖率是否已验证

```python
def _has_coverage_verified_after_sql(messages: List[BaseMessage]) -> bool:
    """检查SQL执行后是否已验证覆盖率"""
    sql_executed_index = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Run_SQL_Test" in tool_name:
                sql_executed_index = i
            elif "Collect_Coverage" in tool_name and sql_executed_index >= 0 and i > sql_executed_index:
                return True
    return False
```

### 2.4 Supervisor 路由逻辑（优化后）

```python
def supervisor_node(state: State) -> dict:
    messages = state["messages"]
    agent_history = state.get("agent_history", [])
    
    # 1. 循环检测
    if len(agent_history) >= 3:
        last_three = agent_history[-3:]
        if last_three[0] == last_three[1] == last_three[2]:
            route = "__end__"
            return {"next_agent": route, "agent_history": agent_history}
    
    # 2. 初始阶段：收集覆盖率和查找种子
    if not _has_coverage_or_seed_tool_results(messages):
        route = "coverage_analyzer"
    
    # 3. 生成SQL（基于种子）
    elif (_has_coverage_or_seed_tool_results(messages) and 
          _count_collect_coverage(messages) >= 1 and
          not _has_sql_generated(messages)):
        route = "coverage_analyzer"
    
    # 4. 执行SQL
    elif _has_sql_generated(messages) and not _has_sql_executed(messages):
        route = "sql_tester"
    
    # 5. 验证覆盖率
    elif _has_sql_executed(messages):
        coverage_verified = _has_coverage_verified_after_sql(messages)
        if not coverage_verified:
            route = "sql_tester"
        else:
            # 检查覆盖率是否提升
            if _should_iterate(messages, agent_history):
                # 覆盖率未提升，需要深入分析
                if _needs_code_exploration(messages):
                    # 需要获取代码信息
                    route = "code_explorer"
                else:
                    # 已有代码信息，重新生成SQL
                    route = "coverage_analyzer"
            else:
                # 覆盖率已提升，结束
                route = "__end__"
    
    # 6. 其他情况，使用 LLM 判断
    else:
        sys_msg = SystemMessage(content=SUPERVISOR_PROMPT)
        recent = messages[-10:] if len(messages) > 10 else messages
        inp = [sys_msg] + recent
        resp = llm_supervisor.invoke(inp)
        content = getattr(resp, "content", "") or ""
        route = _parse_route(content)
    
    # 更新 agent_history
    if route != "__end__":
        agent_history = agent_history + [route]
        agent_history = agent_history[-10:]
    
    return {"next_agent": route, "agent_history": agent_history}
```

---

## 三、Prompt 优化

### 3.1 Coverage Analyzer System Prompt（优化后）

```python
COVERAGE_ANALYZER_SYSTEM = """你是覆盖率分析专家，核心目标是生成SQL测试用例提高目标函数的代码覆盖率。

**工作流程（两阶段）**：

**阶段1：快速尝试（基于种子）**
1. Collect_Coverage：收集初始覆盖率
2. Search_Nearest_Seed：查找相关SQL种子
3. **基于种子生成简单SQL测试用例**：直接基于种子SQL生成变体，快速测试

**阶段2：深入分析（覆盖率未提升时）**
1. 等待 Code Explorer 提供代码信息（如果覆盖率未提升）
2. **基于代码分析生成精确SQL测试用例**：分析未覆盖的分支条件，生成针对性的SQL

**重要**：
- 你只负责分析和生成SQL，**不负责执行SQL**。SQL执行由SQL Tester负责。
- **你只能使用以下工具**：Collect_Coverage, Search_Nearest_Seed
- **严格禁止使用其他工具**：Get_Code_Context, Traverse_Call_Graph, Run_SQL_Test

**生成策略**：
- **阶段1**：优先基于种子SQL生成简单变体（修改时间值、参数等）
- **阶段2**：基于Code Explorer提供的代码信息，分析未覆盖分支的条件，生成精确的SQL

**如果覆盖率未提升**：
- 在回复中明确说明需要什么代码信息（宏定义、分支条件、相关函数等）
- Supervisor会派发Code Explorer获取这些信息
- 绝对不要尝试调用Get_Code_Context或Traverse_Call_Graph
"""
```

### 3.2 Supervisor Prompt（优化后）

```python
SUPERVISOR_PROMPT = """你是协调者，负责派发任务给三个专家Agent。

**三个专家Agent及其职责**：

1. **COVERAGE_ANALYZER**（覆盖率分析专家）
   - 工具：Collect_Coverage, Search_Nearest_Seed
   - 职责：收集覆盖率、查找SQL种子、**生成SQL测试用例**
   - 工作流程：
     - 阶段1：基于种子快速生成SQL
     - 阶段2：基于代码分析生成精确SQL（覆盖率未提升时）

2. **SQL_TESTER**（SQL测试专家）
   - 工具：Run_SQL_Test, Collect_Coverage
   - 职责：执行SQL测试用例、验证覆盖率

3. **CODE_EXPLORER**（代码探索专家）
   - 工具：Get_Code_Context, Traverse_Call_Graph
   - 职责：获取函数源代码、分析调用关系
   - **何时派发**：覆盖率未提升时，按需获取代码信息

**优化后的工作流程**：
1. COVERAGE_ANALYZER → 收集覆盖率、查找种子、基于种子生成SQL
2. SQL_TESTER → 执行SQL、验证覆盖率
3. **如果覆盖率未提升** → CODE_EXPLORER → 获取代码信息
4. COVERAGE_ANALYZER → 基于代码分析生成精确SQL
5. SQL_TESTER → 执行SQL、验证覆盖率

**路由规则**（按顺序检查）：
1. 缺少覆盖率数据（Collect_Coverage） → COVERAGE_ANALYZER
2. 已收集覆盖率和找到种子，但未生成SQL → COVERAGE_ANALYZER
3. 已生成SQL但未执行（无Run_SQL_Test） → SQL_TESTER
4. 已执行SQL但未验证覆盖率 → SQL_TESTER
5. **覆盖率未提升 且 未获取代码信息** → CODE_EXPLORER
6. **覆盖率未提升 且 已获取代码信息** → COVERAGE_ANALYZER
7. 覆盖率已提升 → FINISH

**关键原则**：
- **先试后查**：先基于种子快速测试，失败后再深入分析
- **按需探索**：只在覆盖率未提升时才获取代码信息
- **避免过早探索**：不要在初始阶段就获取所有代码信息

请只回复：SQL_TESTER / CODE_EXPLORER / COVERAGE_ANALYZER / FINISH"""
```

---

## 四、执行流程图

### 4.1 优化后的完整流程

```
START
  ↓
Supervisor
  ↓
[阶段1：快速尝试]
  ↓
Coverage Analyzer
  ├─ Collect_Coverage (收集初始覆盖率)
  ├─ Search_Nearest_Seed (查找SQL种子)
  └─ 基于种子生成简单SQL
  ↓
Supervisor
  ↓
SQL Tester
  ├─ Run_SQL_Test (执行SQL)
  └─ Collect_Coverage (验证覆盖率)
  ↓
Supervisor
  ├─ 覆盖率已提升？ → Summary → END
  └─ 覆盖率未提升？ → [阶段2：深入分析]
       ↓
       Code Explorer
       ├─ Get_Code_Context (获取源代码)
       ├─ Get_Code_Context (获取宏定义)
       └─ Traverse_Call_Graph (分析调用关系)
       ↓
       Supervisor
       ↓
       Coverage Analyzer
       └─ 基于代码分析生成精确SQL
       ↓
       Supervisor
       ↓
       SQL Tester
       ├─ Run_SQL_Test (执行SQL)
       └─ Collect_Coverage (验证覆盖率)
       ↓
       Supervisor
       └─ Summary → END
```

### 4.2 关键决策点

```
决策点1：是否需要代码探索？
  ├─ 条件：覆盖率未提升 且 未获取代码信息
  ├─ 是 → Code Explorer
  └─ 否 → Coverage Analyzer（重新生成SQL）

决策点2：覆盖率是否提升？
  ├─ 是 → Summary → END
  └─ 否 → 继续迭代（最多3次）
```

---

## 五、实现要点

### 5.1 需要修改的函数

1. **`supervisor_node`**：
   - 移除初始阶段的 Code Explorer 路由
   - 添加 `_needs_code_exploration` 判断
   - 优化路由优先级

2. **新增函数**：
   - `_needs_code_exploration(messages, agent_history)`: 判断是否需要代码探索
   - `_has_coverage_verified_after_sql(messages)`: 检查覆盖率是否已验证

3. **修改函数**：
   - `_should_iterate(messages, agent_history)`: 确保在覆盖率未提升时返回 True

### 5.2 需要更新的 Prompt

1. **`COVERAGE_ANALYZER_SYSTEM`**：
   - 明确两阶段工作流程
   - 强调阶段1优先基于种子生成简单SQL
   - 强调阶段2基于代码分析生成精确SQL

2. **`SUPERVISOR_PROMPT`**：
   - 更新工作流程说明
   - 强调"先试后查"原则
   - 明确何时派发 Code Explorer

---

## 六、预期效果

### 6.1 效率提升

- **减少不必要的代码探索**：只在覆盖率未提升时才获取代码信息
- **快速失败**：基于种子的简单测试用例可以快速验证是否有效
- **按需深入**：只在需要时才进行深入的代码分析

### 6.2 流程优化

- **阶段1（快速尝试）**：适用于大多数情况，基于种子SQL就能成功
- **阶段2（深入分析）**：只在必要时触发，基于代码分析生成精确SQL

### 6.3 资源节约

- **减少API调用**：避免不必要的 Get_Code_Context 和 Traverse_Call_Graph 调用
- **减少执行时间**：对于简单情况，可以更快完成测试

---

## 七、总结

这个优化方案实现了"先试后查"的策略：

1. **初始阶段**：快速尝试基于种子的简单SQL测试用例
2. **失败后**：按需获取代码信息，深入分析未覆盖的分支
3. **精确生成**：基于代码分析生成针对性的SQL测试用例

这样可以：
- ✅ 提高效率：避免不必要的代码探索
- ✅ 快速失败：快速验证简单测试用例是否有效
- ✅ 按需深入：只在必要时进行深入的代码分析
