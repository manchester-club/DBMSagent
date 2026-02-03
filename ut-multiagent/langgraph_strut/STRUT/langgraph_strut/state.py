from typing import Annotated, List, TypedDict, Optional, Dict, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class State(TypedDict):
    # 对话历史
    messages: Annotated[List[BaseMessage], add_messages]
    
    # 任务元数据
    c_file_path: str
    func_name: str
    pg_src_path: str
    pg_config_path: str
    suite_dir: Optional[str]
    
    # 中间结果
    context_json: Optional[Dict[str, Any]]
    case_template: Optional[str]
    normalized_c_code: Optional[str]
    run_result: Optional[Dict[str, Any]]
    coverage_report: Optional[Dict[str, Any]]
    
    # 迭代控制
    iteration_count: int
    max_iterations: int
    next_agent: str
