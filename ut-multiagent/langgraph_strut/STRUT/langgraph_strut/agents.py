import os
import sys
import json
from typing import List, Literal, Optional, Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from .state import State

# 确保可以导入项目根目录的模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 完全使用原来代码的方法
from model import access_model
from generator import prompt_generator, opti_generator, case_generator
from main import save_current_round_files, clean_llm_response

# ---------------------------------------------------------------------------
# Prompts (保留作为路由参考)
# ---------------------------------------------------------------------------

MANAGER_PROMPT = """你是测试生成系统的 Manager Agent。你的职责是协调其他三个专家 Agent。

专家 Agent 列表：
1. TEST_GENERATOR: 生成和优化 C 测试代码。
2. EXECUTION_AGENT: 生成套件骨架、编译并运行测试。
3. COVERAGE_AGENT: 采集代码覆盖率反馈。

流程控制规则：
1. 如果没有 context_json，先调用 Extract_Context 工具。
2. 如果有 context_json 但没有 normalized_c_code，派发任务给 TEST_GENERATOR。
3. 如果有 normalized_c_code 但没有 run_result，派发任务给 EXECUTION_AGENT。
4. 如果测试运行成功，派发任务给 COVERAGE_AGENT。
5. 如果覆盖率未达到目标（如 < 100% 且还有未覆盖分支），根据运行结果和覆盖率报告，再次派发任务给 TEST_GENERATOR 进行优化。
6. 如果覆盖率达标或达到最大迭代次数，选择 FINISH。

请只回复关键词：TEST_GENERATOR / EXECUTION_AGENT / COVERAGE_AGENT / FINISH"""

# ---------------------------------------------------------------------------
# Agent Nodes
# ---------------------------------------------------------------------------

def manager_agent(state: State):
    """
    Manager Agent 使用 access_model 进行路由决策
    """
    # 强制迭代限制
    if state["iteration_count"] >= state["max_iterations"]:
        print(f"达到最大迭代次数 ({state['max_iterations']})，停止流程。")
        return {"next_agent": "__end__"}

    messages = state["messages"]
    
    # 逻辑判断 (为了简单高效，减少不必要的 LLM 调用)
    if not state.get("context_json"):
        return {"next_agent": "EXTRACT_CONTEXT_TOOL"}
    
    if state.get("normalized_c_code") and not state.get("run_result"):
        print("检测到代码已生成但未运行，自动派发给 EXECUTION_AGENT")
        return {"next_agent": "execution_agent"}
    
    if state.get("run_result") and not state.get("coverage_report"):
        print("检测到测试已运行但未采集覆盖率，自动派发给 COVERAGE_AGENT")
        return {"next_agent": "coverage_agent"}
    
    # 如果已经有覆盖率报告且达到了 100%，也可以考虑停止
    coverage_report = state.get("coverage_report")
    if coverage_report:
        line_pct = coverage_report.get("line_coverage_pct", 0)
        branch_pct = coverage_report.get("branch_coverage_pct", 0)
        if line_pct >= 100 and (branch_pct == "N/A" or branch_pct >= 100):
            print("覆盖率已达 100%，停止流程。")
            return {"next_agent": "__end__"}

    # 使用原项目的 access_model 进行路由决策
    # 构造路由判断的 prompt
    history_str = ""
    for msg in messages[-10:]: # 增加历史长度
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content
        if len(content) > 300:
            content = content[:300] + "..."
        history_str += f"{role}: {content}\n"
    
    # 显式添加当前状态摘要
    state_summary = f"""
当前系统状态:
- context_json: {"已提取" if state.get("context_json") else "未提取"}
- normalized_c_code: {"已生成" if state.get("normalized_c_code") else "未生成"}
- run_result: {"已获得" if state.get("run_result") else "未获得"}
- coverage_report: {"已获得" if state.get("coverage_report") else "未获得"}
- 当前迭代次数: {state.get("iteration_count", 0)} / {state.get("max_iterations", 3)}
"""

    routing_prompt = f"{MANAGER_PROMPT}\n{state_summary}\n当前对话历史:\n{history_str}\n\n请决定下一个 Agent:"
    
    try:
        # 调用原来代码的 access_model
        response_content = access_model(routing_prompt, model="deepseek-chat")
        content = response_content.upper()
        
        if "TEST_GENERATOR" in content:
            return {"next_agent": "test_generator"}
        elif "EXECUTION_AGENT" in content:
            return {"next_agent": "execution_agent"}
        elif "COVERAGE_AGENT" in content:
            return {"next_agent": "coverage_agent"}
        else:
            return {"next_agent": "__end__"}
    except Exception as e:
        print(f"Manager Agent 决策出错: {e}")
        return {"next_agent": "__end__"}

def test_generator_agent(state: State):
    """
    Test Generator Agent 完全使用原来项目的 prompt_generator 和 opti_generator
    """
    context_data = state["context_json"]
    # 将 context_data 转回 JSON 字符串供 case_generator 使用
    context_json_str = json.dumps(context_data)
    
    # 1. 使用原项目的 case_generator
    case_template, default_PTR, has_stub = case_generator(context_json_str)
    
    is_optimization_mode = state["iteration_count"] > 0
    
    if not is_optimization_mode:
        # 首轮生成：使用原项目的 prompt_generator
        prompt = prompt_generator("", case_template, has_stub)
    else:
        # 优化轮：使用原项目的 opti_generator + 基础 prompt
        base_prompt = prompt_generator("", case_template, has_stub)
        
        # 优先使用上一轮的 normalized_c_code，如果没有则使用原始响应
        prev_code = state.get("normalized_c_code")
        if not prev_code:
            # 尝试从历史消息中获取
            for msg in reversed(state["messages"]):
                if isinstance(msg, AIMessage):
                    prev_code = msg.content
                    break
        
        run_result = state.get("run_result", {})
        error_info = run_result.get("test_errors", "") if run_result else ""
        
        # 2. 使用原项目的 opti_generator
        opti_section = opti_generator(prev_code, error_info)
        
        # 3. 补充未覆盖分支信息 (参考 main.py 的逻辑)
        branch_info = ""
        coverage_report = state.get("coverage_report", {})
        if coverage_report:
            uncovered_branches = coverage_report.get("uncovered_branches", [])
            for i, b in enumerate(uncovered_branches, 1):
                branch_info += f"{i}. branch: {b.get('line_no')}: {b.get('description')} condition uncovered.\n"
            
            uncovered_lines = coverage_report.get("uncovered_lines", [])
            if uncovered_lines:
                branch_info += "\n**Detailed Uncovered Lines:**\n"
                branch_info += '\n'.join([f"- {line}" for line in uncovered_lines]) + "\n"
        
        if not branch_info:
            branch_info = "1. general_optimization: Improve test coverage.\n"
            
        prompt = base_prompt + opti_section + branch_info

    # 调用原项目的 access_model 获取 LLM 响应
    try:
        llm_response = access_model(prompt, model="deepseek-chat")
        
        # 模仿 main.py 的清理逻辑
        cleaned_response = clean_llm_response(llm_response)
        
        # 如果 suite_dir 已经确定，保存当前轮次文件 (模仿 main.py)
        if state.get("suite_dir"):
            os.makedirs(state["suite_dir"], exist_ok=True)
            save_current_round_files(
                state["suite_dir"], 
                prompt, 
                cleaned_response, 
                state["func_name"], 
                is_optimization_mode
            )
            
        return {
            "messages": [AIMessage(content=llm_response)],
            "case_template": case_template,
            "run_result": None,        # 重置运行结果，触发下一轮执行
            "coverage_report": None    # 重置覆盖率报告
        }
    except Exception as e:
        print(f"Test Generator Agent 出错: {e}")
        return {"messages": [AIMessage(content=f"LLM 调用失败: {str(e)}")]}

def execution_agent(state: State):
    # 此 Agent 逻辑在 workflow.py 的 execution_node 中实现，直接返回占位
    return {"messages": [AIMessage(content="Assigning to EXECUTION_AGENT tool...")]}

def coverage_agent(state: State):
    # 此 Agent 逻辑在 workflow.py 的 coverage_node 中实现，直接返回占位
    return {"messages": [AIMessage(content="Assigning to COVERAGE_AGENT tool...")]}
