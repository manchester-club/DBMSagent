#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Traverse_Call_Graph Node - 遍历调用图
"""

import re
import json5
from typing import Dict, List
from langchain_core.tools import tool
from .utils import (
    load_nodes, load_edges, normalize_func_id, get_call_graphs,
    DEFAULT_RELATIONS_FILE, DEFAULT_NODES_FILE
)


def get_node_display_text(node_id: str, nodes: Dict) -> str:
    """获取节点的显示文本"""
    if node_id in nodes:
        node_data = nodes[node_id]
        name = node_data.get('name', node_id)
        file_path = node_data.get('file_path', '')
        if file_path:
            return f"{file_path}:{name}"
        else:
            return name
    match = re.search(r'(function|macro):([^@]+)@([^:]+)', node_id)
    if match:
        return f"{match.group(3)}:{match.group(2)}"
    return node_id


def format_tree_node(node_id: str, relation_type: str, prefix: str, is_last: bool, depth: int, nodes: Dict) -> List[str]:
    """格式化树节点"""
    lines = []
    display_text = get_node_display_text(node_id, nodes)
    
    if depth == 0:
        lines.append(f"{display_text}")
    else:
        connector = "└─" if is_last else "├─"
        relation_label = {
            'calls': 'calls',
            'called_by': 'called by',
            'uses_macro': 'uses macro',
            'includes': 'includes'
        }.get(relation_type, relation_type)
        lines.append(f"{prefix}{connector} {relation_label} — {display_text}")
    
    return lines


def traverse_upstream(start_func_id: str, max_depth: int, nodes: Dict, 
                      reverse_call_graph: Dict, uses_macro_graph: Dict, includes_graph: Dict) -> Dict:
    """向上遍历（查找调用者）"""
    if max_depth <= 0:
        return {
            'tree': '',
            'total_functions': 0,
            'max_depth_reached': 0
        }
    
    visited = set()
    tree_lines = []
    queue = [(start_func_id, 0, '', True, '')]
    total_nodes = 0
    
    while queue:
        current_node, depth, prefix, is_last, relation_type = queue.pop(0)
        
        if current_node in visited or depth > max_depth:
            continue
        
        visited.add(current_node)
        total_nodes += 1
        
        if depth == 0:
            tree_lines.extend(format_tree_node(current_node, '', '', True, depth, nodes))
        else:
            tree_lines.extend(format_tree_node(current_node, relation_type, prefix, is_last, depth, nodes))
        
        children = []
        
        # 1. 查找调用者
        if reverse_call_graph and current_node in reverse_call_graph:
            for caller in reverse_call_graph[current_node]:
                if caller not in visited and depth < max_depth:
                    children.append((caller, 'called_by'))
        
        # 2. 查找使用的宏（只在当前函数层显示）
        if depth == 0 and uses_macro_graph and current_node in uses_macro_graph:
            for macro in uses_macro_graph[current_node]:
                if macro not in visited:
                    children.append((macro, 'uses_macro'))
        
        # 3. 查找包含关系（只在当前函数层显示）
        if depth == 0 and includes_graph and current_node in includes_graph:
            for include in includes_graph[current_node]:
                if include not in visited:
                    children.append((include, 'includes'))
        
        if children:
            if depth == 0:
                new_prefix = ""
            else:
                new_prefix = prefix + ("   " if is_last else "│  ")
            
            for i, (child_node, child_relation) in enumerate(children):
                is_last_child = (i == len(children) - 1)
                queue.append((child_node, depth + 1, new_prefix, is_last_child, child_relation))
    
    return {
        'tree': '\n'.join(tree_lines),
        'total_functions': total_nodes,
        'max_depth_reached': max_depth
    }


def traverse_downstream(start_func_id: str, max_depth: int, nodes: Dict,
                        call_graph: Dict, uses_macro_graph: Dict, includes_graph: Dict) -> Dict:
    """向下遍历（查找被调用者）"""
    if max_depth <= 0:
        return {
            'tree': '',
            'total_functions': 0,
            'max_depth_reached': 0
        }
    
    visited = set()
    tree_lines = []
    queue = [(start_func_id, 0, '', True, '')]
    total_nodes = 0
    
    while queue:
        current_node, depth, prefix, is_last, relation_type = queue.pop(0)
        
        if current_node in visited or depth > max_depth:
            continue
        
        visited.add(current_node)
        total_nodes += 1
        
        if depth == 0:
            tree_lines.extend(format_tree_node(current_node, '', '', True, depth, nodes))
        else:
            tree_lines.extend(format_tree_node(current_node, relation_type, prefix, is_last, depth, nodes))
        
        children = []
        
        # 1. 查找被调用者
        if call_graph and current_node in call_graph:
            for callee in call_graph[current_node]:
                if callee not in visited and depth < max_depth:
                    children.append((callee, 'calls'))
        
        # 2. 查找使用的宏（只在当前函数层显示）
        if depth == 0 and uses_macro_graph and current_node in uses_macro_graph:
            for macro in uses_macro_graph[current_node]:
                if macro not in visited:
                    children.append((macro, 'uses_macro'))
        
        # 3. 查找包含关系（只在当前函数层显示）
        if depth == 0 and includes_graph and current_node in includes_graph:
            for include in includes_graph[current_node]:
                if include not in visited:
                    children.append((include, 'includes'))
        
        if children:
            if depth == 0:
                new_prefix = ""
            else:
                new_prefix = prefix + ("   " if is_last else "│  ")
            
            for i, (child_node, child_relation) in enumerate(children):
                is_last_child = (i == len(children) - 1)
                queue.append((child_node, depth + 1, new_prefix, is_last_child, child_relation))
    
    return {
        'tree': '\n'.join(tree_lines),
        'total_functions': total_nodes,
        'max_depth_reached': max_depth
    }


@tool
def Traverse_Call_Graph(
    start_func_id: str,
    direction: str,
    max_depth: int = 3,
    relations_file: str = DEFAULT_RELATIONS_FILE,
    nodes_file: str = DEFAULT_NODES_FILE
) -> str:
    """在知识图谱的函数调用层级中向上（调用者）或向下（被调用者）遍历。
    
    功能：
    - 向上遍历（Upstream）：查找调用当前函数的所有函数（Caller），显示"called by"关系
    - 向下遍历（Downstream）：查找当前函数调用的所有函数（Callee），显示"calls"关系
    - 显示函数使用的宏（uses macro）和包含关系（includes）
    - 返回树形结构的调用关系图
    
    参数：
        start_func_id: 起始函数ID，格式如 "function:func_name@file_path:line"
        direction: 遍历方向，"Upstream"（向上，找调用者）或 "Downstream"（向下，找被调用者）
        max_depth: 遍历深度，默认为3，最大建议不超过5
    """
    try:
        if not start_func_id:
            return json5.dumps({
                'tree': '',
                'total_functions': 0,
                'max_depth_reached': 0,
                'status': 'Error',
                'error_message': 'start_func_id参数为空'
            }, ensure_ascii=False)
        
        if not direction:
            return json5.dumps({
                'tree': '',
                'total_functions': 0,
                'max_depth_reached': 0,
                'status': 'Error',
                'error_message': 'direction参数为空，必须是"Upstream"或"Downstream"'
            }, ensure_ascii=False)
        
        direction = direction.strip()
        if direction not in ['Upstream', 'Downstream']:
            return json5.dumps({
                'tree': '',
                'total_functions': 0,
                'max_depth_reached': 0,
                'status': 'Error',
                'error_message': f'direction必须是"Upstream"或"Downstream"，当前值: {direction}'
            }, ensure_ascii=False)
        
        try:
            max_depth = int(max_depth)
            if max_depth < 1:
                max_depth = 1
            elif max_depth > 10:
                max_depth = 10
        except (ValueError, TypeError):
            max_depth = 3
        
        # 构建调用图
        nodes = load_nodes(nodes_file)
        call_graph, reverse_call_graph, uses_macro_graph, includes_graph = get_call_graphs()
        
        # 验证起始函数是否存在
        normalized_func_id = normalize_func_id(start_func_id, nodes)
        if not normalized_func_id:
            return json5.dumps({
                'tree': '',
                'total_functions': 0,
                'max_depth_reached': 0,
                'status': 'Error',
                'error_message': f'起始函数不存在: {start_func_id}'
            }, ensure_ascii=False)
        
        start_func_id = normalized_func_id
        
        # 验证是否为函数节点
        node_data = nodes.get(start_func_id, {})
        if node_data.get('type') != 'function':
            return json5.dumps({
                'tree': '',
                'total_functions': 0,
                'max_depth_reached': 0,
                'status': 'Error',
                'error_message': f'起始节点不是函数类型: {start_func_id}'
            }, ensure_ascii=False)
        
        # 根据方向遍历（get_call_graphs 返回的图可能为 None，用 or {} 保证类型安全）
        rcg = reverse_call_graph or {}
        ug = uses_macro_graph or {}
        ig = includes_graph or {}
        cg = call_graph or {}
        if direction == 'Upstream':
            result = traverse_upstream(start_func_id, max_depth, nodes, rcg, ug, ig)
        else:
            result = traverse_downstream(start_func_id, max_depth, nodes, cg, ug, ig)
        
        result['status'] = 'Success'
        result['error_message'] = ''
        result['start_func_id'] = start_func_id
        result['direction'] = direction
        result['max_depth'] = max_depth
        
        return json5.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json5.dumps({
            'tree': '',
            'total_functions': 0,
            'max_depth_reached': 0,
            'status': 'Error',
            'error_message': f'遍历调用图时发生异常: {str(e)}'
        }, ensure_ascii=False)
