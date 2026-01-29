#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Get_Code_Context Node - 获取源代码上下文
"""

import re
import json5
from langchain_core.tools import tool
from .utils import load_nodes, DEFAULT_NODES_FILE


@tool
def Get_Code_Context(query_name: str, query_type: str, nodes_file: str = DEFAULT_NODES_FILE) -> str:
    """从PostgreSQL节点文件中获取函数或宏的源代码上下文。
    
    功能：
    - 根据名称和类型（FUNCTION或MACRO）查找对应的源代码
    - 对于函数（FUNCTION）：优先返回带有覆盖率信息的gcov_content（如果存在），否则返回raw_source
    - 对于宏（MACRO）：返回raw_source
    - 包含函数/宏的定义、注释等信息
    
    参数：
        query_name: 要搜索的名称（如 "ExecFindPartition" 或 "MAX_BUFFER_SIZE"）
        query_type: 搜索类型，"FUNCTION"（函数）或 "MACRO"（宏）
    """
    try:
        if not query_name:
            return json5.dumps({
                'source_code': '',
                'file_path': '',
                'line_number': 0,
                'name': '',
                'type': '',
                'status': 'Error',
                'error_message': 'query_name参数为空'
            }, ensure_ascii=False)
        
        if not query_type:
            return json5.dumps({
                'source_code': '',
                'file_path': '',
                'line_number': 0,
                'name': '',
                'type': '',
                'status': 'Error',
                'error_message': 'query_type参数为空，必须是"FUNCTION"或"MACRO"'
            }, ensure_ascii=False)
        
        query_type_upper = query_type.upper()
        if query_type_upper not in ['FUNCTION', 'MACRO']:
            return json5.dumps({
                'source_code': '',
                'file_path': '',
                'line_number': 0,
                'name': '',
                'type': '',
                'status': 'Error',
                'error_message': f'query_type必须是"FUNCTION"或"MACRO"，当前值: {query_type}'
            }, ensure_ascii=False)
        
        # 查找节点
        nodes = load_nodes(nodes_file)
        node_type = 'function' if query_type_upper == 'FUNCTION' else 'macro'
        
        node_data = None
        for node_id, data in nodes.items():
            if data.get('type') == node_type and data.get('name') == query_name:
                node_data = data
                break
        
        if not node_data:
            # 尝试大小写不敏感匹配
            query_name_lower = query_name.lower()
            for node_id, data in nodes.items():
                if data.get('type') == node_type:
                    node_name = data.get('name', '')
                    if node_name.lower() == query_name_lower:
                        node_data = data
                        break
        
        if not node_data:
            return json5.dumps({
                'source_code': '',
                'file_path': '',
                'line_number': 0,
                'name': query_name,
                'type': query_type_upper,
                'status': 'Error',
                'error_message': f'未找到{query_type_upper}类型的节点: {query_name}'
            }, ensure_ascii=False)
        
        # 提取源代码和相关信息
        file_path = node_data.get('file_path', '')
        line_number = node_data.get('line_number', 0)
        name = node_data.get('name', query_name)
        node_type_actual = node_data.get('type', query_type_upper.lower())
        signature = node_data.get('signature', '')
        
        # 对于函数类型，优先返回gcov_content
        if query_type_upper == 'FUNCTION' and node_type_actual == 'function':
            gcov_content = node_data.get('gcov_content', '')
            if gcov_content and gcov_content.strip():
                source_code = gcov_content
                if line_number == 0:
                    for line in gcov_content.split('\n'):
                        match = re.match(r'\s*\d+[*]?:\s*(\d+):.*\b' + re.escape(name) + r'\s*\(', line)
                        if match:
                            line_number = int(match.group(1))
                            break
            else:
                source_code = node_data.get('raw_source', '')
        else:
            source_code = node_data.get('raw_source', '')
        
        result = {
            'source_code': source_code,
            'file_path': file_path,
            'line_number': line_number,
            'name': name,
            'type': node_type_actual,
            'signature': signature,
            'status': 'Success',
            'error_message': ''
        }
        
        return json5.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json5.dumps({
            'source_code': '',
            'file_path': '',
            'line_number': 0,
            'name': '',
            'type': '',
            'status': 'Error',
            'error_message': f'获取代码上下文时发生异常: {str(e)}'
        }, ensure_ascii=False)
