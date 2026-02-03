import os
import json
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END, START
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from .state import State
from .agents import manager_agent, test_generator_agent, execution_agent, coverage_agent
from .nodes.extract_context import Extract_Context
from .nodes.generate_skeleton import Generate_Test_Suite_Skeleton
from .nodes.run_test import Run_Test_Suite
from .nodes.collect_coverage import Collect_Coverage
from .nodes.normalize_c import Normalize_C_Output

# ---------------------------------------------------------------------------
# Tool Wrapper Functions (用于在图中直接操作 State)
# ---------------------------------------------------------------------------

def extract_context_node(state: State):
    print("\n[Node] Extracting Context...")
    result_str = Extract_Context.invoke({
        "c_file_path": state["c_file_path"],
        "func_name": state["func_name"],
        "pg_src_path": state["pg_src_path"]
    })
    context = json.loads(result_str)
    return {"context_json": context}

def normalize_code_node(state: State):
    print("\n[Node] Normalizing C Code...")
    # 获取最后一条 AIMessage (来自 Test Generator)
    last_msg = state["messages"][-1]
    raw_code = last_msg.content
    
    # 优先使用 case_template 进行头文件重排序
    context_info = state.get("case_template") or json.dumps(state["context_json"])
    
    normalized_code = Normalize_C_Output.invoke({
        "llm_raw_output": raw_code,
        "context_json_str": context_info
    })
    return {"normalized_c_code": normalized_code}

def execution_node(state: State):
    print("\n[Node] Generating Skeleton and Running Test...")
    # 1. Generate Skeleton
    skeleton_result_str = Generate_Test_Suite_Skeleton.invoke({
        "normalized_c_code": state["normalized_c_code"],
        "func_name": state["func_name"],
        "suite_dir": state["suite_dir"],
        "pg_config_path": state["pg_config_path"]
    })
    
    # 2. Run Test
    run_result_str = Run_Test_Suite.invoke({
        "suite_dir": state["suite_dir"],
        "pg_config_path": state["pg_config_path"]
    })
    
    run_result = json.loads(run_result_str)
    
    # 构造一条消息，告知 Manager 运行结果
    status = run_result.get("status", "Unknown")
    compile_ok = run_result.get("compile_ok", False)
    msg_content = f"EXECUTION_AGENT 完成。状态: {status}, 编译成功: {compile_ok}。"
    if not compile_ok:
        msg_content += f"\n错误信息: {run_result.get('test_errors', '')[:500]}"

    return {
        "run_result": run_result,
        "messages": [AIMessage(content=msg_content)]
    }

def coverage_node(state: State):
    print("\n[Node] Collecting Coverage...")
    report_str = Collect_Coverage.invoke({
        "suite_dir": state["suite_dir"],
        "func_name": state["func_name"]
    })
    report = json.loads(report_str)
    
    line_pct = report.get("line_coverage_pct", 0)
    msg_content = f"COVERAGE_AGENT 完成。行覆盖率: {line_pct}%。"
    
    return {
        "coverage_report": report, 
        "iteration_count": state["iteration_count"] + 1,
        "messages": [AIMessage(content=msg_content)]
    }

# ---------------------------------------------------------------------------
# Build the Graph
# ---------------------------------------------------------------------------

builder = StateGraph(State)

# 添加 Agent 节点
builder.add_node("manager", manager_agent)
builder.add_node("test_generator", test_generator_agent)
builder.add_node("execution_agent", execution_node) # 直接封装了逻辑
builder.add_node("coverage_agent", coverage_node)   # 直接封装了逻辑

# 添加辅助节点
builder.add_node("extract_context", extract_context_node)
builder.add_node("normalize_code", normalize_code_node)

# 定义边
builder.add_edge(START, "manager")

# Manager 的条件路由
def manager_router(state: State):
    return state["next_agent"]

builder.add_conditional_edges(
    "manager",
    manager_router,
    {
        "EXTRACT_CONTEXT_TOOL": "extract_context",
        "test_generator": "test_generator",
        "execution_agent": "execution_agent",
        "coverage_agent": "coverage_agent",
        "__end__": END
    }
)

# 各 Agent 完成后的回路
builder.add_edge("extract_context", "manager")
builder.add_edge("test_generator", "normalize_code")
builder.add_edge("normalize_code", "manager")
builder.add_edge("execution_agent", "manager")
builder.add_edge("coverage_agent", "manager")

# 编译
app = builder.compile()

# ---------------------------------------------------------------------------
# Execution Helper
# ---------------------------------------------------------------------------

def run_strut_multi_agent(c_file_path: str, func_name: str, pg_src_path: str, pg_config_path: str, suite_dir: str = None):
    # 如果没提供 suite_dir，模仿 main.py 的逻辑生成一个
    if not suite_dir:
        dir_path = os.path.dirname(os.path.abspath(c_file_path))
        file_base_name = os.path.splitext(os.path.basename(c_file_path))[0]
        outer_dir = os.path.join(dir_path, f"my_{file_base_name}")
        suite_dir = os.path.join(outer_dir, f"test_{func_name}_suite")
        print(f"自动生成 suite_dir: {suite_dir}")

    initial_state = {
        "messages": [HumanMessage(content=f"请为函数 {func_name} 在文件 {c_file_path} 中生成单元测试。")],
        "c_file_path": c_file_path,
        "func_name": func_name,
        "pg_src_path": pg_src_path,
        "pg_config_path": pg_config_path,
        "suite_dir": suite_dir,
        "iteration_count": 0,
        "max_iterations": 3,
        "context_json": None,
        "case_template": None,
        "normalized_c_code": None,
        "run_result": None,
        "coverage_report": None,
        "next_agent": "manager"
    }
    
    for output in app.stream(initial_state):
        # 打印流程中的关键信息
        for key, value in output.items():
            print(f"\n--- [Finished Node: {key}] ---")
            if "next_agent" in value:
                print(f"Next assigned agent: {value['next_agent']}")
    
    print("\n✅ STRUT LangGraph Workflow Completed.")

if __name__ == "__main__":
    # 可以通过命令行参数或直接在此修改进行测试
    import argparse
    
    parser = argparse.ArgumentParser(description="Run STRUT LangGraph Workflow")
    parser.add_argument("c_file", help="Path to the C source file")
    parser.add_argument("-f", "--func", required=True, help="Function name to test")
    parser.add_argument("--pg_src", default="/usr/src/postgresql", help="PostgreSQL source path")
    parser.add_argument("--pg_config", default="/usr/local/pgsql/bin/pg_config", help="pg_config path")
    parser.add_argument("--suite_dir", help="Output suite directory (optional)")
    
    args = parser.parse_args()
    
    run_strut_multi_agent(
        c_file_path=args.c_file,
        func_name=args.func,
        pg_src_path=args.pg_src,
        pg_config_path=args.pg_config,
        suite_dir=args.suite_dir
    )
