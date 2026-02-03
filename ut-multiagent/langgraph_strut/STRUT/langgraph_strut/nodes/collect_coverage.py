import os
import sys
import json
from langchain_core.tools import tool

# 将项目根目录添加到 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from coverage import infer_from_suite_dir, compute_row, format_branch_edge

@tool
def Collect_Coverage(suite_dir: str, func_name: str) -> str:
    """
    收集目标函数的代码覆盖率信息，包括行覆盖率、分支覆盖率和未覆盖详情。
    
    参数:
        suite_dir: 测试套件目录
        func_name: 目标函数名
    """
    try:
        # 使用 coverage.py 的推断逻辑
        inferred = infer_from_suite_dir(suite_dir)
        row, res = compute_row(inferred)
        
        # 构造结构化报告
        report = {
            "line_coverage_pct": row.line_pct,
            "branch_coverage_pct": row.branch_pct if row.branch_pct is not None else "N/A",
            "total_lines": res.total_lines,
            "covered_lines": res.covered_lines,
            "uncovered_lines": res.uncovered_lines,
            "total_branches": res.total_branches,
            "covered_branches": res.covered_branches,
            "uncovered_branches": [
                {
                    "line_no": b.line_no,
                    "branch_id": b.branch_id,
                    "description": format_branch_edge(b)
                }
                for b in res.uncovered_branches
            ],
            "status": "Success"
        }
        
        return json.dumps(report, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "Error", "error_message": str(e)}, ensure_ascii=False)
