# SQL Tester 集成 Collect_Coverage 方案

## 方案概述

将 `Collect_Coverage` 工具添加到 SQL Tester，使其在执行完 SQL 后立即验证覆盖率，减少一次 Agent 派发，提高执行效率。

## 当前流程 vs 优化后流程

### 当前流程
```
Coverage Analyzer (生成 SQL)
    ↓
SQL Tester (执行 SQL)
    ↓
Supervisor (派发)
    ↓
Coverage Analyzer (验证覆盖率)
```

### 优化后流程
```
Coverage Analyzer (生成 SQL)
    ↓
SQL Tester (执行 SQL + 验证覆盖率)
    ↓
Supervisor (根据覆盖率结果决定下一步)
```

## 实施方案

### 1. 修改工具配置

**位置**：`coverage_multi_agent.py` 第 65-68 行

**当前**：
```python
tools_sql = [Run_SQL_Test]
tools_coverage = [Collect_Coverage, Search_Nearest_Seed]
```

**修改后**：
```python
tools_sql = [Run_SQL_Test, Collect_Coverage]  # 添加 Collect_Coverage
tools_coverage = [Collect_Coverage, Search_Nearest_Seed]  # 保持不变
```

**影响**：
- SQL Tester 可以使用 `Collect_Coverage` 工具
- Coverage Analyzer 仍然可以使用 `Collect_Coverage`（用于初始收集）

---

### 2. 更新 LLM 绑定

**位置**：`coverage_multi_agent.py` 第 70 行

**当前**：
```python
llm_sql = llm_base.bind_tools(tools_sql)
```

**修改后**：
```python
llm_sql = llm_base.bind_tools(tools_sql)  # 自动包含 Collect_Coverage
```

**说明**：由于 `tools_sql` 已经包含 `Collect_Coverage`，LLM 绑定会自动更新。

---

### 3. 更新 SQL Tester System Prompt

**位置**：`coverage_multi_agent.py` 第 580-622 行

**当前职责**：
- 只执行 SQL
- 返回执行结果

**新增职责**：
- 执行 SQL 后，自动验证覆盖率
- 报告覆盖率是否提升

**修改后的 Prompt**：
```python
SQL_TESTER_SYSTEM = """你是 SQL 测试专家，**专门负责执行 SQL 测试用例并验证覆盖率**。

**核心职责**：
1. **执行** Coverage Analyzer 生成的 SQL 测试用例
2. **验证覆盖率**：执行完 SQL 后，立即调用 Collect_Coverage 验证覆盖率是否提升
3. 返回执行结果和覆盖率变化

**重要原则**：
- Coverage Analyzer 已经基于 seed SQL（如果找到）生成了测试用例
- 你的任务就是**直接执行这些 SQL**，然后验证覆盖率
- 如果 SQL 执行失败，只报告错误，不要尝试生成新的 SQL

**工作流程**：
1. **必须**从对话历史中查找 Coverage Analyzer 生成的 SQL 测试用例（查找 ```sql 代码块）
2. **必须**对每个 SQL，调用 Run_SQL_Test(sql_script="SQL语句")
3. **执行完 SQL 后，必须立即调用 Collect_Coverage 验证覆盖率**
   - 从对话历史中提取目标函数 ID（通常是 function:函数名@文件路径:行号 格式）
   - 调用 Collect_Coverage(target_func_id="目标函数ID")
4. 报告执行结果和覆盖率变化

**工具调用格式**：
- Run_SQL_Test: {"sql_script": "SELECT ...;"}
- Collect_Coverage: {"target_func_id": "function:函数名@文件路径:行号"}

**覆盖率验证**：
- 如果覆盖率提升：报告"覆盖率从 X% 提升到 Y%"
- 如果覆盖率未提升：报告"覆盖率仍为 X%，未提升"
- 如果覆盖率下降：报告"覆盖率从 X% 下降到 Y%"

**关键要求**：
- **看到 SQL 代码块后，必须立即调用 Run_SQL_Test 工具**
- **执行完 SQL 后，必须立即调用 Collect_Coverage 工具**
- **不要只回复文本，必须调用工具**
- **如果对话历史中有多个 SQL，执行所有 SQL，但只验证一次覆盖率（使用最后一个 SQL 执行后的结果）**

**严格禁止**：
- ❌ **不要生成新的 SQL 测试用例**（Coverage Analyzer 已经基于 seed 生成了）
- ❌ **不要自己乱生成 SQL**（即使没有找到 seed，也应该由 Coverage Analyzer 生成）
- ❌ 不要分析 SQL 为什么失败
- ❌ 不要改进或修改 SQL
- ❌ 不要提供解决方案或改进建议
- ❌ 不要写"问题分析"、"关键点"、"解决方案"等章节

**回复格式**：
- SQL 执行成功 + 覆盖率提升：返回"SQL 执行成功。覆盖率从 X% 提升到 Y%。"
- SQL 执行成功 + 覆盖率未提升：返回"SQL 执行成功。覆盖率仍为 X%，未提升。"
- SQL 执行失败：返回"SQL 执行失败：[错误信息]"
- 找不到 SQL：返回"未找到 Coverage Analyzer 生成的 SQL 测试用例。"

**重要**：
- 你的回复应该尽可能简短，只包含执行结果和覆盖率变化
- 不要包含分析、建议或新的 SQL
- **记住：SQL 测试用例的生成是 Coverage Analyzer 的职责，你只需要执行并验证覆盖率即可**"""
```

---

### 4. 添加目标函数 ID 提取函数

**位置**：在 `coverage_multi_agent.py` 中添加新函数

**功能**：从对话历史中提取目标函数 ID

```python
def _extract_target_func_id(messages: List[BaseMessage]) -> Optional[str]:
    """从对话历史中提取目标函数 ID"""
    # 方法1：从 Collect_Coverage 工具调用结果中提取
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Collect_Coverage" in tool_name:
                # 尝试从工具调用参数中提取
                # 或者从工具调用结果中提取
                content = str(msg.content)
                # 解析 JSON 或查找 function: 模式
                import json
                try:
                    result = json.loads(content)
                    if "function_name" in result and "file_path" in result:
                        return f"function:{result['function_name']}@{result['file_path']}"
                except:
                    pass
                # 尝试从文本中提取
                import re
                match = re.search(r'function:([^@]+)@([^:]+):(\d+)', content)
                if match:
                    return f"function:{match.group(1)}@{match.group(2)}:{match.group(3)}"
    
    # 方法2：从用户消息中提取
    for msg in messages:
        if isinstance(msg, HumanMessage) and msg.content:
            content = str(msg.content)
            # 查找 function: 模式
            import re
            match = re.search(r'function:([^@]+)@([^:]+):(\d+)', content)
            if match:
                return f"function:{match.group(1)}@{match.group(2)}:{match.group(3)}"
    
    # 方法3：从 Search_Nearest_Seed 结果中提取
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Search_Nearest_Seed" in tool_name:
                content = str(msg.content)
                import json
                try:
                    result = json.loads(content)
                    if "nearest_function" in result:
                        return result["nearest_function"]
                except:
                    pass
    
    return None
```

---

### 5. 改进 SQL Tester Node

**位置**：`coverage_multi_agent.py` 第 625-692 行

**当前逻辑**：
- 执行 SQL
- 检查是否执行成功
- 如果未执行，强制要求执行

**新增逻辑**：
- 执行 SQL 后，检查是否验证了覆盖率
- 如果未验证，强制要求验证

**修改后的代码**：
```python
def sql_tester_node(state: State) -> dict:
    """SQL Tester 节点，检查并执行 Coverage Analyzer 生成的 SQL，并验证覆盖率"""
    result = _run_agent_loop(state, llm_sql, tools_sql, "SQL Tester", system_prompt=SQL_TESTER_SYSTEM)
    
    all_messages = list(state["messages"]) + result.get("messages", [])
    last_msg = all_messages[-1] if all_messages else None
    
    # 检查是否执行了 SQL
    has_run_sql_test = _has_sql_executed(all_messages)
    
    # 检查是否验证了覆盖率
    has_collect_coverage_after_sql = False
    sql_executed_index = -1
    for i, msg in enumerate(all_messages):
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Run_SQL_Test" in tool_name:
                sql_executed_index = i
            elif "Collect_Coverage" in tool_name and sql_executed_index >= 0 and i > sql_executed_index:
                has_collect_coverage_after_sql = True
                break
    
    # 如果执行了 SQL 但未验证覆盖率，强制要求验证
    if has_run_sql_test and not has_collect_coverage_after_sql:
        print(f"\n[SQL Tester] ⚠️ 检测到 SQL 已执行但未验证覆盖率，强制要求验证...", flush=True)
        
        # 提取目标函数 ID
        target_func_id = _extract_target_func_id(all_messages)
        
        if target_func_id:
            forced_prompt = (
                f"**必须立即验证覆盖率**，调用 Collect_Coverage 工具：\n"
                f"目标函数 ID: {target_func_id}\n"
                f"调用 Collect_Coverage(target_func_id=\"{target_func_id}\")。"
            )
        else:
            forced_prompt = (
                "**必须立即验证覆盖率**，调用 Collect_Coverage 工具。"
                "从对话历史中提取目标函数 ID（通常是 function:函数名@文件路径:行号 格式），"
                "调用 Collect_Coverage(target_func_id=\"目标函数ID\")。"
            )
        
        forced_state_dict = {
            "messages": all_messages + [HumanMessage(content=forced_prompt)],
            "next_agent": state.get("next_agent", "__end__")
        }
        forced_result = _run_agent_loop(
            cast(State, forced_state_dict), llm_sql, tools_sql, "SQL Tester",
            system_prompt=SQL_TESTER_SYSTEM,
        )
        result["messages"].extend(forced_result["messages"])
    
    # 原有的 SQL 执行检查逻辑（保持不变）
    if isinstance(last_msg, AIMessage) and last_msg.content:
        content = str(last_msg.content)
        has_sql_code = ("```sql" in content.lower() or 
                        ("select" in content.lower() and "from" in content.lower()))
        
        if has_sql_code and not has_run_sql_test:
            # ... 原有的强制执行逻辑 ...
            pass
    
    return result
```

---

### 6. 调整 Supervisor 路由逻辑

**位置**：`coverage_multi_agent.py` 第 320-379 行

**当前逻辑**（第 346 行）：
```python
# 4. 检查是否需要 Coverage Analyzer（第二次：验证覆盖率）
elif _has_sql_executed(messages) and _count_collect_coverage(messages) < 2:
    route = "coverage_analyzer"
```

**修改后逻辑**：
```python
# 4. 检查是否需要 Coverage Analyzer（第二次：验证覆盖率）
#    如果 SQL Tester 已经验证了覆盖率，就不需要再派发 Coverage Analyzer
elif _has_sql_executed(messages) and _count_collect_coverage(messages) < 2:
    # 检查 SQL Tester 是否已经验证了覆盖率（在 SQL 执行之后）
    sql_executed_index = -1
    coverage_verified_after_sql = False
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Run_SQL_Test" in tool_name:
                sql_executed_index = i
            elif "Collect_Coverage" in tool_name and sql_executed_index >= 0 and i > sql_executed_index:
                coverage_verified_after_sql = True
                break
    
    if coverage_verified_after_sql:
        # SQL Tester 已经验证了覆盖率，不需要再派发 Coverage Analyzer
        # 检查覆盖率是否提升，决定下一步
        route = "__end__"  # 或者根据覆盖率结果决定下一步
    else:
        # SQL Tester 没有验证覆盖率，派发 Coverage Analyzer 验证
        route = "coverage_analyzer"
```

---

### 7. 添加覆盖率对比函数

**位置**：在 `coverage_multi_agent.py` 中添加新函数

**功能**：比较执行 SQL 前后的覆盖率

```python
def _check_coverage_improvement(messages: List[BaseMessage]) -> Optional[dict]:
    """检查覆盖率是否提升，返回对比结果"""
    coverage_results = []
    
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Collect_Coverage" in tool_name:
                try:
                    import json
                    result = json.loads(str(msg.content))
                    if "coverage" in result:
                        coverage_results.append({
                            "coverage": result["coverage"],
                            "index": len(coverage_results)
                        })
                except:
                    pass
    
    if len(coverage_results) < 2:
        return None
    
    # 比较最后一次和第一次的覆盖率
    first_coverage = coverage_results[0]["coverage"]
    last_coverage = coverage_results[-1]["coverage"]
    
    return {
        "first_coverage": first_coverage,
        "last_coverage": last_coverage,
        "improved": last_coverage > first_coverage,
        "improvement": last_coverage - first_coverage
    }
```

---

## 优势

1. **减少 Agent 派发次数**：从 3 次减少到 2 次
2. **提高执行效率**：SQL Tester 可以立即知道测试效果
3. **更快的迭代**：如果覆盖率未提升，可以更快地尝试下一个 SQL
4. **更清晰的职责**：SQL Tester 负责"执行+验证"，Coverage Analyzer 负责"分析+生成"

## 潜在问题及解决方案

### 问题 1：SQL Tester 可能不知道目标函数 ID

**解决方案**：
- 添加 `_extract_target_func_id` 函数从对话历史中提取
- 在 System Prompt 中明确说明如何提取
- 在强制执行逻辑中提供目标函数 ID

### 问题 2：多个 SQL 执行后，应该验证哪个覆盖率？

**解决方案**：
- 只验证最后一个 SQL 执行后的覆盖率（因为所有 SQL 都会影响覆盖率）
- 或者验证所有 SQL 执行后的最终覆盖率

### 问题 3：如果覆盖率未提升，下一步应该做什么？

**解决方案**：
- Supervisor 可以根据覆盖率结果决定：
  - 如果未提升：继续派发 Coverage Analyzer 生成新的 SQL
  - 如果提升：可以结束或继续优化

## 实施建议

1. **分步实施**：
   - 第一步：添加 `Collect_Coverage` 到 `tools_sql`
   - 第二步：更新 SQL Tester System Prompt
   - 第三步：添加强制执行逻辑
   - 第四步：调整 Supervisor 路由逻辑

2. **测试验证**：
   - 测试 SQL Tester 能否正确提取目标函数 ID
   - 测试 SQL Tester 能否正确验证覆盖率
   - 测试 Supervisor 路由逻辑是否正确

3. **监控效果**：
   - 监控 Agent 派发次数是否减少
   - 监控执行时间是否缩短
   - 监控覆盖率提升成功率
