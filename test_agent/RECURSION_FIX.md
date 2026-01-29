# 递归限制问题修复

## 问题描述

从执行日志看到，系统达到了递归限制（25次），错误信息：
```
langgraph.errors.GraphRecursionError: Recursion limit of 25 reached without hitting a stop condition.
```

## 问题分析

### 根本原因
Supervisor 在 Coverage Analyzer 和 SQL Tester 之间反复派发，导致无限循环：

1. **Coverage Analyzer 生成了 SQL** → Supervisor 派发到 SQL Tester
2. **SQL Tester 执行 SQL 失败** → SQL Tester 又生成了新的 SQL（不应该）
3. **Supervisor 检测到新的 SQL** → 又派发到 SQL Tester
4. **Coverage Analyzer 又生成了 SQL** → 循环继续
5. **达到递归限制**

### 具体问题

1. **SQL Tester 不应该生成 SQL**
   - SQL Tester 的职责是执行 SQL，不是生成 SQL
   - 但日志显示 SQL Tester 在 SQL 执行失败后，又生成了新的 SQL 测试用例

2. **Supervisor 路由逻辑不够精确**
   - 无法区分 Coverage Analyzer 生成的 SQL 和 SQL Tester 生成的 SQL
   - 没有循环检测机制

3. **Coverage Analyzer 重复生成 SQL**
   - 在 SQL 执行失败后，Coverage Analyzer 又生成了新的 SQL
   - 没有检查是否已经生成过 SQL

## 修复措施

### 1. 改进 SQL Tester 的 Prompt
- **明确禁止生成 SQL**：在 system prompt 中明确说明"只执行 SQL，不生成 SQL"
- **禁止分析或改进 SQL**：如果 SQL 执行失败，只返回错误信息，不要生成新的 SQL

### 2. 改进 `_has_sql_generated` 函数
- **只识别 Coverage Analyzer 生成的 SQL**：
  - 检查消息之前是否有 `Collect_Coverage` 或 `Search_Nearest_Seed` 的调用
  - 检查消息中是否包含"请 SQL Tester 执行"等提示
- **忽略 SQL Tester 生成的 SQL**：避免将 SQL Tester 的分析误认为是 SQL 生成

### 3. 改进 Supervisor 路由逻辑
- **添加循环检测**：
  - 跟踪最近的 Agent 调用
  - 如果同一个 Agent 连续被派发 3 次以上，结束流程
- **更精确的路由判断**：
  - 区分 Coverage Analyzer 生成的 SQL 和 SQL Tester 的分析
  - 避免重复派发

## 修复后的工作流程

```
1. Code Explorer → 获取源代码和调用关系
2. Coverage Analyzer（第一次）→ 收集覆盖率 + 查找种子 + 生成 SQL
3. SQL Tester → 执行 SQL（只执行，不生成）
4. Coverage Analyzer（第二次）→ 验证覆盖率提升
5. Summary → 生成报告
```

## 预期效果

修复后应该能够：
1. ✅ SQL Tester 只执行 SQL，不生成 SQL
2. ✅ Supervisor 能够正确区分 Coverage Analyzer 和 SQL Tester 的消息
3. ✅ 避免无限循环，即使 SQL 执行失败也能正常结束
4. ✅ 如果达到循环检测阈值，自动结束流程

## 测试建议

1. 测试 SQL 执行成功的情况
2. 测试 SQL 执行失败的情况（确保不会无限循环）
3. 测试 Coverage Analyzer 生成多个 SQL 的情况
4. 测试 Supervisor 的循环检测机制
