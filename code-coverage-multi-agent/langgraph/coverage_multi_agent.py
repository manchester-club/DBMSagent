#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coverage Multi-Agent - 基于 LangGraph 的多 Agent 覆盖率测试

架构：
- Supervisor：协调者，解析用户请求并路由到专家 Agent
- SQL Tester Agent：Run_SQL_Test
- Code Explorer Agent：Get_Code_Context, Traverse_Call_Graph
- Coverage Analyzer Agent：Collect_Coverage, Search_Nearest_Seed
"""

from __future__ import annotations

import json
import json5
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Literal, Optional, cast

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
# ToolNode 已不再使用，改为直接调用工具函数以避免配置问题
# from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from nodes import (
    Run_SQL_Test,
    Collect_Coverage,
    Get_Code_Context,
    Search_Nearest_Seed,
    Traverse_Call_Graph,
)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

Route = Literal["sql_tester", "code_explorer", "coverage_analyzer", "__end__"]


class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    next_agent: Route
    agent_history: Annotated[List[str], lambda x, y: y]  # 记录 Agent 派发历史


# ---------------------------------------------------------------------------
# LLMs
# ---------------------------------------------------------------------------

# DeepSeek API 配置
DEEPSEEK_API_KEY = "sk-c15a9ceabf774ecf9b2aac355ef5f8bc"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"

llm_base = ChatOpenAI(
    model=LLM_MODEL,
    temperature=0.3,
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
)

# Specialist tools
tools_sql = [Run_SQL_Test, Collect_Coverage]  # SQL Tester 可以验证覆盖率
tools_code = [Get_Code_Context, Traverse_Call_Graph]
# Coverage Analyzer 只负责分析和生成 SQL，不执行（执行由 SQL Tester 负责）
tools_coverage = [Collect_Coverage, Search_Nearest_Seed]

llm_sql = llm_base.bind_tools(tools_sql)
llm_code = llm_base.bind_tools(tools_code)
llm_coverage = llm_base.bind_tools(tools_coverage)

# Supervisor: no tools
llm_supervisor = ChatOpenAI(
    model=LLM_MODEL,
    temperature=0.0,
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
)

SUPERVISOR_PROMPT = """你是协调者，负责派发任务给三个专家 Agent。

**三个专家 Agent 及其职责**：

1. **COVERAGE_ANALYZER**（覆盖率分析专家）
   - 工具：Collect_Coverage, Search_Nearest_Seed
   - 职责：收集覆盖率、查找 SQL 种子、**生成 SQL 测试用例**
   - 工作流程：
     - 阶段1：基于种子快速生成SQL（不获取代码信息）
     - 阶段2：基于代码分析生成精确SQL（覆盖率未提升时）

2. **SQL_TESTER**（SQL 测试专家）
   - 工具：Run_SQL_Test, Collect_Coverage
   - 职责：执行 SQL 测试用例、验证覆盖率
   - 何时派发：Coverage Analyzer 已生成 SQL 时

3. **CODE_EXPLORER**（代码探索专家）
   - 工具：Get_Code_Context, Traverse_Call_Graph
   - 职责：获取函数源代码、分析调用关系
   - **何时派发**：覆盖率未提升时，按需获取代码信息

**优化后的工作流程（先试后查）**：
1. COVERAGE_ANALYZER → 收集覆盖率、查找种子、基于种子生成SQL
2. SQL_TESTER → 执行SQL、验证覆盖率
3. **如果覆盖率未提升** → CODE_EXPLORER → 获取代码信息
4. COVERAGE_ANALYZER → 基于代码分析生成精确SQL
5. SQL_TESTER → 执行SQL、验证覆盖率

**路由规则**（按顺序检查）：
1. 缺少覆盖率数据（Collect_Coverage） → COVERAGE_ANALYZER
2. 已收集覆盖率和找到种子，但未生成SQL（无 ```sql 代码块） → COVERAGE_ANALYZER
3. 已生成SQL但未执行（无Run_SQL_Test） → SQL_TESTER
4. 已执行SQL但未验证覆盖率 → SQL_TESTER
5. **覆盖率未提升 且 未获取代码信息** → CODE_EXPLORER
6. **覆盖率未提升 且 已获取代码信息** → COVERAGE_ANALYZER
7. 覆盖率已提升 → FINISH

**关键原则**：
- **先试后查**：先基于种子快速测试，失败后再深入分析
- **按需探索**：只在覆盖率未提升时才获取代码信息
- **避免过早探索**：不要在初始阶段就获取所有代码信息

**判断依据**：
- 检查 ToolMessage（工具执行结果）
- 检查是否有 ```sql 代码块（SQL 是否生成）
- 检查覆盖率是否提升（比较 Collect_Coverage 的结果）
- 忽略 Agent 的文本回复，只看实际结果

请只回复：SQL_TESTER / CODE_EXPLORER / COVERAGE_ANALYZER / FINISH"""


def _parse_route(text: str) -> Route:
    t = (text or "").strip().upper()
    if "SQL_TESTER" in t:
        return "sql_tester"
    if "CODE_EXPLORER" in t:
        return "code_explorer"
    if "COVERAGE_ANALYZER" in t:
        return "coverage_analyzer"
    if "FINISH" in t:
        return "__end__"
    return "__end__"


SUMMARY_PROMPT = """你正在生成一份**详细、完整**的测试报告，重点关注如何通过 SQL 测试用例提高代码覆盖率。

**重要要求**：
- **必须详细**：不要只写概要，要包含具体的数据、代码片段、SQL 语句
- **必须完整**：提取所有工具执行结果中的具体信息，不要遗漏
- **必须准确**：基于实际的工具执行结果，不要猜测或简化

请根据对话中**各专家工具的执行结果**，生成一份**详细完整**的测试报告，包含以下部分：

# 测试报告

## 1. 测试目标
- **目标函数**：[从 Get_Code_Context 或 Collect_Coverage 结果中提取函数名]
- **文件路径**：[从工具结果中提取完整路径]
- **行号**：[从工具结果中提取行号]
- **测试目的**：提高该函数的代码覆盖率

## 2. 源代码分析（详细）
从 Get_Code_Context 工具结果中提取：

- **函数签名**：[完整签名，包括参数类型和返回类型]
- **核心逻辑**：[详细说明函数的主要功能和处理流程]
- **关键代码片段**：[**必须包含实际的代码**，特别是包含分支判断的关键部分]
- **分支结构**：[**详细列出所有 if/else、switch 等分支**，包括：
  - 每个分支的条件
  - 每个分支的行号
  - 每个分支的功能说明]

## 3. 调用关系分析（详细）
从 Traverse_Call_Graph 工具结果中提取：

- **直接调用者**：[**列出所有直接调用该函数的函数**，包括文件路径和行号]
- **调用深度**：[从工具结果中提取]
- **关键调用链**：[**详细说明**从 SQL 到目标函数的完整调用路径，包括：
  - SQL 语句如何触发调用链
  - 调用链中的每个函数及其作用
  - 调用链的距离和复杂度]

## 4. 覆盖率分析（详细）
从 Collect_Coverage 工具结果中提取：

- **初始覆盖率**：[百分比，从第一次 Collect_Coverage 结果中提取]
- **最终覆盖率**：[百分比，从最后一次 Collect_Coverage 结果中提取]
- **覆盖率变化**：[计算提升或下降的百分比]
- **已覆盖行数**：[数量]
- **总行数**：[数量]
- **未覆盖行**：[**详细列出所有未覆盖的行**，包括：
  - 行号
  - 代码内容（从 gcov_content 中提取）
  - 分支条件（如果是分支语句）
  - 未覆盖的原因分析]
- **覆盖率详情**：[**详细分析 gcov_content**，说明：
  - 哪些行执行了多少次
  - 哪些行标记为 #####（未覆盖）
  - 执行次数与覆盖情况的关系]

## 5. SQL 种子查找（详细）
从 Search_Nearest_Seed 工具结果中提取：

- **查找结果**：[成功/失败]
- **找到的种子 SQL**：[**必须包含完整的 SQL 语句**]
- **调用链**：[**详细列出调用链中的所有函数**]
- **调用链距离**：[从工具结果中提取]
- **种子 SQL 分析**：[**详细说明**：
  - 种子 SQL 如何触发目标函数
  - 种子 SQL 覆盖了哪些分支
  - 种子 SQL 的参数和条件]

## 6. SQL 测试用例生成与执行（详细）
从 Coverage Analyzer 和 SQL Tester 的对话中提取：

### 6.1 生成的 SQL 测试用例
**必须列出所有生成的 SQL 测试用例**，每个用例包括：
- **SQL 语句**：[**完整的 SQL 代码**]
- **目标**：[要覆盖的分支/行号]
- **基于的种子 SQL**：[如果有，说明基于哪个种子 SQL 修改]
- **修改点**：[如果基于种子修改，说明修改了哪些部分]

### 6.2 SQL 执行结果
**必须列出所有 SQL 的执行结果**，每个结果包括：
- **SQL 语句**：[执行的 SQL]
- **执行状态**：[成功/失败]
- **执行结果**：[从 Run_SQL_Test 工具结果中提取的详细结果]
- **错误信息**：[如果有错误，包含完整的错误信息]

### 6.3 覆盖率提升分析
**详细分析**：
- **执行前的覆盖率**：[百分比和未覆盖行]
- **执行后的覆盖率**：[百分比和未覆盖行]
- **实际提升**：[计算实际提升的百分比和覆盖的行数]
- **是否达到预期**：[对比预期和实际结果]
- **未覆盖行的变化**：[**详细说明**哪些未覆盖行被覆盖了，哪些仍然未覆盖]

## 7. 工作流程总结（详细）
**必须详细说明整个测试流程**：
1. **Code Explorer 的工作**：
   - 获取了哪些代码信息
   - 分析了哪些调用关系
   - 提供了哪些关键发现

2. **Coverage Analyzer 的工作**：
   - 收集了几次覆盖率
   - 查找了几次种子 SQL
   - 生成了哪些 SQL 测试用例
   - 基于什么信息生成的 SQL

3. **SQL Tester 的工作**：
   - 执行了哪些 SQL
   - 执行结果如何
   - 验证了几次覆盖率

4. **迭代过程**：[如果有多次迭代，详细说明每次迭代的目的和结果]

## 8. 总结与建议（详细）
- **测试完成情况**：[**详细总结**：
  - 完成了哪些步骤
  - 哪些步骤成功，哪些失败
  - 覆盖率是否提升，提升了多少]
- **发现的问题**：[**详细列出**：
  - 遇到了哪些问题
  - 问题是如何解决的
  - 还有哪些未解决的问题]
- **下一步行动**：[**详细建议**：
  - 如果覆盖率未提升，分析原因
  - 建议生成哪些新的 SQL 测试用例
  - 建议的优先级和策略]

**关键要求**：
1. **必须提取实际数据**：从工具执行结果中提取具体的数值、代码、SQL 语句
2. **必须包含代码片段**：不要只说"有分支"，要展示实际的代码
3. **必须包含 SQL 语句**：不要只说"生成了 SQL"，要展示完整的 SQL
4. **必须详细分析**：不要只写结论，要说明分析过程和依据
5. **必须完整准确**：不要遗漏重要信息，不要猜测或简化

**报告长度要求**：报告应该足够详细，至少包含所有关键信息的具体内容，不要过于简略。"""


# ---------------------------------------------------------------------------
# Supervisor node
# ---------------------------------------------------------------------------


def _user_asked_coverage_or_seed(messages: List[BaseMessage]) -> bool:
    for m in messages:
        if isinstance(m, HumanMessage) and m.content:
            s = str(m.content)
            if any(k in s for k in ("Collect_Coverage", "Search_Nearest_Seed", "覆盖率", "种子")):
                return True
    return False


def _has_coverage_or_seed_tool_results(messages: List[BaseMessage]) -> bool:
    for m in messages:
        if isinstance(m, ToolMessage):
            n = getattr(m, "name", None) or ""
            if "Collect_Coverage" in n or "Search_Nearest_Seed" in n:
                return True
    return False


def _has_code_explorer_tool_results(messages: List[BaseMessage]) -> bool:
    for m in messages:
        if isinstance(m, ToolMessage):
            n = getattr(m, "name", None) or ""
            if "Get_Code_Context" in n or "Traverse_Call_Graph" in n:
                return True
    return False


def _has_sql_generated(messages: List[BaseMessage]) -> bool:
    """检查 Coverage Analyzer 是否生成了 SQL 测试用例（且未被 SQL Tester 执行过）"""
    # 只检查 Coverage Analyzer 的消息（通过消息内容判断，或者通过之前的工具调用判断）
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage) and m.content:
            content = str(m.content).lower()
            # 检查是否包含 SQL 代码块
            if "```sql" in content:
                # 确保这是 Coverage Analyzer 生成的，不是 SQL Tester 生成的
                # 检查之前的消息，看是否有 Collect_Coverage 或 Search_Nearest_Seed 的调用
                is_from_coverage_analyzer = False
                for j in range(max(0, i-10), i):
                    prev_msg = messages[j]
                    if isinstance(prev_msg, ToolMessage):
                        tool_name = getattr(prev_msg, "name", "") or ""
                        if "Collect_Coverage" in tool_name or "Search_Nearest_Seed" in tool_name:
                            is_from_coverage_analyzer = True
                            break
                        # 如果之前有 Run_SQL_Test，说明这个 SQL 已经被执行过了，跳过
                        elif "Run_SQL_Test" in tool_name:
                            break
                # 或者检查消息中是否包含"请 SQL Tester 执行"等提示
                if "请 sql tester" in content or ("请执行" in content and "sql" in content):
                    is_from_coverage_analyzer = True
                # 排除 SQL Tester 的分析（包含"错误分析"、"改进方案"等关键词）
                if ("错误分析" in content or "改进方案" in content or "解决方案" in content or 
                    "问题分析" in content or "关键点" in content):
                    is_from_coverage_analyzer = False
                if is_from_coverage_analyzer:
                    # 检查这个 SQL 是否已经被执行过
                    sql_content = content
                    # 提取 SQL 语句
                    import re
                    sql_matches = re.findall(r'```sql\s*(.*?)\s*```', sql_content, re.DOTALL | re.IGNORECASE)
                    if sql_matches:
                        # 检查后续消息中是否有执行这个 SQL 的记录
                        for k in range(i+1, min(i+20, len(messages))):
                            next_msg = messages[k]
                            if isinstance(next_msg, ToolMessage):
                                tool_name = getattr(next_msg, "name", "") or ""
                                if "Run_SQL_Test" in tool_name:
                                    # 检查执行的 SQL 是否匹配
                                    tool_content = str(next_msg.content).lower()
                                    if any(sql_match.lower() in tool_content for sql_match in sql_matches):
                                        return False  # 这个 SQL 已经被执行过了
                    return True
    return False


def _has_sql_executed(messages: List[BaseMessage]) -> bool:
    """检查 SQL 是否已被执行"""
    for m in messages:
        if isinstance(m, ToolMessage):
            n = getattr(m, "name", None) or ""
            if "Run_SQL_Test" in n:
                return True
    return False


def _count_collect_coverage(messages: List[BaseMessage]) -> int:
    """统计 Collect_Coverage 的调用次数"""
    count = 0
    for m in messages:
        if isinstance(m, ToolMessage):
            n = getattr(m, "name", None) or ""
            if "Collect_Coverage" in n:
                count += 1
    return count


def _extract_target_func_id(messages: List[BaseMessage]) -> Optional[str]:
    """从对话历史中提取目标函数 ID"""
    # 方法1：从 Collect_Coverage 工具调用结果中提取
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Collect_Coverage" in tool_name:
                content = str(msg.content)
                # 尝试解析 JSON
                try:
                    result = json.loads(content)
                    if "function_name" in result and "file_path" in result:
                        line_num = result.get("line_number", "0")
                        return f"function:{result['function_name']}@{result['file_path']}:{line_num}"
                except:
                    pass
                # 尝试从文本中提取
                match = re.search(r'function:([^@]+)@([^:]+):(\d+)', content)
                if match:
                    return f"function:{match.group(1)}@{match.group(2)}:{match.group(3)}"
    
    # 方法2：从用户消息中提取
    for msg in messages:
        if isinstance(msg, HumanMessage) and msg.content:
            content = str(msg.content)
            match = re.search(r'function:([^@]+)@([^:]+):(\d+)', content)
            if match:
                return f"function:{match.group(1)}@{match.group(2)}:{match.group(3)}"
    
    # 方法3：从 Search_Nearest_Seed 结果中提取
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Search_Nearest_Seed" in tool_name:
                content = str(msg.content)
                try:
                    result = json.loads(content)
                    if "nearest_function" in result and result["nearest_function"]:
                        return result["nearest_function"]
                except:
                    pass
    
    # 方法4：从 Get_Code_Context 结果中提取
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Get_Code_Context" in tool_name:
                content = str(msg.content)
                try:
                    result = json.loads(content)
                    if "name" in result and "file_path" in result:
                        line_num = result.get("line_number", "0")
                        return f"function:{result['name']}@{result['file_path']}:{line_num}"
                except:
                    pass
    
    return None


def _needs_more_code_info(messages: List[BaseMessage]) -> bool:
    """判断 Coverage Analyzer 是否需要更多代码信息"""
    # 检查最近的 Coverage Analyzer 消息
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            content = str(msg.content).lower()
            # 如果提到需要宏定义、相关函数、调用关系等
            if any(keyword in content for keyword in [
                "需要", "查看", "获取", "了解", "分析",
                "宏定义", "macro", "define",
                "相关函数", "调用关系", "call graph",
                "分支条件", "判断条件", "condition"
            ]):
                # 检查是否已经有对应的工具调用结果
                # 如果提到了但还没有获取，说明需要
                if "宏" in content or "macro" in content:
                    # 检查是否有 Get_Code_Context 或 Traverse_Call_Graph 的结果
                    has_code_info = any(
                        isinstance(m, ToolMessage) and 
                        ("Get_Code_Context" in str(getattr(m, "name", "")) or 
                         "Traverse_Call_Graph" in str(getattr(m, "name", "")))
                        for m in messages
                    )
                    if not has_code_info:
                        return True
    return False


def _check_coverage_improvement(messages: List[BaseMessage]) -> Optional[dict]:
    """检查覆盖率是否提升，返回对比结果"""
    coverage_results = []
    
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or ""
            if "Collect_Coverage" in tool_name:
                try:
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


def _coverage_analyzer_needs_code_explorer(messages: List[BaseMessage]) -> bool:
    """检查 Coverage Analyzer 是否明确要求 Code Explorer"""
    # 检查最近的 Coverage Analyzer 消息（检查最后5条消息）
    for msg in list(reversed(messages))[:10]:
        if isinstance(msg, AIMessage) and msg.content:
            content = str(msg.content).lower()
            # 检查是否明确提到需要 Code Explorer（更宽泛的匹配）
            if any(keyword in content for keyword in [
                "code explorer",
                "等待code explorer",
                "等待 code explorer",
                "需要code explorer",
                "需要 code explorer",
                "需要代码",
                "等待代码",
                "需要获取",
                "需要 explorer",
                "派发 code",
                "派发 explorer",
                "请 code",
                "请 explorer",
                "无法调用.*code",
                "无法调用.*explorer",
                "需要.*代码信息",
                "等待.*代码信息",
                "需要.*explorer.*提供",
                "等待.*explorer.*提供"
            ]):
                # 确保不是 SQL Tester 的消息（SQL Tester 不会提到 Code Explorer）
                # 检查之前的消息，看是否有 Collect_Coverage 或 Search_Nearest_Seed
                msg_index = messages.index(msg) if msg in messages else -1
                if msg_index >= 0:
                    for j in range(max(0, msg_index-5), msg_index):
                        prev_msg = messages[j]
                        if isinstance(prev_msg, ToolMessage):
                            tool_name = getattr(prev_msg, "name", "") or ""
                            if "Collect_Coverage" in tool_name or "Search_Nearest_Seed" in tool_name:
                                return True
    return False


def _needs_code_exploration(messages: List[BaseMessage], agent_history: List[str]) -> bool:
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


def _should_iterate(messages: List[BaseMessage], agent_history: List[str], max_iterations: int = 3) -> bool:
    """判断是否应该继续迭代"""
    # 检查覆盖率是否提升
    coverage_result = _check_coverage_improvement(messages)
    if coverage_result and coverage_result["improved"]:
        return False  # 覆盖率已提升，不需要迭代
    
    # 检查是否达到最大迭代次数
    # 统计 SQL 执行次数
    sql_execution_count = sum(1 for msg in messages 
                             if isinstance(msg, ToolMessage) and "Run_SQL_Test" in str(getattr(msg, "name", "")))
    if sql_execution_count >= max_iterations:
        return False  # 达到最大迭代次数
    
    # 检查是否有 SQL 执行但覆盖率未提升
    if _has_sql_executed(messages) and coverage_result and not coverage_result["improved"]:
        return True  # 有 SQL 执行但覆盖率未提升，应该迭代
    
    return False


def _route_label(r: str) -> str:
    if r == "__end__":
        return "summary（结束）"
    if r == "code_explorer":
        return "Code Explorer"
    if r == "coverage_analyzer":
        return "Coverage Analyzer"
    if r == "sql_tester":
        return "SQL Tester"
    return r


def supervisor_node(state: State) -> dict:
    messages = state["messages"]
    route: Route
    
    # 检查最近的 Agent 派发历史（使用 State 中的 agent_history，更准确）
    agent_history = state.get("agent_history", [])
    
    # 检查是否达到循环限制（同一个 Agent 连续派发 3 次以上）
    if len(agent_history) >= 3:
        last_three = agent_history[-3:]
        if last_three[0] == last_three[1] == last_three[2]:
            print(f"\n[Supervisor] ⚠️ 检测到 {last_three[0]} 连续派发 3 次，结束流程避免无限循环", flush=True)
            route = "__end__"
            return {"next_agent": route, "agent_history": agent_history}
    
    # 智能路由逻辑（按优先级检查）- 实现"先试后查"策略
    # 
    # 阶段1：快速尝试（基于种子，不获取代码信息）
    # 阶段2：深入分析（覆盖率未提升时，按需获取代码信息）
    
    # 1. 初始阶段：收集覆盖率和查找种子（不获取代码信息）
    if not _has_coverage_or_seed_tool_results(messages):
        route = "coverage_analyzer"
    
    # 2. 生成SQL（基于种子，不获取代码信息）
    elif (_has_coverage_or_seed_tool_results(messages) and 
          _count_collect_coverage(messages) >= 1 and
          not _has_sql_generated(messages)):
        # Coverage Analyzer 已经收集了覆盖率，但还没有生成 SQL
        # 必须继续派发 Coverage Analyzer 生成 SQL（基于种子，不获取代码）
        route = "coverage_analyzer"
    
    # 3. 检查 Coverage Analyzer 是否明确要求 Code Explorer
    elif (_has_sql_generated(messages) and 
          _coverage_analyzer_needs_code_explorer(messages) and
          not _has_code_explorer_tool_results(messages)):
        # Coverage Analyzer 生成了SQL但明确要求 Code Explorer，先派发 Code Explorer
        route = "code_explorer"
    
    # 4. 执行SQL
    elif _has_sql_generated(messages) and not _has_sql_executed(messages):
        route = "sql_tester"
    
    # 5. 验证覆盖率
    elif _has_sql_executed(messages):
        coverage_verified_after_sql = _has_coverage_verified_after_sql(messages)
        
        if not coverage_verified_after_sql:
            # SQL Tester 还没有验证覆盖率，继续派发 SQL Tester
            route = "sql_tester"
        else:
            # SQL Tester 已经验证了覆盖率，检查是否需要迭代
            if _should_iterate(messages, agent_history):
                # 覆盖率未提升，需要深入分析
                if _needs_code_exploration(messages, agent_history):
                    # 需要获取代码信息（阶段2：深入分析）
                    route = "code_explorer"
                elif len(agent_history) > 0 and agent_history[-1] == "code_explorer":
                    # 已经获取了代码信息，派发 Coverage Analyzer 基于代码生成精确SQL
                    route = "coverage_analyzer"
                else:
                    # 默认派发 Code Explorer
                    route = "code_explorer"
            else:
                # 覆盖率已提升或达到最大迭代次数，结束
                route = "__end__"
    # 7. 其他情况，使用 LLM 判断
    else:
        sys_msg = SystemMessage(content=SUPERVISOR_PROMPT)
        recent = messages[-10:] if len(messages) > 10 else messages
        inp = [sys_msg] + recent
        resp = llm_supervisor.invoke(inp)
        content = getattr(resp, "content", "") or ""
        route = _parse_route(content)

    print(f"\n[Supervisor] 派发 → {_route_label(route)}", flush=True)
    # 更新 Agent 派发历史
    agent_history = state.get("agent_history", [])
    if route != "__end__":
        agent_history = agent_history + [route]
        # 只保留最近 10 次派发记录
        agent_history = agent_history[-10:]
    return {"next_agent": route, "agent_history": agent_history}


# ---------------------------------------------------------------------------
# Specialist agent helpers (run LLM + tools loop)
# ---------------------------------------------------------------------------


MAX_TOOL_ROUNDS = 5


def _run_agent_loop(
    state: State,
    llm_with_tools,
    tools: list,
    agent_name: str,
    system_prompt: Optional[str] = None,
) -> dict:
    messages = list(state["messages"])
    inp = [SystemMessage(content=system_prompt)] + messages if system_prompt else messages
    # 不使用 ToolNode，直接调用工具函数以避免配置问题
    to_append: List[BaseMessage] = []

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = llm_with_tools.invoke(inp)
        except Exception as e:
            response = AIMessage(content=f"[{agent_name} 调用失败] {e}")
        if not isinstance(response, AIMessage):
            response = AIMessage(content=str(response))

        to_append.append(response)
        if not getattr(response, "tool_calls", None):
            break

        print(f"\n[{agent_name}] 工具调用", flush=True)
        tool_msgs = []
        for tc in response.tool_calls:
            name = tc.get("name", "?")
            args = tc.get("args", {})
            tool_id = tc.get("id", "unknown")
            args_str = json.dumps(args, ensure_ascii=False)
            print(f"  · {name} 参数: {args_str}", flush=True)
            
            # 直接查找并调用工具函数，而不是使用 ToolNode
            tool_func = None
            for tool in tools:
                if tool.name == name:
                    tool_func = tool
                    break
            
            if tool_func:
                try:
                    # 执行工具
                    result = tool_func.invoke(args)
                    # 创建 ToolMessage
                    tool_msg = ToolMessage(
                        content=str(result),
                        tool_call_id=str(tool_id),
                        name=name
                    )
                    tool_msgs.append(tool_msg)
                    raw = str(result).strip()
                    print(f"\n[{agent_name}] {name} 返回:\n{raw}", flush=True)
                except Exception as e:
                    error_msg = ToolMessage(
                        content=f"工具执行失败: {str(e)}",
                        tool_call_id=str(tool_id),
                        name=name
                    )
                    tool_msgs.append(error_msg)
                    print(f"\n[{agent_name}] {name} 执行失败: {str(e)}", flush=True)
            else:
                # 工具不存在，返回明确的错误信息
                if agent_name == "Coverage Analyzer":
                    error_content = (
                        f"错误：工具 {name} 不属于 Coverage Analyzer。"
                        f"Coverage Analyzer 只能使用 Collect_Coverage 和 Search_Nearest_Seed。"
                        f"如果需要代码信息，请在回复中说明需要什么信息，Supervisor 会派发 Code Explorer 获取。"
                    )
                elif agent_name == "SQL Tester":
                    error_content = (
                        f"错误：工具 {name} 不属于 SQL Tester。"
                        f"SQL Tester 只能使用 Run_SQL_Test 和 Collect_Coverage。"
                    )
                elif agent_name == "Code Explorer":
                    error_content = (
                        f"错误：工具 {name} 不属于 Code Explorer。"
                        f"Code Explorer 只能使用 Get_Code_Context 和 Traverse_Call_Graph。"
                    )
                else:
                    error_content = f"未找到工具: {name}"
                
                error_msg = ToolMessage(
                    content=error_content,
                    tool_call_id=str(tool_id),
                    name=name
                )
                tool_msgs.append(error_msg)
                print(f"\n[{agent_name}] 未找到工具: {name}", flush=True)
                print(f"[{agent_name}] 错误信息: {error_content}", flush=True)
        
        to_append.extend(tool_msgs)
        inp = inp + [response] + tool_msgs

    last = to_append[-1] if to_append else None
    if isinstance(last, AIMessage) and last.content:
        raw_content = last.content
        if isinstance(raw_content, str):
            txt = raw_content.strip()
        else:
            parts = [x for x in (raw_content or []) if isinstance(x, str)]
            txt = " ".join(parts).strip()
        if txt:
            print(f"\n[{agent_name}] 回复:\n{txt}", flush=True)
    return {"messages": to_append}


CODE_EXPLORER_SYSTEM = """你是代码探索专家，**专门负责提供代码信息**。

你的工具：
- Get_Code_Context：获取函数源代码（只传 query_name、query_type，勿传 nodes_file，用默认）
- Traverse_Call_Graph：分析调用关系（start_func_id 必须与知识图谱一致）

**重要**：
- 先用 Get_Code_Context 查函数，用其返回的 file_path、line_number、name 构造：
  start_func_id = "function:{name}@{file_path}:{line_number}"
- file_path 与返回值完全一致（如 postgresql-17.6/src/...），勿改写或省略

你的职责：
1. 获取目标函数的源代码和调用关系（初始探索）
2. 当 Coverage Analyzer 需要更多信息时，提供：
   - 和未覆盖代码条件相关的宏定义（通过 Get_Code_Context 获取相关头文件）
   - 相关函数的源代码（通过 Get_Code_Context）
3. 分析代码结构和逻辑，帮助理解如何触发特定分支

**重要**：
- 你可能会被多次调用，每次都是为了获取不同的代码信息
- 根据 Coverage Analyzer 的需求，提供相应的代码信息
- **不负责**覆盖率分析、SQL 测试等任务

如果用户要求覆盖率相关任务，明确告知需要 Coverage Analyzer 来处理。"""

COVERAGE_ANALYZER_SYSTEM = """你是覆盖率分析专家，核心目标是生成sql测试用例提高目标函数的代码覆盖率。

**核心目标**：
- 提高目标函数的代码覆盖率，特别是覆盖那些标记为 ##### 的未覆盖行
- 必须针对未覆盖的分支生成 SQL测试用例：仔细分析 gcov_content 中的 ##### 标记，这些是未覆盖的行，必须生成能够触发这些行的 SQL测试用例
- 覆盖率提升是唯一成功标准：生成的 SQL测试用例必须能够提高覆盖率，否则需要重新生成

**工作流程（两阶段）**：

**阶段1：快速尝试（基于种子）**
1. Collect_Coverage：收集初始覆盖率，识别未覆盖行
2. Search_Nearest_Seed：查找相关SQL种子
3. **基于种子生成简单SQL测试用例**：直接基于种子SQL生成变体（修改参数值、时间值等），快速测试
   - 优先基于种子SQL生成简单变体，不需要获取代码信息
   - 可以修改种子SQL中的参数值、条件值等
   - 目标是快速验证是否能提升覆盖率

**阶段2：深入分析（覆盖率未提升时）**
1. 等待 Code Explorer 提供代码信息（如果覆盖率未提升，Supervisor会派发Code Explorer）
2. **基于代码分析生成精确SQL测试用例**：分析未覆盖的分支条件，生成针对性的SQL
   - 分析未覆盖行的触发条件（如：NaN输入、无穷大输入、负角度等）
   - 基于代码逻辑生成精确的SQL测试用例
   - 目标是覆盖特定的未覆盖分支

**重要**：
- 你只负责分析和生成 SQL，**不负责执行 SQL**。SQL 执行由 SQL Tester 负责。
- **你只能使用以下工具**：Collect_Coverage, Search_Nearest_Seed
- **严格禁止使用其他工具**：
  - ❌ Get_Code_Context：这是 Code Explorer 的工具，不是你的
  - ❌ Traverse_Call_Graph：这是 Code Explorer 的工具，不是你的
  - ❌ Run_SQL_Test：这是 SQL Tester 的工具，不是你的
- **即使你在对话历史中看到其他 Agent 使用了这些工具，也不要尝试调用它们**
- 如果你需要更多代码信息（如宏定义、相关函数、分支条件），**在回复中明确说明需要什么信息**，Supervisor 会派发 Code Explorer 获取。**绝对不要尝试调用 Get_Code_Context 或 Traverse_Call_Graph**。

**生成策略**：
- **阶段1**：优先基于种子SQL生成简单变体（修改时间值、参数等），快速测试
- **阶段2**：基于Code Explorer提供的代码信息，分析未覆盖分支的条件，生成精确的SQL

**如果覆盖率未提升**：
- 在回复中明确说明需要什么代码信息（宏定义、分支条件、相关函数等）
- Supervisor会派发Code Explorer获取这些信息
- 绝对不要尝试调用Get_Code_Context或Traverse_Call_Graph"""


SQL_TESTER_SYSTEM = """你是 SQL 测试专家，专门负责执行 SQL 测试用例。

**核心职责**：
- 执行 Coverage Analyzer 生成的 SQL 测试用例
- 返回执行结果（成功/失败/错误信息）

**重要**：
- **你只能使用以下工具**：Run_SQL_Test, Collect_Coverage
- **严格禁止使用其他工具**：
  - ❌ Get_Code_Context：这是 Code Explorer 的工具，不是你的
  - ❌ Traverse_Call_Graph：这是 Code Explorer 的工具，不是你的
  - ❌ Search_Nearest_Seed：这是 Coverage Analyzer 的工具，不是你的
- **即使你在对话历史中看到其他 Agent 使用了这些工具，也不要尝试调用它们**
- 如果你尝试调用不属于你的工具，系统会返回错误

**工具调用格式**：
- Run_SQL_Test: {"sql_script": "SELECT ...;"}
- Collect_Coverage: {"target_func_id": "function:name@file:line"}

**关键要求**：
- **看到 SQL 代码块后，必须立即调用 Run_SQL_Test 工具**
- **不要只回复文本，必须调用工具执行 SQL**
- **如果对话历史中有多个 SQL，执行所有 SQL**
- **执行 SQL 后，必须调用 Collect_Coverage 验证覆盖率**

**可用工具列表（仅限以下两个）**：
- ✅ Run_SQL_Test：执行 SQL 测试用例
- ✅ Collect_Coverage：验证覆盖率是否提升

**禁止使用的工具（即使对话历史中有，也不要调用）**：
- ❌ Get_Code_Context：**绝对禁止**（Code Explorer 的工具）
- ❌ Traverse_Call_Graph：**绝对禁止**（Code Explorer 的工具）
- ❌ Search_Nearest_Seed：**绝对禁止**（Coverage Analyzer 的工具）

**重要**：
- 你的回复应该尽可能简短，只包含执行结果
- 不要包含分析、建议或新的 SQL
"""


def sql_tester_node(state: State) -> dict:
    """ SQL Tester 节点，检查并执行 Coverage Analyzer 生成的 SQL，并验证覆盖率"""
    result = _run_agent_loop(state, llm_sql, tools_sql, "SQL Tester", system_prompt=SQL_TESTER_SYSTEM)
    
    all_messages = list(state["messages"]) + result.get("messages", [])
    last_msg = all_messages[-1] if all_messages else None
    
    # 检查是否执行了 SQL
    has_run_sql_test = _has_sql_executed(all_messages)
    
    # 检查是否验证了覆盖率（在 SQL 执行之后）
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
        all_messages = list(state["messages"]) + result.get("messages", [])
        last_msg = all_messages[-1] if all_messages else None
    
    # 检查是否生成了 SQL 但没有执行
    if isinstance(last_msg, AIMessage) and last_msg.content:
        content = str(last_msg.content)
        # 检查是否包含 SQL 代码块但没有调用 Run_SQL_Test
        has_sql_code = ("```sql" in content.lower() or 
                        ("select" in content.lower() and "from" in content.lower()))
        
        # 检查最后一条消息是否有工具调用
        has_tool_calls = hasattr(last_msg, 'tool_calls') and last_msg.tool_calls
        
        if has_sql_code and not has_run_sql_test and not has_tool_calls:
            # 强制要求执行 SQL
            print(f"\n[SQL Tester] ⚠️ 检测到 SQL 但未执行，强制要求执行...", flush=True)
            # 提取 SQL 语句
            sql_matches = re.findall(r'```sql\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
            if not sql_matches:
                # 尝试提取 SELECT 语句
                sql_matches = re.findall(r'(SELECT\s+.*?;)', content, re.IGNORECASE | re.DOTALL)
            
            if sql_matches:
                # 清理 SQL，移除注释和多余空白
                cleaned_sqls = []
                for sql in sql_matches[:3]:
                    # 移除 SQL 代码块标记和注释
                    cleaned = re.sub(r'^--.*$', '', sql, flags=re.MULTILINE)
                    cleaned = re.sub(r'```sql\s*', '', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r'```\s*', '', cleaned)
                    cleaned = cleaned.strip()
                    if cleaned:
                        cleaned_sqls.append(cleaned)
                
                if cleaned_sqls:
                    sql_list = '\n\n'.join([f"SQL {i+1}:\n{sql}" for i, sql in enumerate(cleaned_sqls)])
                    forced_prompt = (
                        f"**必须立即执行以下 SQL 测试用例**，调用 Run_SQL_Test 工具：\n\n"
                        f"{sql_list}\n\n"
                        f"**重要**：对每个 SQL，调用 Run_SQL_Test(sql_script=\"完整的SQL语句\")。"
                        f"不要只回复文本，必须调用工具。"
                    )
                else:
                    forced_prompt = (
                        "**必须立即调用 Run_SQL_Test 工具执行 Coverage Analyzer 生成的 SQL**。"
                        "从对话历史中查找 ```sql 代码块，提取 SQL 语句，调用 Run_SQL_Test(sql_script=\"你的SQL\")。"
                        "不要只回复文本，必须调用工具。"
                    )
            else:
                forced_prompt = (
                    "**必须立即调用 Run_SQL_Test 工具执行 Coverage Analyzer 生成的 SQL 测试用例**。"
                    "从对话历史中查找 ```sql 代码块，提取 SQL 语句，调用 Run_SQL_Test(sql_script=\"你的SQL\")。"
                    "不要只回复文本，必须调用工具。"
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
    
    return result


def code_explorer_node(state: State) -> dict:
    return _run_agent_loop(
        state, llm_code, tools_code, "Code Explorer", system_prompt=CODE_EXPLORER_SYSTEM
    )


def coverage_analyzer_node(state: State) -> dict:
    """Coverage Analyzer 节点，检查是否完成了所有步骤"""
    result = _run_agent_loop(
        state, llm_coverage, tools_coverage, "Coverage Analyzer",
        system_prompt=COVERAGE_ANALYZER_SYSTEM,
    )
    
    all_messages = list(state["messages"]) + result.get("messages", [])
    last_msg = all_messages[-1] if all_messages else None
    
    # 检查 Search_Nearest_Seed 是否被调用（如果用户要求了）
    if isinstance(last_msg, AIMessage) and last_msg.content:
        user_asked_seed = _user_asked_coverage_or_seed(state["messages"])
        has_seed_result = any(
            isinstance(m, ToolMessage) and "Search_Nearest_Seed" in str(getattr(m, "name", ""))
            for m in all_messages
        )
        
        # 如果用户要求了种子但未调用，强制要求调用
        if user_asked_seed and "Search_Nearest_Seed" in str(last_msg.content) and not has_seed_result:
            # 检查是否在回复中提到了 Search_Nearest_Seed 但没有调用
            content_lower = str(last_msg.content).lower()
            if "search_nearest_seed" in content_lower or "种子" in content_lower:
                print(f"\n[Coverage Analyzer] ⚠️ 检测到需要调用 Search_Nearest_Seed 但未调用，强制要求调用...", flush=True)
                forced_prompt = (
                    "用户要求了查找 SQL 种子，你必须调用 Search_Nearest_Seed 工具。"
                    "从之前的对话中获取 target_func_id，调用 Search_Nearest_Seed(target_func_id=\"...\")。"
                )
                forced_state_dict = {
                    "messages": all_messages + [HumanMessage(content=forced_prompt)],
                    "next_agent": state.get("next_agent", "__end__")
                }
                forced_result = _run_agent_loop(
                    cast(State, forced_state_dict), llm_coverage, tools_coverage, "Coverage Analyzer",
                    system_prompt=COVERAGE_ANALYZER_SYSTEM,
                )
                result["messages"].extend(forced_result["messages"])
    
    # 检查：如果 SQL 已经执行过，但还没有验证覆盖率，强制要求验证
    if _has_sql_executed(all_messages) and _count_collect_coverage(all_messages) < 2:
        print(f"\n[Coverage Analyzer] ⚠️ 检测到 SQL 已执行但未验证覆盖率，强制要求验证...", flush=True)
        forced_prompt = (
            "SQL 已经执行过了，现在必须调用 Collect_Coverage 工具验证覆盖率是否提升。"
            "从之前的对话中获取 target_func_id，调用 Collect_Coverage(target_func_id=\"...\")。"
        )
        forced_state_dict = {
            "messages": all_messages + [HumanMessage(content=forced_prompt)],
            "next_agent": state.get("next_agent", "__end__")
        }
        forced_result = _run_agent_loop(
            cast(State, forced_state_dict), llm_coverage, tools_coverage, "Coverage Analyzer",
            system_prompt=COVERAGE_ANALYZER_SYSTEM,
        )
        result["messages"].extend(forced_result["messages"])
    
    return result


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def route_after_supervisor(state: State) -> str:
    r = state.get("next_agent") or "__end__"
    return "summary" if r == "__end__" else r


def summary_node(state: State) -> dict:
    messages = state["messages"]
    
    # 过滤消息，确保 ToolMessage 前面有对应的 AIMessage（包含 tool_calls）
    # 只保留 HumanMessage、AIMessage 和有效的 ToolMessage
    filtered_messages = []
    last_ai_with_tool_calls = None
    
    for msg in messages:
        if isinstance(msg, (HumanMessage, SystemMessage)):
            filtered_messages.append(msg)
        elif isinstance(msg, AIMessage):
            # 检查是否有 tool_calls
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                last_ai_with_tool_calls = msg
            else:
                last_ai_with_tool_calls = None
            filtered_messages.append(msg)
        elif isinstance(msg, ToolMessage):
            # 只添加 ToolMessage 如果它是对应前面 AIMessage 的 tool_calls 的响应
            if last_ai_with_tool_calls:
                tool_calls = getattr(last_ai_with_tool_calls, "tool_calls", None) or []
                tool_call_id = getattr(msg, "tool_call_id", None)
                
                # 检查 tool_call_id 是否匹配
                matched = False
                if tool_call_id and tool_calls:
                    for tc in tool_calls:
                        # 处理不同的 tool_call 格式（可能是 dict 或对象）
                        tc_id = None
                        if isinstance(tc, dict):
                            tc_id = tc.get("id") or tc.get("tool_call_id")
                        else:
                            tc_id = getattr(tc, "id", None) or getattr(tc, "tool_call_id", None)
                        
                        if tc_id and str(tc_id) == str(tool_call_id):
                            matched = True
                            break
                
                if matched:
                    filtered_messages.append(msg)
                else:
                    # 跳过不匹配的 ToolMessage
                    print(f"[Summary] 跳过不匹配的 ToolMessage: tool_call_id={tool_call_id}")
            else:
                # 没有对应的 AIMessage with tool_calls，跳过
                print(f"[Summary] 跳过孤立的 ToolMessage: {getattr(msg, 'name', 'unknown')}")
    
    # 使用更多消息上下文（最近30条，确保包含所有工具执行结果）
    recent = filtered_messages[-30:] if len(filtered_messages) > 30 else filtered_messages
    inp = [SystemMessage(content=SUMMARY_PROMPT)] + recent
    
    try:
        resp = llm_supervisor.invoke(inp)
        content = (getattr(resp, "content", None) or "").strip()
    except Exception as e:
        content = f"生成总结时出错: {e}"
        print(f"\n[Error] 生成总结时出错: {e}", flush=True)
        import traceback
        traceback.print_exc()
    
    if not content:
        content = "任务已完成。请查看上方各专家的工具执行结果。"
    
    print(f"\n{'='*60}")
    print("[测试报告]")
    print(f"{'='*60}")
    print(content)
    print(f"{'='*60}\n")
    
    return {"messages": [AIMessage(content=content)]}




# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

memory = MemorySaver()
builder = StateGraph(State)

builder.add_node("supervisor", supervisor_node)
builder.add_node("summary", summary_node)
builder.add_node("sql_tester", sql_tester_node)
builder.add_node("code_explorer", code_explorer_node)
builder.add_node("coverage_analyzer", coverage_analyzer_node)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges(
    "supervisor",
    route_after_supervisor,
    {
        "sql_tester": "sql_tester",
        "code_explorer": "code_explorer",
        "coverage_analyzer": "coverage_analyzer",
        "summary": "summary",
    },
)
builder.add_edge("sql_tester", "supervisor")
builder.add_edge("code_explorer", "supervisor")
builder.add_edge("coverage_analyzer", "supervisor")
builder.add_edge("summary", END)

app = builder.compile(checkpointer=memory)


def run_test(
    user_input: str,
    thread_id: str = "multi_agent_test",
    config: Optional[RunnableConfig] = None,
    recursion_limit: int = 25,
) -> List[BaseMessage]:
    cfg = dict(config) if config else {}
    cfg["recursion_limit"] = recursion_limit
    configurable = cfg.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        cfg["configurable"] = configurable
    configurable["thread_id"] = thread_id
    initial: State = {
        "messages": [HumanMessage(content=user_input)],
        "next_agent": "__end__",
        "agent_history": [],
    }
    final = app.invoke(initial, config=cast(RunnableConfig, cfg))
    return final.get("messages", [])


class TeeLogger:
    """同时输出到控制台和文件的日志类"""
    def __init__(self, log_file_path: str):
        self.log_file = open(log_file_path, 'w', encoding='utf-8')
        self.log_file.write(f"日志开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_file.write("=" * 80 + "\n\n")
    
    def write(self, text: str):
        """写入日志（同时输出到控制台和文件）"""
        # 输出到控制台（直接使用 sys.stdout 避免递归）
        sys.stdout.write(text)
        sys.stdout.flush()
        # 写入文件
        self.log_file.write(text)
        self.log_file.flush()
    
    def writeln(self, text: str = ""):
        """写入一行日志"""
        self.write(text + "\n")
    
    def close(self):
        """关闭日志文件"""
        self.log_file.write("\n" + "=" * 80 + "\n")
        self.log_file.write(f"日志结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_file.close()


def extract_function_name(user_input: str) -> str:
    """从用户输入中提取函数名"""
    # 尝试匹配 "请提高XXX函数的代码覆盖率"
    match = re.search(r'请提高\s*(\w+)\s*函数的代码覆盖率', user_input)
    if match:
        return match.group(1)
    # 尝试匹配 "function:XXX@"
    match = re.search(r'function:(\w+)@', user_input)
    if match:
        return match.group(1)
    # 默认返回 "unknown"
    return "unknown"


def get_log_file_path(function_name: str, base_dir: str = None) -> str:
    """生成日志文件路径，如果重复则加序号"""
    if base_dir is None:
        # 获取脚本所在目录的父目录（test_agent目录）
        script_dir = Path(__file__).parent.parent
        log_dir = script_dir / "log"
    else:
        log_dir = Path(base_dir) / "log"
    
    # 创建log目录
    log_dir.mkdir(exist_ok=True)
    
    # 生成时间戳
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 生成基础文件名
    base_filename = f"{function_name}_{timestamp}.log"
    log_file_path = log_dir / base_filename
    
    # 如果文件已存在，添加序号
    counter = 1
    while log_file_path.exists():
        filename_with_counter = f"{function_name}_{timestamp}_{counter}.log"
        log_file_path = log_dir / filename_with_counter
        counter += 1
    
    return str(log_file_path)


if __name__ == "__main__":
    import sys

    # 提取函数名并创建日志文件
    test_prompt = (
        "请提高overlaps_time函数的代码覆盖率："
        "1) 用 Collect_Coverage 收集覆盖率；"
        "2) 用 Search_Nearest_Seed 查找相关 SQL 种子；"
        "3) 用 Code Explorer 获取其源代码；"
        "4) 用 Traverse_Call_Graph 向上遍历调用关系；"
        "5) 用 Coverage Analyzer 生成 SQL 测试用例；"
        "6) 用 SQL Tester 执行 SQL 测试用例；"
        "7) 用 Collect_Coverage 验证覆盖率是否提升。"
        "8) 如果覆盖率没有提升，重复步骤 2-7。"
        "9) 如果覆盖率提升，结束。"
    )
    
    function_name = extract_function_name(test_prompt)
    log_file_path = get_log_file_path(function_name)
    logger = TeeLogger(log_file_path)
    
    # 重定向print到logger
    original_print = print
    def log_print(*args, **kwargs):
        """重定向print到logger"""
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '\n')
        text = sep.join(str(arg) for arg in args) + end
        logger.write(text)
    
    # 临时替换print
    import builtins
    builtins.print = log_print
    
    print("=" * 60)
    print("Coverage Multi-Agent (Supervisor + SQL Tester / Code Explorer / Coverage Analyzer)")
    print("=" * 60)
    print(f"日志文件: {log_file_path}")
    print()

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        thread_id = "multi_agent_interactive"
        while True:
            try:
                line = input("\n[User] ").strip()
                if not line:
                    continue
                if line.lower() in ("q", "quit", "exit"):
                    print("Bye.")
                    break
                run_test(line, thread_id=thread_id)
            except KeyboardInterrupt:
                print("\nBye.")
                break
    else:
        print("\n[Test] overlaps_time\n")
        print("[User]", test_prompt)
        print()
        try:
            msgs = run_test(test_prompt, thread_id="overlaps_time_test")
        except KeyboardInterrupt:
            print("\n[Error] 程序被用户中断")
            sys.exit(1)
        except Exception as e:
            print(f"\n[Error] 程序执行出错: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        print("\n" + "=" * 50)
        print("对话记录 (Messages)")
        print("=" * 50)
        for i, m in enumerate(msgs):
            name = type(m).__name__
            content = (getattr(m, "content", None) or "")
            cap = 200
            if len(content) > cap:
                content = content[:cap].rstrip() + "..."
            prefix = "[User]      " if name == "HumanMessage" else "[Assistant] "
            if name == "ToolMessage":
                tname = (getattr(m, "name", None) or "?")[:24]
                prefix = f"[Tool: {tname}] "
            print(f"  {prefix} {content}")
        print("\nDone.")
        
        # 恢复原始print并关闭日志
        builtins.print = original_print
        logger.close()
        print(f"\n日志已保存到: {log_file_path}")