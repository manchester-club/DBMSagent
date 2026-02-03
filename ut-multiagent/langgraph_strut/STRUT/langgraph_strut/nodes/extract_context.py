import os
import sys
import json
from langchain_core.tools import tool

# 将项目根目录添加到 sys.path 以便导入原有模块
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from seed_case_generator import generate_seed_case

@tool
def Extract_Context(c_file_path: str, func_name: str, pg_src_path: str) -> str:
    """
    提取目标函数的上下文信息，包括函数签名、宏、结构体、typedef、includes 和种子用例。
    
    参数:
        c_file_path: C 源文件路径
        func_name: 目标函数名
        pg_src_path: PostgreSQL 源码根目录
    """
    try:
        # 调用原有的 generate_seed_case 函数
        case_content, compiler_args = generate_seed_case(c_file_path, pg_src_path, func_name)
        
        # 解析返回的 JSON 字符串以确保其有效性
        context_data = json.loads(case_content)
        
        # 补充编译参数到结果中，以便后续使用（可选）
        context_data["compiler_args"] = compiler_args
        
        return json.dumps(context_data, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "Error", "error_message": str(e)}, ensure_ascii=False)
