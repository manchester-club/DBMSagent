# 正确的 Agent 执行流程

## 流程设计原则

**核心思想：先试后查（Try-First-Then-Explore）**

- **阶段1（快速尝试）**：基于SQL种子快速生成测试用例，不获取代码信息
- **阶段2（深入分析）**：如果覆盖率未提升，再获取代码信息，生成精确测试用例

---

## 完整流程

```
START
  ↓
[Supervisor] 派发 → Coverage Analyzer
  ↓
[阶段1：快速尝试]
  ↓
步骤1: Coverage Analyzer → Collect_Coverage（收集初始覆盖率）
  ↓
步骤2: Coverage Analyzer → Search_Nearest_Seed（查找SQL种子）
  ↓
步骤3: Coverage Analyzer → 基于种子生成SQL测试用例（不获取代码）
  ↓
步骤4: SQL Tester → Run_SQL_Test（执行SQL）
  ↓
步骤5: SQL Tester → Collect_Coverage（验证覆盖率）
  ↓
[Supervisor] 判断：覆盖率是否提升？
  ├─ 是 → [阶段3：结束] → Summary → END
  └─ 否 → [阶段2：深入分析]
       ↓
步骤6: Code Explorer → Get_Code_Context（获取函数源代码）
  ↓
步骤7: Code Explorer → Traverse_Call_Graph（分析调用关系，可选）
  ↓
步骤8: Coverage Analyzer → 基于代码分析生成精确SQL测试用例
  ↓
步骤9: SQL Tester → Run_SQL_Test（执行精确SQL）
  ↓
步骤10: SQL Tester → Collect_Coverage（验证覆盖率）
  ↓
[Supervisor] 判断：覆盖率是否提升？
  ├─ 是 → [阶段3：结束] → Summary → END
  └─ 否 → 继续迭代或结束
```

---

## 详细步骤说明

### 阶段1：快速尝试（基于种子）

#### 步骤1：Supervisor 派发 → Coverage Analyzer

**Supervisor 决策逻辑**：
```python
if not _has_coverage_or_seed_tool_results(messages):
    route = "coverage_analyzer"  # 需要先收集覆盖率
```

**Coverage Analyzer 执行**：
- **工具调用**: `Collect_Coverage`
  - 参数: `target_func_id = "function:dcosd@postgresql-17.6/src/backend/utils/adt/float.c:2311"`
- **返回结果**:
  - 覆盖率: 80.0%（16/20行）
  - 未覆盖行: 第2322行、第2325-2327行、第2337行、第2356行
  - gcov_content: 完整的覆盖率信息

**关键点**：
- ✅ 不获取代码信息
- ✅ 只收集覆盖率数据

---

#### 步骤2：Supervisor 派发 → Coverage Analyzer

**Supervisor 决策逻辑**：
```python
if (_has_coverage_or_seed_tool_results(messages) and 
    _count_collect_coverage(messages) >= 1 and 
    not _has_sql_generated(messages)):
    route = "coverage_analyzer"  # 需要查找种子并生成SQL
```

**Coverage Analyzer 执行**：
- **工具调用1**: `Search_Nearest_Seed`
  - 参数: `target_func_id = "function:dcosd@postgresql-17.6/src/backend/utils/adt/float.c:2311"`
  - 返回: SQL种子
    ```sql
    SELECT x,
           cosd(x),
           cosd(x) IN (-1,-0.5,0,0.5,1) AS cosd_exact
    FROM (VALUES (0), (60), (90), (120), (180),
          (240), (270), (300), (360)) AS t(x);
    ```
    - 调用链: `["dcosd"]`
    - 距离: 0（直接调用）

- **生成SQL测试用例**（基于种子，不分析代码）：
  ```sql
  SELECT cosd(0);
  SELECT cosd(90);
  SELECT cosd(180);
  ```

**关键点**：
- ✅ 基于种子SQL生成变体
- ✅ 不获取代码信息
- ✅ 快速生成简单测试用例

---

#### 步骤3：Supervisor 派发 → SQL Tester

**Supervisor 决策逻辑**：
```python
if (_has_sql_generated(messages) and 
    not _has_sql_executed(messages)):
    route = "sql_tester"  # 需要执行SQL
```

**SQL Tester 执行**：
- **工具调用**: `Run_SQL_Test`
  - 参数: `sql_script = "SELECT cosd(0); SELECT cosd(90); SELECT cosd(180);"`
  - 返回:
    - 状态: Success
    - 返回数据: `[(1.0,), (0.0,), (-1.0,)]`

**关键点**：
- ✅ 执行SQL测试用例
- ✅ 记录执行结果

---

#### 步骤4：Supervisor 派发 → SQL Tester

**Supervisor 决策逻辑**：
```python
if (_has_sql_executed(messages) and 
    not coverage_verified_after_sql):
    route = "sql_tester"  # 需要验证覆盖率
```

**SQL Tester 执行**：
- **工具调用**: `Collect_Coverage`
  - 参数: `target_func_id = "function:dcosd@postgresql-17.6/src/backend/utils/adt/float.c:2311"`
  - 返回:
    - ❌ **覆盖率未提升，仍为 80.0%（16/20行）**
    - 未覆盖行: 第2322行、第2325-2327行、第2337行、第2356行

**关键点**：
- ✅ 验证覆盖率是否提升
- ✅ 如果未提升，进入阶段2

---

### 阶段2：深入分析（按需探索）

#### 步骤5：Supervisor 派发 → Code Explorer

**Supervisor 决策逻辑**：
```python
if (_has_sql_executed(messages) and 
    coverage_verified_after_sql and 
    _should_iterate(messages, agent_history) and  # 覆盖率未提升
    _needs_code_exploration(messages)):  # 未获取代码信息
    route = "code_explorer"  # 需要获取代码信息
```

**Code Explorer 执行**：
- **工具调用1**: `Get_Code_Context`
  - 参数: `query_name = "dcosd"`, `query_type = "FUNCTION"`
  - 返回: 函数源代码（包含gcov注释）

- **工具调用2**: `Traverse_Call_Graph`（可选）
  - 参数: `start_func_id = "function:dcosd@...", direction = "Upstream/Downstream"`
  - 返回: 调用关系树

- **工具调用3**: `Get_Code_Context`（获取相关函数/宏）
  - 参数: `query_name = "cosd_q1"`, `query_type = "FUNCTION"`
  - 返回: 相关函数源代码

**关键点**：
- ✅ 只在覆盖率未提升时执行
- ✅ 获取完整的代码信息
- ✅ 分析调用关系

---

#### 步骤6：Supervisor 派发 → Coverage Analyzer

**Supervisor 决策逻辑**：
```python
if (_has_code_exploration_results(messages) and 
    _has_sql_executed(messages) and 
    not _has_new_sql_generated_after_code_exploration(messages)):
    route = "coverage_analyzer"  # 需要基于代码生成精确SQL
```

**Coverage Analyzer 执行**：
- **分析代码逻辑**：
  - 识别未覆盖行的触发条件
  - 分析分支逻辑
  - 确定测试用例需求

- **生成精确SQL测试用例**（基于代码分析）：
  ```sql
  -- 覆盖第2322行：NaN处理
  SELECT cosd('NaN'::float8);
  
  -- 覆盖第2325-2327行：无穷大错误处理
  SELECT cosd('Infinity'::float8);
  SELECT cosd('-Infinity'::float8);
  
  -- 覆盖第2337行：负角度处理
  SELECT cosd(-45.0);
  ```

**关键点**：
- ✅ 基于代码分析生成测试用例
- ✅ 针对未覆盖行生成精确SQL
- ✅ 考虑边界条件和异常情况

---

#### 步骤7：Supervisor 派发 → SQL Tester

**Supervisor 决策逻辑**：
```python
if (_has_sql_generated(messages) and 
    _has_sql_executed(messages) and 
    _has_code_exploration_results(messages)):
    route = "sql_tester"  # 需要执行新的SQL
```

**SQL Tester 执行**：
- **工具调用**: `Run_SQL_Test`
  - 参数: `sql_script = "SELECT cosd('NaN'::float8); SELECT cosd('Infinity'::float8); ..."`
  - 返回:
    - 状态: Success/Error
    - 返回数据: 执行结果

**关键点**：
- ✅ 执行基于代码分析的精确SQL
- ✅ 记录执行结果（包括错误）

---

#### 步骤8：Supervisor 派发 → SQL Tester

**Supervisor 决策逻辑**：
```python
if (_has_sql_executed(messages) and 
    coverage_verified_after_sql):
    route = "sql_tester"  # 需要验证覆盖率
```

**SQL Tester 执行**：
- **工具调用**: `Collect_Coverage`
  - 参数: `target_func_id = "function:dcosd@postgresql-17.6/src/backend/utils/adt/float.c:2311"`
  - 返回:
    - ✅ **覆盖率提升到 95.0%（19/20行）**
    - 已覆盖行: 第2322行、第2325-2327行、第2337行
    - 未覆盖行: 第2356行

**关键点**：
- ✅ 验证覆盖率提升
- ✅ 如果提升，进入阶段3

---

### 阶段3：结束（生成报告）

#### 步骤9：Supervisor 派发 → Summary

**Supervisor 决策逻辑**：
```python
if (_has_sql_executed(messages) and 
    coverage_verified_after_sql and 
    not _should_iterate(messages, agent_history)):  # 覆盖率已提升或达到目标
    route = "__end__"  # 结束流程
```

**Summary 执行**：
- **生成测试报告**：
  - 测试目标
  - 源代码分析
  - 覆盖率分析（初始和最终）
  - SQL种子查找
  - SQL测试用例生成与执行
  - 工作流程总结
  - 总结与建议

**关键点**：
- ✅ 生成完整的测试报告
- ✅ 记录整个测试过程

---

## 关键决策点

### 1. 何时进入阶段2（深入分析）？

**条件**：
- ✅ SQL已执行
- ✅ 覆盖率已验证
- ✅ 覆盖率未提升（`_should_iterate` 返回 True）
- ✅ 未获取代码信息（`_needs_code_exploration` 返回 True）

**逻辑**：
```python
if (_has_sql_executed(messages) and 
    coverage_verified_after_sql and 
    _should_iterate(messages, agent_history) and 
    _needs_code_exploration(messages)):
    route = "code_explorer"
```

---

### 2. 何时结束流程？

**条件**：
- ✅ SQL已执行
- ✅ 覆盖率已验证
- ✅ 覆盖率已提升（`_should_iterate` 返回 False）

**逻辑**：
```python
if (_has_sql_executed(messages) and 
    coverage_verified_after_sql and 
    not _should_iterate(messages, agent_history)):
    route = "__end__"
```

---

## 流程对比

### ❌ 错误的流程（当前实现）

```
START
  ↓
Code Explorer → Get_Code_Context（一开始就获取代码）
  ↓
Code Explorer → Traverse_Call_Graph
  ↓
Coverage Analyzer → Search_Nearest_Seed
  ↓
Coverage Analyzer → 基于代码生成SQL
  ↓
SQL Tester → Run_SQL_Test
  ↓
SQL Tester → Collect_Coverage
  ↓
Summary → END
```

**问题**：
- ❌ 一开始就获取代码信息，浪费资源
- ❌ 没有先尝试基于种子的快速测试
- ❌ 没有"先试后查"的优化策略

---

### ✅ 正确的流程（优化后）

```
START
  ↓
[阶段1：快速尝试]
Coverage Analyzer → Collect_Coverage
  ↓
Coverage Analyzer → Search_Nearest_Seed
  ↓
Coverage Analyzer → 基于种子生成SQL（不获取代码）
  ↓
SQL Tester → Run_SQL_Test
  ↓
SQL Tester → Collect_Coverage
  ↓
[判断：覆盖率是否提升？]
  ├─ 是 → Summary → END
  └─ 否 → [阶段2：深入分析]
       ↓
Code Explorer → Get_Code_Context（按需获取代码）
  ↓
Coverage Analyzer → 基于代码生成精确SQL
  ↓
SQL Tester → Run_SQL_Test
  ↓
SQL Tester → Collect_Coverage
  ↓
Summary → END
```

**优势**：
- ✅ 先尝试快速测试，节省资源
- ✅ 只在需要时获取代码信息
- ✅ 实现"先试后查"的优化策略
- ✅ 提高整体效率

---

## 实现要点

### 1. Supervisor 路由逻辑

需要实现以下检查函数：
- `_has_coverage_or_seed_tool_results(messages)` - 是否有覆盖率或种子结果
- `_count_collect_coverage(messages)` - 收集覆盖率的次数
- `_has_sql_generated(messages)` - 是否已生成SQL
- `_has_sql_executed(messages)` - 是否已执行SQL
- `coverage_verified_after_sql` - SQL执行后是否已验证覆盖率
- `_should_iterate(messages, agent_history)` - 是否应该继续迭代
- `_needs_code_exploration(messages)` - 是否需要代码探索
- `_has_code_exploration_results(messages)` - 是否有代码探索结果

### 2. Agent 提示词优化

- **Coverage Analyzer（阶段1）**：提示词应强调"基于种子SQL生成测试用例，不需要获取代码信息"
- **Coverage Analyzer（阶段2）**：提示词应强调"基于代码分析生成精确测试用例"
- **Code Explorer**：提示词应强调"只在需要时获取代码信息"

### 3. 消息过滤

在 `summary_node` 中，需要正确过滤消息，确保：
- 只包含相关的工具调用结果
- 正确关联 `ToolMessage` 和 `AIMessage`
- 避免消息格式错误

---

## 总结

正确的 Agent 流程应该遵循"先试后查"的原则：

1. **阶段1（快速尝试）**：基于SQL种子快速生成测试用例，不获取代码信息
2. **阶段2（深入分析）**：如果覆盖率未提升，再获取代码信息，生成精确测试用例
3. **阶段3（结束）**：生成测试报告

这样可以：
- ✅ 提高效率（先尝试快速测试）
- ✅ 节省资源（按需获取代码信息）
- ✅ 实现优化策略（先试后查）
