import os
import sys
import json
from langchain_core.tools import tool

# 将项目根目录添加到 sys.path 以便导入原有模块
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from pg_regress_generator import generate_pg_regress_suite

@tool
def Generate_Test_Suite_Skeleton(normalized_c_code: str, func_name: str, suite_dir: str, pg_config_path: str) -> str:
    """
    生成 pg_regress 测试套件的骨架，包括 Makefile、C 源码、SQL 脚本和预期输出。
    
    参数:
        normalized_c_code: 经过处理的 C 测试代码
        func_name: 目标函数名
        suite_dir: 测试套件保存目录
        pg_config_path: pg_config 工具路径
    """
    try:
        # 创建目录
        os.makedirs(suite_dir, exist_ok=True)
        
        # 调用原有的 generate_pg_regress_suite 函数
        # 注意：原函数内部会写文件，不返回清单，我们手动构造一个清单
        generate_pg_regress_suite(normalized_c_code, func_name, "", suite_dir, pg_config_path)
        
        manifest = {
            "suite_dir": suite_dir,
            "files": [
                f"test_{func_name}.c",
                "Makefile",
                f"test_{func_name}.control",
                f"test_{func_name}--1.0.sql",
                "sql/test_{func_name}.sql",
                "expected/test_{func_name}.out"
            ],
            "status": "Success"
        }
        
        return json.dumps(manifest, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "Error", "error_message": str(e)}, ensure_ascii=False)
