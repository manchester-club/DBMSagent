import os
import sys
import json
from langchain_core.tools import tool

# 将项目根目录添加到 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入 main.py 中的清理逻辑 (如果 main.py 能被导入的话，否则需要复制过来)
from main import clean_llm_response, reorder_all_includes_in_file

@tool
def Normalize_C_Output(llm_raw_output: str, context_json_str: str) -> str:
    """
    清理 LLM 生成的 C 代码，去掉 Markdown 标记并重新整理头文件顺序。
    
    参数:
        llm_raw_output: LLM 返回的原始文本内容
        context_json_str: 提取的上下文 JSON 字符串 (包含种子用例信息)
    """
    try:
        # 1. 清理 Markdown 标记
        cleaned_code = clean_llm_response(llm_raw_output)
        
        # 2. 重新排序头文件并合并种子用例头文件
        # context_json_str 实际上是 Extract_Context 的输出
        normalized_code = reorder_all_includes_in_file(cleaned_code, context_json_str)
        
        return normalized_code
    except Exception as e:
        return f"// Error in Normalize_C_Output: {str(e)}\n{llm_raw_output}"
