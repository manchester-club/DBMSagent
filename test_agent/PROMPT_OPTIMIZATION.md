# Prompt 优化说明

## 优化目标

根据用户需求，优化了两个关键部分的 prompt：
1. **Coverage Analyzer**：强调基于 seed SQL 生成测试用例
2. **SQL Tester**：强调不自己生成 SQL，只执行 Coverage Analyzer 生成的 SQL

## 优化内容

### 1. Coverage Analyzer Prompt 优化

#### 核心改进

**之前的问题：**
- 虽然提到了 Search_Nearest_Seed，但没有强调必须基于 seed 来生成 SQL
- 可能导致 Coverage Analyzer 自己乱生成 SQL，而不是基于 seed 修改

**优化后的关键点：**

1. **明确目标**：
   - 强调核心目标是"提高目标函数的代码覆盖率"
   - 明确识别所有未覆盖的分支和代码行

2. **强化 seed 的作用**：
   - 如果找到了 seed SQL，**必须基于这个种子 SQL 来生成测试用例**
   - 明确说明"这是生成测试用例的基础，不要自己乱生成"

3. **基于 seed 的修改策略**：
   - 保留 seed SQL 的核心结构
   - 修改参数值以触发未覆盖的分支
   - 添加或修改条件以覆盖不同的代码路径
   - 确保修改后的 SQL 能够触发目标函数中的未覆盖行

4. **SQL 生成格式**：
   - 明确要求注释说明基于哪个 seed SQL 修改
   - 说明修改点和目标

#### 关键语句

```
**关键**：如果工具返回了 seed_sql（status="Success"），**必须基于这个种子 SQL 来生成测试用例**
- 理解种子 SQL 如何触发目标函数
- 分析种子 SQL 的参数、条件和执行路径
- **这是生成测试用例的基础，不要自己乱生成**
```

```
**核心原则**：
- **如果找到了 seed SQL**：**必须基于 seed SQL 来修改**，而不是自己从头生成
- **如果没有找到 seed SQL**：可以基于覆盖率分析结果生成新的 SQL
```

### 2. SQL Tester Prompt 优化

#### 核心改进

**之前的问题：**
- 虽然禁止生成 SQL，但没有强调为什么不应该生成
- 没有明确说明 Coverage Analyzer 已经基于 seed 生成了 SQL

**优化后的关键点：**

1. **明确职责边界**：
   - 强调"只执行"SQL，不生成、不修改、不分析
   - 明确说明 Coverage Analyzer 已经基于 seed SQL 生成了测试用例

2. **强化禁止生成**：
   - 明确说明"不要自己乱生成 SQL"
   - 即使没有找到 seed，也应该由 Coverage Analyzer 生成

3. **执行原则**：
   - 直接执行 Coverage Analyzer 生成的 SQL
   - 如果执行失败，只报告错误，不尝试生成新的 SQL

#### 关键语句

```
**重要原则**：
- Coverage Analyzer 已经基于 seed SQL（如果找到）生成了测试用例
- 你的任务就是**直接执行这些 SQL**，不要自己生成或修改
- 如果 SQL 执行失败，只报告错误，不要尝试生成新的 SQL
```

```
- ❌ **不要生成新的 SQL 测试用例**（Coverage Analyzer 已经基于 seed 生成了）
- ❌ **不要自己乱生成 SQL**（即使没有找到 seed，也应该由 Coverage Analyzer 生成）
```

## 工作流程优化

### 优化后的完整流程

```
1. Coverage Analyzer 收集覆盖率
   ↓
2. Coverage Analyzer 查找 seed SQL（如果用户要求）
   ↓
3. Coverage Analyzer 基于 seed SQL 生成测试用例
   - 如果找到 seed：基于 seed 修改
   - 如果没找到 seed：基于覆盖率分析生成
   ↓
4. SQL Tester 执行 SQL
   - 只执行，不生成
   ↓
5. Coverage Analyzer 验证覆盖率提升
```

## 预期效果

1. **Coverage Analyzer**：
   - 如果找到了 seed SQL，会基于 seed 来修改生成测试用例
   - 不会自己乱生成 SQL
   - 生成的 SQL 更有可能成功执行（因为基于已有的 seed）

2. **SQL Tester**：
   - 明确知道不应该生成 SQL
   - 只执行 Coverage Analyzer 生成的 SQL
   - 即使执行失败，也不会尝试生成新的 SQL

## 示例

### 场景：找到了 seed SQL

**Seed SQL：**
```sql
select 'infinity'::date, '-infinity'::date;
```

**Coverage Analyzer 生成的测试用例（基于 seed 修改）：**
```sql
-- 基于 seed SQL: select 'infinity'::date, '-infinity'::date;
-- 目标：覆盖第 301 行的 else 分支（非特殊日期错误处理）
-- 修改点：将特殊日期值改为普通日期值，触发错误分支
-- 预期：触发 elog(ERROR, "invalid argument for EncodeSpecialDate")
SELECT '2023-01-01'::date::text;
```

**SQL Tester 的行为：**
- 直接执行这个 SQL
- 不生成新的 SQL
- 如果执行失败，只报告错误
