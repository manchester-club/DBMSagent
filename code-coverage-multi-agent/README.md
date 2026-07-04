# Code Coverage Multi-Agent System

基于 LangGraph 的多 Agent 代码覆盖率提升系统，采用"先试后查"（Try-First-Then-Explore）优化策略。

## 系统架构

本系统包含三个核心 Agent：

1. **Coverage Analyzer**（覆盖率分析专家）
   - 工具：`Collect_Coverage`, `Search_Nearest_Seed`
   - 职责：收集覆盖率、查找SQL种子、生成SQL测试用例

2. **SQL Tester**（SQL测试专家）
   - 工具：`Run_SQL_Test`, `Collect_Coverage`
   - 职责：执行SQL测试用例、验证覆盖率

3. **Code Explorer**（代码探索专家）
   - 工具：`Get_Code_Context`, `Traverse_Call_Graph`
   - 职责：获取函数源代码、分析调用关系

4. **Supervisor**（协调者）
   - 职责：根据工作流程智能派发任务给各个Agent

## 核心工作流程

### 阶段1：快速尝试（基于种子）

```
Supervisor → Coverage Analyzer
  ↓
Coverage Analyzer → Collect_Coverage（收集初始覆盖率）
  ↓
Coverage Analyzer → Search_Nearest_Seed（查找SQL种子）
  ↓
Coverage Analyzer → 基于种子生成简单SQL（不获取代码信息）
  ↓
Supervisor → SQL Tester
  ↓
SQL Tester → Run_SQL_Test（执行SQL）
  ↓
SQL Tester → Collect_Coverage（验证覆盖率）
```

### 阶段2：深入分析（按需探索）

仅在覆盖率未提升时执行：

```
Supervisor → Code Explorer（按需获取代码信息）
  ↓
Code Explorer → Get_Code_Context（获取函数源代码）
  ↓
Code Explorer → Traverse_Call_Graph（分析调用关系）
  ↓
Supervisor → Coverage Analyzer
  ↓
Coverage Analyzer → 基于代码分析生成精确SQL
  ↓
Supervisor → SQL Tester
  ↓
SQL Tester → 执行和验证
```

## 核心特性

- ✅ **先试后查策略**：先基于种子快速测试，失败后再深入分析
- ✅ **按需探索**：只在覆盖率未提升时才获取代码信息
- ✅ **智能路由**：Supervisor 根据工作流程智能派发任务
- ✅ **批量测试**：支持批量测试多个函数
- ✅ **详细日志**：完整的执行过程记录

## 文件结构

```
test_agent/
├── langgraph/
│   ├── coverage_multi_agent.py    # 核心多Agent系统
│   └── nodes/
│       ├── collect_coverage.py    # 覆盖率收集工具
│       ├── search_nearest_seed.py # SQL种子查找工具
│       ├── run_sql_test.py        # SQL测试执行工具
│       ├── get_code_context.py    # 代码获取工具
│       └── traverse_call_graph.py # 调用关系分析工具
├── batch_test_functions.py        # 批量测试脚本
├── dcosd_workflow_ui.html         # UI演示页面
├── jinggu-db-test-platform.html   # 金箍数据库系统测试平台大屏
├── 待测函数集合.md                 # 待测函数列表
├── CORRECT_AGENT_WORKFLOW.md      # 正确工作流程文档
├── AGENT_ARCHITECTURE_AND_WORKFLOW.md  # Agent架构文档
└── README.md                       # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install langgraph langchain langchain-community psycopg2-binary
```

### 2. 配置环境

确保已配置：
- PostgreSQL 数据库连接
- Neo4j 数据库连接（用于调用关系分析）
- LLM API（支持 Ollama 或 OpenAI API）

### 3. 运行单个函数测试

```python
from langgraph.coverage_multi_agent import run_test

result = run_test("dcosd")
```

### 4. 批量测试

```bash
python3 batch_test_functions.py --start-index 0 --end-index 10
```

## 使用示例

### 测试单个函数

```python
from langgraph.coverage_multi_agent import run_test

# 测试 dcosd 函数
result = run_test("dcosd")
print(f"覆盖率: {result['coverage']}%")
```

### 批量测试

```bash
# 测试前10个函数
python3 batch_test_functions.py --start-index 0 --end-index 10

# 跳过零覆盖率函数
python3 batch_test_functions.py --skip-zero
```

## 工作流程优化

本系统实现了"先试后查"（Try-First-Then-Explore）优化策略：

1. **阶段1（快速尝试）**：基于SQL种子快速生成测试用例，不获取代码信息
2. **阶段2（深入分析）**：如果覆盖率未提升，再获取代码信息，生成精确测试用例

这样可以：
- ✅ 提高效率（先尝试快速测试）
- ✅ 节省资源（按需获取代码信息）
- ✅ 实现优化策略（先试后查）

详细流程说明请参考 `CORRECT_AGENT_WORKFLOW.md`。

## 文档

- [金箍数据库系统测试平台大屏](jinggu-db-test-platform.html) - 数据库系统测试平台可视化页面
- [正确工作流程](CORRECT_AGENT_WORKFLOW.md) - 详细的工作流程说明
- [Agent架构和工作流程](AGENT_ARCHITECTURE_AND_WORKFLOW.md) - Agent架构和交互说明
- [dcosd函数工作流程](DCOSD_FUNCTION_CORRECT_WORKFLOW.md) - 具体案例演示

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
