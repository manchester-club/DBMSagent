# 完整的 Agent 架构和执行流程

## 一、系统架构

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      Supervisor (协调者)                      │
│  - 负责派发任务给三个专家 Agent                                │
│  - 根据消息状态和路由规则决定下一个执行的 Agent                │
│  - 实现"先试后查"的优化策略                                    │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Coverage Analyzer │ │   Code Explorer  │ │    SQL Tester      │
│  (覆盖率分析专家)  │ │   (代码探索专家)  │ │   (SQL测试专家)     │
└──────────────────┘ └──────────────────┘ └──────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ 工具:             │ │ 工具:             │ │ 工具:             │
│ - Collect_Coverage│ │ - Get_Code_Context│ │ - Run_SQL_Test   │
│ - Search_Nearest_│ │ - Traverse_Call_  │ │ - Collect_Coverage│
│   Seed            │ │   Graph           │ │                   │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

### 1.2 Agent 职责和工具

#### 1.2.1 Supervisor（协调者）

**职责**：
- 协调三个专家 Agent 的工作
- 根据消息状态和路由规则决定下一个执行的 Agent
- 实现"先试后查"的优化策略

**路由规则**（按优先级）：
1. 缺少覆盖率数据 → Coverage Analyzer
2. 已收集覆盖率但未生成SQL → Coverage Analyzer
3. Coverage Analyzer 要求 Code Explorer → Code Explorer
4. 已生成SQL但未执行 → SQL Tester
5. 已执行SQL但未验证覆盖率 → SQL Tester
6. 覆盖率未提升且未获取代码信息 → Code Explorer
7. 覆盖率未提升且已获取代码信息 → Coverage Analyzer
8. 覆盖率已提升 → Summary → END

---

#### 1.2.2 Coverage Analyzer（覆盖率分析专家）

**职责**：
- 收集目标函数的代码覆盖率
- 查找相关的 SQL 种子
- 生成 SQL 测试用例以提高覆盖率

**工具**：
- `Collect_Coverage`: 收集目标函数的代码覆盖率
  - 参数: `target_func_id` (函数ID)
  - 返回: 覆盖率百分比、已覆盖行数、总行数、gcov_content等
- `Search_Nearest_Seed`: 查找能触发目标函数的 SQL 种子
  - 参数: `target_func_id` (函数ID)
  - 返回: SQL种子、调用链、距离等

**工作流程（两阶段）**：
- **阶段1：快速尝试（基于种子）**
  - 收集初始覆盖率
  - 查找SQL种子
  - 基于种子生成简单SQL测试用例（不获取代码信息）
- **阶段2：深入分析（覆盖率未提升时）**
  - 等待 Code Explorer 提供代码信息
  - 基于代码分析生成精确SQL测试用例

**禁止使用的工具**：
- ❌ Get_Code_Context
- ❌ Traverse_Call_Graph
- ❌ Run_SQL_Test

---

#### 1.2.3 Code Explorer（代码探索专家）

**职责**：
- 获取函数源代码
- 分析函数调用关系
- 提供代码信息以帮助生成精确的测试用例

**工具**：
- `Get_Code_Context`: 获取函数或宏的源代码
  - 参数: `query_name` (函数/宏名), `query_type` (FUNCTION/MACRO)
  - 返回: 源代码、文件路径、行号等
- `Traverse_Call_Graph`: 分析函数调用关系
  - 参数: `start_func_id` (函数ID), `direction` (Upstream/Downstream), `max_depth` (最大深度)
  - 返回: 调用关系树

**何时被派发**：
- Coverage Analyzer 明确要求 Code Explorer 时
- 覆盖率未提升且未获取代码信息时

**禁止使用的工具**：
- ❌ Collect_Coverage
- ❌ Search_Nearest_Seed
- ❌ Run_SQL_Test

---

#### 1.2.4 SQL Tester（SQL 测试专家）

**职责**：
- 执行 Coverage Analyzer 生成的 SQL 测试用例
- 验证覆盖率是否提升

**工具**：
- `Run_SQL_Test`: 执行 SQL 测试用例
  - 参数: `sql_script` (SQL脚本)
  - 返回: 执行状态、返回数据、错误信息等
- `Collect_Coverage`: 验证覆盖率是否提升
  - 参数: `target_func_id` (函数ID)
  - 返回: 覆盖率百分比、已覆盖行数、总行数等

**何时被派发**：
- Coverage Analyzer 已生成 SQL 时
- SQL 已执行但未验证覆盖率时

**禁止使用的工具**：
- ❌ Get_Code_Context
- ❌ Traverse_Call_Graph
- ❌ Search_Nearest_Seed

---

## 二、完整执行流程

### 2.1 流程概览

```
START
  ↓
[阶段1：快速尝试（基于种子）]
  ↓
Supervisor → Coverage Analyzer
  ├─ Collect_Coverage（收集初始覆盖率）
  ├─ Search_Nearest_Seed（查找SQL种子）
  └─ 基于种子生成SQL测试用例（不获取代码）
  ↓
Supervisor → SQL Tester
  ├─ Run_SQL_Test（执行SQL）
  └─ Collect_Coverage（验证覆盖率）
  ↓
[判断：覆盖率是否提升？]
  ├─ 是 → Summary → END
  └─ 否 → [阶段2：深入分析（按需探索）]
       ↓
       Supervisor → Code Explorer
       ├─ Get_Code_Context（获取源代码）
       └─ Traverse_Call_Graph（分析调用关系）
       ↓
       Supervisor → Coverage Analyzer
       └─ 基于代码分析生成精确SQL测试用例
       ↓
       Supervisor → SQL Tester
       ├─ Run_SQL_Test（执行精确SQL）
       └─ Collect_Coverage（验证覆盖率）
       ↓
       Summary → END
```

### 2.2 详细执行步骤

#### 阶段1：快速尝试（基于种子）

**步骤1：Supervisor 派发 → Coverage Analyzer**

**Supervisor 决策逻辑**：
```python
if not _has_coverage_or_seed_tool_results(messages):
    route = "coverage_analyzer"  # 需要先收集覆盖率
```

**Coverage Analyzer 执行**：
- **工具调用**: `Collect_Coverage`
  - 参数: `target_func_id = "function:dcosd@postgresql-17.6/src/backend/utils/adt/float.c:2311"`
  - 返回: 覆盖率、已覆盖行数、总行数、gcov_content

**关键点**：
- ✅ 不获取代码信息
- ✅ 只收集覆盖率数据

---

**步骤2：Supervisor 派发 → Coverage Analyzer**

**Supervisor 决策逻辑**：
```python
if (_has_coverage_or_seed_tool_results(messages) and 
    _count_collect_coverage(messages) >= 1 and
    not _has_sql_generated(messages)):
    route = "coverage_analyzer"  # 需要查找种子并生成SQL
```

**Coverage Analyzer 执行**：
- **工具调用**: `Search_Nearest_Seed`
  - 参数: `target_func_id = "function:dcosd@postgresql-17.6/src/backend/utils/adt/float.c:2311"`
  - 返回: SQL种子、调用链、距离

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

**步骤3：Supervisor 派发 → SQL Tester**

**Supervisor 决策逻辑**：
```python
if (_has_sql_generated(messages) and 
    not _has_sql_executed(messages) and
    not _coverage_analyzer_needs_code_explorer(messages)):
    route = "sql_tester"  # 需要执行SQL
```

**SQL Tester 执行**：
- **工具调用**: `Run_SQL_Test`
  - 参数: `sql_script = "SELECT cosd(0); SELECT cosd(90); SELECT cosd(180);"`
  - 返回: 执行状态、返回数据

**关键点**：
- ✅ 执行SQL测试用例
- ✅ 记录执行结果

---

**步骤4：Supervisor 派发 → SQL Tester**

**Supervisor 决策逻辑**：
```python
if (_has_sql_executed(messages) and 
    not _has_coverage_verified_after_sql(messages)):
    route = "sql_tester"  # 需要验证覆盖率
```

**SQL Tester 执行**：
- **工具调用**: `Collect_Coverage`
  - 参数: `target_func_id = "function:dcosd@postgresql-17.6/src/backend/utils/adt/float.c:2311"`
  - 返回: 覆盖率、已覆盖行数、总行数

**关键点**：
- ✅ 验证覆盖率是否提升
- ✅ 如果未提升，进入阶段2

---

#### 阶段2：深入分析（按需探索）

**步骤5：Supervisor 派发 → Code Explorer**

**Supervisor 决策逻辑**：
```python
if (_has_sql_generated(messages) and 
    _coverage_analyzer_needs_code_explorer(messages) and
    not _has_code_explorer_tool_results(messages)):
    route = "code_explorer"  # Coverage Analyzer 要求 Code Explorer
```

或者：

```python
if (_has_sql_executed(messages) and 
    _has_coverage_verified_after_sql(messages) and 
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

**步骤6：Supervisor 派发 → Coverage Analyzer**

**Supervisor 决策逻辑**：
```python
if (_has_code_explorer_tool_results(messages) and 
    _has_sql_executed(messages) and 
    _should_iterate(messages, agent_history)):
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

**步骤7：Supervisor 派发 → SQL Tester**

**Supervisor 决策逻辑**：
```python
if (_has_sql_generated(messages) and 
    _has_code_explorer_tool_results(messages)):
    route = "sql_tester"  # 需要执行新的SQL
```

**SQL Tester 执行**：
- **工具调用**: `Run_SQL_Test`
  - 参数: `sql_script = "SELECT cosd('NaN'::float8); SELECT cosd('Infinity'::float8); ..."`
  - 返回: 执行状态、返回数据

**关键点**：
- ✅ 执行基于代码分析的精确SQL
- ✅ 记录执行结果（包括错误）

---

**步骤8：Supervisor 派发 → SQL Tester**

**Supervisor 决策逻辑**：
```python
if (_has_sql_executed(messages) and 
    not _has_coverage_verified_after_sql(messages)):
    route = "sql_tester"  # 需要验证覆盖率
```

**SQL Tester 执行**：
- **工具调用**: `Collect_Coverage`
  - 参数: `target_func_id = "function:dcosd@postgresql-17.6/src/backend/utils/adt/float.c:2311"`
  - 返回: 覆盖率、已覆盖行数、总行数

**关键点**：
- ✅ 验证覆盖率提升
- ✅ 如果提升，进入阶段3

---

#### 阶段3：结束（生成报告）

**步骤9：Supervisor 派发 → Summary**

**Supervisor 决策逻辑**：
```python
if (_has_sql_executed(messages) and 
    _has_coverage_verified_after_sql(messages) and 
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

## 三、关键决策点

### 3.1 何时进入阶段2（深入分析）？

**条件1：Coverage Analyzer 明确要求 Code Explorer**
```python
if (_has_sql_generated(messages) and 
    _coverage_analyzer_needs_code_explorer(messages) and
    not _has_code_explorer_tool_results(messages)):
    route = "code_explorer"
```

**条件2：覆盖率未提升且未获取代码信息**
```python
if (_has_sql_executed(messages) and 
    _has_coverage_verified_after_sql(messages) and 
    _should_iterate(messages, agent_history) and  # 覆盖率未提升
    _needs_code_exploration(messages)):  # 未获取代码信息
    route = "code_explorer"
```

---

### 3.2 何时结束流程？

**条件**：
- ✅ SQL已执行
- ✅ 覆盖率已验证
- ✅ 覆盖率已提升（`_should_iterate` 返回 False）

**逻辑**：
```python
if (_has_sql_executed(messages) and 
    _has_coverage_verified_after_sql(messages) and 
    not _should_iterate(messages, agent_history)):
    route = "__end__"
```

---

## 四、核心优化策略

### 4.1 "先试后查"（Try-First-Then-Explore）

**核心思想**：
- **阶段1（快速尝试）**：基于SQL种子快速生成测试用例，不获取代码信息
- **阶段2（深入分析）**：如果覆盖率未提升，再获取代码信息，生成精确测试用例

**优势**：
- ✅ 提高效率：先尝试快速测试，节省资源
- ✅ 按需探索：只在需要时获取代码信息
- ✅ 实现优化策略：遵循"先试后查"原则

---

### 4.2 流程对比

#### ❌ 错误的流程（优化前）

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

#### ✅ 正确的流程（优化后）

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

---

## 五、实现细节

### 5.1 Supervisor 路由逻辑

**关键检查函数**：
- `_has_coverage_or_seed_tool_results(messages)` - 是否有覆盖率或种子结果
- `_count_collect_coverage(messages)` - 收集覆盖率的次数
- `_has_sql_generated(messages)` - 是否已生成SQL
- `_has_sql_executed(messages)` - 是否已执行SQL
- `_has_coverage_verified_after_sql(messages)` - SQL执行后是否已验证覆盖率
- `_should_iterate(messages, agent_history)` - 是否应该继续迭代
- `_needs_code_exploration(messages, agent_history)` - 是否需要代码探索
- `_coverage_analyzer_needs_code_explorer(messages)` - Coverage Analyzer 是否要求 Code Explorer
- `_has_code_explorer_tool_results(messages)` - 是否有代码探索结果

---

### 5.2 Agent 提示词

#### Coverage Analyzer 提示词

**阶段1：快速尝试（基于种子）**
- 优先基于种子SQL生成简单变体
- 不需要获取代码信息
- 快速验证是否能提升覆盖率

**阶段2：深入分析（覆盖率未提升时）**
- 等待 Code Explorer 提供代码信息
- 基于代码分析生成精确SQL测试用例
- 分析未覆盖行的触发条件

---

#### Code Explorer 提示词

- 只在需要时获取代码信息
- 根据 Coverage Analyzer 的需求提供相应的代码信息
- 提供函数源代码、宏定义、调用关系等

---

#### SQL Tester 提示词

- 看到 SQL 代码块后，必须立即调用 Run_SQL_Test 工具
- 执行 SQL 后，必须调用 Collect_Coverage 验证覆盖率
- 只能使用 Run_SQL_Test 和 Collect_Coverage 工具

---

## 六、实际执行示例

### 6.1 示例：dcosd 函数测试流程

**初始状态**：
- 目标函数：`dcosd`
- 初始覆盖率：80.0%（16/20行）
- 未覆盖行：第2322行、第2325-2327行、第2337行、第2356行

**阶段1：快速尝试**
1. Coverage Analyzer → Collect_Coverage（收集初始覆盖率：80.0%）
2. Coverage Analyzer → Search_Nearest_Seed（找到SQL种子）
3. Coverage Analyzer → 基于种子生成SQL：
   ```sql
   SELECT cosd(0);
   SELECT cosd(90);
   SELECT cosd(180);
   ```
4. SQL Tester → Run_SQL_Test（执行SQL）
5. SQL Tester → Collect_Coverage（验证覆盖率：仍为80.0%）

**阶段2：深入分析**
6. Code Explorer → Get_Code_Context（获取dcosd源代码）
7. Code Explorer → Get_Code_Context（获取cosd_q1源代码）
8. Coverage Analyzer → 基于代码分析生成精确SQL：
   ```sql
   SELECT cosd('NaN'::float8);
   SELECT cosd('Infinity'::float8);
   SELECT cosd('-Infinity'::float8);
   SELECT cosd(-45.0);
   ```
9. SQL Tester → Run_SQL_Test（执行精确SQL）
10. SQL Tester → Collect_Coverage（验证覆盖率：提升到95.0%）

**结果**：
- 最终覆盖率：95.0%（19/20行）
- 覆盖率提升：+15.0%（+3行）
- 未覆盖行：第2356行（溢出错误处理）

---

## 七、总结

### 7.1 核心特点

1. **多Agent协作**：Supervisor 协调三个专家 Agent 协同工作
2. **职责分离**：每个 Agent 有明确的职责和工具
3. **优化策略**：实现"先试后查"的优化策略
4. **智能路由**：Supervisor 根据消息状态智能路由

### 7.2 优势

- ✅ **提高效率**：先尝试快速测试，节省资源
- ✅ **按需探索**：只在需要时获取代码信息
- ✅ **灵活适应**：根据覆盖率提升情况动态调整策略
- ✅ **完整记录**：生成详细的测试报告

### 7.3 适用场景

- 提高代码覆盖率
- 生成SQL测试用例
- 分析未覆盖的代码分支
- 自动化测试用例生成

---

## 八、技术实现

### 8.1 框架

- **LangGraph**：多Agent协作框架
- **LangChain**：LLM调用和工具集成
- **PostgreSQL**：目标数据库

### 8.2 关键组件

- **Supervisor Node**：路由决策节点
- **Coverage Analyzer Node**：覆盖率分析节点
- **Code Explorer Node**：代码探索节点
- **SQL Tester Node**：SQL测试节点
- **Summary Node**：报告生成节点

### 8.3 工具实现

- **Collect_Coverage**：基于 gcov 收集覆盖率
- **Search_Nearest_Seed**：基于知识图谱查找SQL种子
- **Get_Code_Context**：从代码库获取源代码
- **Traverse_Call_Graph**：分析函数调用关系
- **Run_SQL_Test**：执行SQL测试用例

---

**文档版本**：v1.0  
**最后更新**：2026-01-29  
**作者**：Auto Agent
