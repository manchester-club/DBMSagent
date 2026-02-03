import os
import sys
import json
import subprocess
from langchain_core.tools import tool

# 将项目根目录添加到 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@tool
def Run_Test_Suite(suite_dir: str, pg_config_path: str) -> str:
    """
    编译并运行测试套件，收集执行结果。
    
    参数:
        suite_dir: 测试套件目录路径
        pg_config_path: pg_config 工具路径
    """
    try:
        run_script = os.path.join(project_root, "run_test_suite.sh")
        
        # 执行脚本
        # 脚本用法: bash run_test_suite.sh <suite_path>
        result = subprocess.run(
            ["bash", run_script, suite_dir],
            capture_output=True,
            text=True,
            env=os.environ.copy()
        )
        
        # 检查错误文件
        error_file = os.path.join(suite_dir, "test_errors.txt")
        error_content = ""
        if os.path.exists(error_file):
            with open(error_file, "r") as f:
                error_content = f.read()
        
        run_result = {
            "exit_code": result.returncode,
            "stdout": result.stdout[-1000:], # 截取部分输出以防过大
            "stderr": result.stderr[-1000:],
            "compile_ok": "Error" not in result.stdout and "Error" not in result.stderr, # 简单启发式判断
            "test_errors": error_content[-2000:], # 重点是错误日志内容
            "status": "Success" if result.returncode == 0 else "Fail"
        }
        
        return json.dumps(run_result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "Error", "error_message": str(e)}, ensure_ascii=False)
