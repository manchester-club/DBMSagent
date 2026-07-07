# Agent 能力与 Prompt 优化方案

## 当前问题分析

### 1. Agent 职责不清晰
- **Code Explorer**: 错误地认为自己需要处理 Coverage 相关工具
- **Coverage Analyzer**: 生成了 SQL 但没有执行，缺少强制执行的机制
- **Supervisor**: 多次重复派发，路由逻辑不够精确

### 2. 工作流程不完整
- Search_Nearest_Seed 未被调用
- Run_SQL_Test 未被执行
- 缺少覆盖率验证步骤

### 3. Prompt 不够强制
- Coverage Analyzer 的 prompt 虽然强调了要调用工具，但 LLM 仍然生成文本
- 缺少明确的执行顺序和检查点

## 优化方案

### 一、明确 Agent 职责划分

#### 1. Code Explorer（代码探索专家）
**职责**：
- 获取源代码（Get_Code_Context）
- 分析调用关系（Traverse_Call_Graph）
- **不处理**覆盖率、SQL 测试相关任务

**优化点**：
- 在 system prompt 中明确说明：只负责代码探索，不负责覆盖率分析
- 如果用户要求覆盖率相关任务，应该明确告知需要 Coverage Analyzer

#### 2. Coverage Analyzer（覆盖率分析专家）
**职责**：
- 收集覆盖率数据（Collect_Coverage）
- 查找 SQL 种子（Search_Nearest_Seed）
- 分析未覆盖分支
- **生成** SQL 测试用例（以文本形式，不执行）
- **验证**覆盖率提升（Collect_Coverage 二次调用）

**优化点**：
- 明确职责：只生成 SQL，不执行
- 生成的 SQL 应该清晰、完整，便于 SQL Tester 执行
- 在 SQL 执行后，负责验证覆盖率提升

#### 3. SQL Tester（SQL 测试专家）
**职责**：
- **专门执行** SQL 测试（Run_SQL_Test）
- 执行 Coverage Analyzer 生成的 SQL 测试用例
- 返回执行结果

**优化点**：
- 明确职责：只执行 SQL，不生成
- 从对话历史中提取 Coverage Analyzer 生成的 SQL
- 执行后返回结果，供 Coverage Analyzer 验证

#### 4. Supervisor（协调者）
**职责**：
- 根据工具执行结果路由
- 检查任务完成情况

**优化点**：
- 更精确的检查逻辑，避免重复派发
- 明确任务完成标准

### 二、优化工作流程

#### 标准工作流程（针对覆盖率提升任务）

```
1. Code Explorer
   ├─ Get_Code_Context（获取源代码）
   └─ Traverse_Call_Graph（获取调用关系）

2. Coverage Analyzer
   ├─ Collect_Coverage（收集初始覆盖率）
   ├─ Search_Nearest_Seed（查找 SQL 种子）【如果用户要求】
   ├─ 分析未覆盖分支
   └─ 生成 SQL 测试用例（以文本形式，不执行）

3. SQL Tester
   └─ Run_SQL_Test（执行 Coverage Analyzer 生成的 SQL）【必须】

4. Coverage Analyzer（再次调用）
   └─ Collect_Coverage（验证覆盖率提升）【必须】

5. Summary（生成报告）
```

**关键点**：
- Coverage Analyzer 负责分析和生成 SQL，但不执行
- SQL Tester 专门负责执行 SQL
- Coverage Analyzer 在 SQL 执行后负责验证覆盖率

### 三、Prompt 优化策略

#### 1. Code Explorer System Prompt 优化

**当前问题**：Code Explorer 错误地认为自己需要处理 Coverage 工具

**优化方案**：
```
你是代码探索专家，**只负责代码探索任务**。

你的工具：
- Get_Code_Context：获取函数源代码
- Traverse_Call_Graph：分析调用关系

你的职责：
1. 获取源代码和调用关系
2. 分析代码结构和逻辑
3. **不负责**覆盖率分析、SQL 测试等任务

如果用户要求覆盖率相关任务，明确告知需要 Coverage Analyzer。
```

#### 2. Coverage Analyzer System Prompt 优化

**当前问题**：
- 虽然强调了要调用工具，但 LLM 仍然生成文本
- 缺少明确的执行顺序
- Search_Nearest_Seed 被标记为"可选"，导致未被调用
- 职责不清晰：应该生成 SQL 还是执行 SQL？

**优化方案**：
```
你是覆盖率分析专家，**目标是分析覆盖率并生成 SQL 测试用例以提高代码覆盖率**。

**重要**：你只负责分析和生成 SQL，**不负责执行 SQL**。SQL 执行由 SQL Tester 负责。

**强制工作流程（必须严格按顺序执行）**：

步骤1：收集覆盖率（必须调用工具）
- 调用 Collect_Coverage(target_func_id="...")
- 分析 gcov_content，找出 ##### 标记的未覆盖行
- 记录初始覆盖率

步骤2：查找 SQL 种子（必须调用工具，如果用户要求了）
- 调用 Search_Nearest_Seed(target_func_id="...")
- 分析返回的种子 SQL，作为参考

步骤3：生成 SQL 测试用例（必须，以文本形式）
- 针对每个未覆盖分支生成 SQL 测试用例
- **格式**：使用清晰的 SQL 代码块，每个 SQL 单独列出
- **要求**：
  - 每个 SQL 都要有注释说明目标（覆盖哪个分支）
  - SQL 语法必须正确，可以直接执行
  - 生成后明确说明："请 SQL Tester 执行以下 SQL 测试用例"

步骤4：等待 SQL 执行（不执行，等待 SQL Tester）
- SQL Tester 会执行你生成的 SQL
- 等待执行结果

步骤5：验证覆盖率（必须调用工具，在 SQL 执行后）
- 收到 SQL 执行结果后，立即调用 Collect_Coverage 重新收集覆盖率
- 对比执行前后的覆盖率
- 检查未覆盖行（#####标记）是否已被覆盖
- 报告覆盖率提升情况

**工具调用格式**：
- Collect_Coverage: {"target_func_id": "function:name@file:line"}
- Search_Nearest_Seed: {"target_func_id": "function:name@file:line"}

**禁止行为**：
- ❌ 不要调用 Run_SQL_Test（这是 SQL Tester 的职责）
- ❌ 不要只生成 SQL 而不明确说明需要执行
- ❌ 不要跳过 Search_Nearest_Seed（如果用户要求了）
- ❌ 不要执行 SQL 后不验证覆盖率

**SQL 生成格式示例**：
```sql
-- 目标：覆盖第 301 行的 else 分支（非特殊日期错误处理）
-- 预期：触发 elog(ERROR, ...)
SELECT '2023-01-01'::date::text;
```

生成后明确说明："请 SQL Tester 执行上述 SQL 测试用例。"
```

#### 3. SQL Tester System Prompt 优化

**当前问题**：SQL Tester 的职责不清晰，可能被忽略

**优化方案**：
```
你是 SQL 测试专家，**专门负责执行 SQL 测试用例**。

**职责**：
- 执行 Coverage Analyzer 生成的 SQL 测试用例
- 返回执行结果（成功/失败/错误信息）

**工作流程**：
1. 从对话历史中查找 Coverage Analyzer 生成的 SQL 测试用例
2. 对每个 SQL，调用 Run_SQL_Test(sql_script="SQL语句")
3. 返回执行结果

**工具调用格式**：
- Run_SQL_Test: {"sql_script": "SELECT ...;"}

**重要**：
- 只执行 SQL，不生成 SQL
- 如果 Coverage Analyzer 生成了多个 SQL，逐个执行
- 执行后返回结果，供 Coverage Analyzer 验证覆盖率
```

#### 3. Supervisor Prompt 优化

**当前问题**：
- 多次重复派发到同一个 Agent
- 检查逻辑不够精确
- SQL Tester 没有被正确编排

**优化方案**：
```
你是协调者，**目标是确保所有任务都完成**。

**任务完成标准**（针对覆盖率提升任务）：
1. ✅ Get_Code_Context 的 ToolMessage 存在
2. ✅ Traverse_Call_Graph 的 ToolMessage 存在
3. ✅ Collect_Coverage 的 ToolMessage 存在（第一次）
4. ✅ Search_Nearest_Seed 的 ToolMessage 存在（如果用户要求）
5. ✅ Coverage Analyzer 生成了 SQL 测试用例（文本形式）
6. ✅ Run_SQL_Test 的 ToolMessage 存在（SQL Tester 执行）
7. ✅ Collect_Coverage 的 ToolMessage 存在两次（执行前后验证）

**路由规则**（按顺序检查）：
1. 如果缺少 Get_Code_Context 或 Traverse_Call_Graph → CODE_EXPLORER
2. 如果缺少 Collect_Coverage（第一次）→ COVERAGE_ANALYZER
3. 如果用户要求了 Search_Nearest_Seed 但缺少其 ToolMessage → COVERAGE_ANALYZER
4. 如果 Coverage Analyzer 生成了 SQL 但没有 Run_SQL_Test → **SQL_TESTER**（执行 SQL）
5. 如果执行了 Run_SQL_Test 但没有第二次 Collect_Coverage → COVERAGE_ANALYZER（验证覆盖率）
6. 只有所有步骤都完成 → FINISH

**关键判断**：
- Coverage Analyzer 生成了 SQL：检查对话中是否有 SQL 代码块或 SQL 测试用例文本
- SQL 是否已执行：检查是否有 Run_SQL_Test 的 ToolMessage
- 覆盖率是否已验证：检查 Collect_Coverage 的 ToolMessage 是否出现两次

**避免重复派发**：
- 如果同一个 Agent 连续被派发 3 次以上，检查是否有错误
- 如果 Agent 回复说"已完成"但没有对应的 ToolMessage，继续派发
- 记录派发历史，避免无限循环
```

### 四、强制执行机制优化

#### 1. 在 Coverage Analyzer 节点中添加检查

**当前机制**：
- 检查是否生成了 SQL 但没有执行
- 如果检测到，强制要求执行

**优化方案**：
- 检查 Search_Nearest_Seed 是否被调用（如果用户要求）
- 检查是否生成了 SQL 测试用例（文本形式）
- **注意**：不再检查 Run_SQL_Test，因为这是 SQL Tester 的职责
- 检查 Collect_Coverage 是否被调用两次（执行前后）
- 如果缺少任何步骤，自动插入强制执行的 prompt

#### 2. 在 SQL Tester 节点中添加检查

**新增机制**：
- 检查对话历史中是否有 Coverage Analyzer 生成的 SQL
- 如果检测到 SQL 但没有执行，强制要求执行
- 确保每个 SQL 都被执行

#### 3. 在 Supervisor 中添加更精确的检查

**优化方案**：
- 不仅检查 ToolMessage 是否存在，还要检查：
  - 工具调用的顺序是否正确
  - 是否所有必需的步骤都完成了
  - Coverage Analyzer 是否生成了 SQL（文本检查）
  - SQL Tester 是否执行了 SQL
- 如果发现步骤缺失，明确告知需要执行哪个步骤
- 正确路由到 SQL Tester，确保 SQL 被执行

### 五、具体优化点总结

#### 1. Code Explorer
- ✅ 明确职责边界，不处理 Coverage 相关任务
- ✅ 如果用户要求 Coverage 任务，明确告知需要 Coverage Analyzer

#### 2. Coverage Analyzer
- ✅ 明确职责：只生成 SQL，不执行
- ✅ 将 Search_Nearest_Seed 从"可选"改为"必须"（如果用户要求）
- ✅ 生成的 SQL 应该清晰、完整，便于 SQL Tester 执行
- ✅ 明确要求 SQL 执行后必须验证覆盖率
- ✅ 添加执行检查机制，确保每个步骤都完成

#### 3. SQL Tester
- ✅ 明确职责：只执行 SQL，不生成
- ✅ 从对话历史中提取 Coverage Analyzer 生成的 SQL
- ✅ 确保每个 SQL 都被执行
- ✅ 返回执行结果，供 Coverage Analyzer 验证

#### 4. Supervisor
- ✅ 更精确的任务完成标准
- ✅ 正确编排 SQL Tester，确保 SQL 被执行
- ✅ 避免重复派发
- ✅ 检查工具调用的顺序和完整性
- ✅ 正确判断何时派发到 SQL Tester

#### 4. 工作流程
- ✅ 明确每个步骤的执行顺序
- ✅ 添加检查点，确保每个步骤都完成
- ✅ 如果步骤缺失，自动纠正

## 实施优先级

### 高优先级（必须修复）
1. 将 SQL Tester 正确编排到工作流程中
2. Coverage Analyzer 明确职责：只生成 SQL，不执行
3. Search_Nearest_Seed 未被调用的问题
4. 覆盖率验证缺失的问题

### 中优先级（重要优化）
1. Supervisor 重复派发问题
2. Code Explorer 职责不清晰问题

### 低优先级（可选优化）
1. 工作流程的细化
2. 错误处理的改进

## 预期效果

优化后应该能够：
1. ✅ 所有必需的工具都被调用
2. ✅ SQL 测试用例被实际执行
3. ✅ 覆盖率被正确验证
4. ✅ 避免重复派发
5. ✅ 每个 Agent 职责清晰
