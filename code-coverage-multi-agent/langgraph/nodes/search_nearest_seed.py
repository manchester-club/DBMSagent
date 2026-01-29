#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search_Nearest_Seed Node - 查找SQL种子
"""

import re
import json5
from collections import deque
from typing import Dict
from langchain_core.tools import tool
from .utils import (
    load_nodes, load_edges, normalize_func_id, get_seed_indices,
    DEFAULT_RELATIONS_FILE, DEFAULT_NODES_FILE
)


def find_seeds_for_function(func_id: str, distance: int, function_paths: Dict, path_sqls: Dict) -> Dict:
    """为指定函数查找所有种子SQL"""
    # 加载多个 nodes 文件（postgresql_nodes.json 和 pin_log_nodes.json）
    nodes = load_nodes()
    # 尝试加载 pin_log_nodes.json 中的 SQL 节点
    pin_log_nodes_file = "/public/home/rongyankai/graph/source/pin_log_nodes.json"
    try:
        import json
        with open(pin_log_nodes_file, 'r', encoding='utf-8') as f:
            pin_log_data = json.load(f)
            pin_log_nodes = pin_log_data.get('nodes', {})
            # 合并 SQL 节点（只合并 sql: 开头的节点）
            for sql_id, sql_node in pin_log_nodes.items():
                if sql_id.startswith('sql:') and sql_id not in nodes:
                    nodes[sql_id] = sql_node
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # pin_log_nodes.json 不存在或格式错误，忽略
    
    seeds = []
    missing_sql_nodes = []
    
    if function_paths is not None and func_id in function_paths:
        path_sqls_dict = path_sqls if path_sqls is not None else {}
        for path_info in function_paths[func_id]:
            path_id = path_info['path_id']
            if path_id in path_sqls_dict:
                for sql_id in path_sqls_dict[path_id]:
                    sql_node = nodes.get(sql_id, {})
                    path_node = nodes.get(path_id, {})
                    sql_content = sql_node.get('sql', '') or sql_node.get('raw_source', '')
                    if not sql_content and sql_id not in nodes:
                        missing_sql_nodes.append(sql_id)
                    seeds.append({
                        'sql_id': sql_id,
                        'sql': sql_content,
                        'call_chain': path_node.get('path', []),
                        'distance': distance,
                        'nearest_function': func_id,
                        'position': path_info.get('position', 999),
                        'sql_node_exists': sql_id in nodes
                    })
    
    # 过滤掉 SQL 为空的种子
    valid_seeds = [s for s in seeds if s['sql']]
    
    if valid_seeds:
        valid_seeds.sort(key=lambda x: x.get('position', 999))
        best_seed = valid_seeds[0]
        return {
            'status': 'Success',
            'error_message': '',
            'seed_sql': best_seed['sql'],
            'call_chain': best_seed['call_chain'],
            'distance': best_seed['distance'],
            'nearest_function': best_seed['nearest_function']
        }
    else:
        # 构建详细的错误信息
        error_parts = []
        if func_id in function_paths:
            path_count = len(function_paths[func_id])
            error_parts.append(f'函数有 {path_count} 个关联路径')
            sql_count = sum(len(path_sqls.get(p['path_id'], [])) for p in function_paths[func_id])
            error_parts.append(f'这些路径共关联 {sql_count} 个 SQL ID')
            if missing_sql_nodes:
                error_parts.append(f'其中 {len(missing_sql_nodes)} 个 SQL 节点不在 nodes 中（示例: {missing_sql_nodes[0]}）')
            if seeds:
                empty_count = len([s for s in seeds if not s['sql']])
                error_parts.append(f'{empty_count} 个 SQL 节点存在但 sql/raw_source 字段为空')
        else:
            error_parts.append('函数不在 function_paths 中（没有 function_in_path 关系）')
        
        error_msg = '未找到有效的种子 SQL。' + '；'.join(error_parts) + '。'
        return {
            'status': 'Error',
            'error_message': error_msg,
            'seed_sql': '',
            'call_chain': [],
            'distance': distance,
            'nearest_function': func_id
        }


def bfs_find_nearest_seed(target_func_id: str, max_depth: int, reverse_call_graph: Dict, function_paths: Dict, path_sqls: Dict) -> Dict:
    """使用BFS查找最近的种子"""
    # 调试信息
    print(f"[bfs_find_nearest_seed] 目标函数: {target_func_id}", flush=True)
    print(f"[bfs_find_nearest_seed] function_paths 中有 {len(function_paths)} 个函数", flush=True)
    in_paths = target_func_id in function_paths if function_paths else False
    print(f"[bfs_find_nearest_seed] 目标函数在 function_paths 中: {in_paths}", flush=True)
    
    # 步骤1: 检查目标函数本身是否有有效的 SQL
    if function_paths and target_func_id in function_paths:
        print(f"[bfs_find_nearest_seed] 找到目标函数在 function_paths 中，路径数量: {len(function_paths[target_func_id])}", flush=True)
        result = find_seeds_for_function(target_func_id, distance=0, function_paths=function_paths, path_sqls=path_sqls)
        print(f"[bfs_find_nearest_seed] find_seeds_for_function 结果: status={result.get('status')}, seed_sql长度={len(result.get('seed_sql', ''))}", flush=True)
        # 如果找到了有效的 SQL，直接返回
        if result.get('status') == 'Success' and result.get('seed_sql'):
            return result
        # 如果没有有效的 SQL，继续向上查找调用者
        print(f"[bfs_find_nearest_seed] 目标函数没有有效的 SQL，继续向上查找调用者", flush=True)
    else:
        print(f"[bfs_find_nearest_seed] 目标函数不在 function_paths 中，尝试向上查找调用者", flush=True)
    
    # 步骤2: 检查是否有向上的调用关系
    if not reverse_call_graph or target_func_id not in reverse_call_graph:
        return {
            'status': 'Error',
            'error_message': '该函数未被触发且没有向上调用关系',
            'seed_sql': '',
            'call_chain': [],
            'distance': -1,
            'nearest_function': ''
        }
    
    # 步骤3: BFS查找调用者（从目标函数开始，distance=0）
    queue = deque([(target_func_id, 0)])
    visited = {target_func_id}
    
    while queue:
        current_func, distance = queue.popleft()
        
        if distance >= max_depth:
            continue
        
        # 检查当前函数是否有SQL触发（跳过目标函数本身，因为已经在步骤1检查过了）
        if current_func != target_func_id and function_paths is not None and current_func in function_paths:
            result = find_seeds_for_function(current_func, distance=distance, function_paths=function_paths, path_sqls=path_sqls)
            # 如果找到了有效的 SQL，返回
            if result.get('status') == 'Success' and result.get('seed_sql'):
                return result
        
        # 查找callers（向上遍历）
        if reverse_call_graph and current_func in reverse_call_graph:
            for caller in reverse_call_graph[current_func]:
                if caller not in visited:
                    visited.add(caller)
                    queue.append((caller, distance + 1))
    
    # 达到max_depth仍未找到
    visited_funcs = list(visited)
    funcs_with_paths = [f for f in visited_funcs if function_paths is not None and f in function_paths]
    
    # 检查是否找到了调用者但 SQL 节点不存在
    callers_found = []
    if target_func_id in reverse_call_graph:
        direct_callers = reverse_call_graph[target_func_id]
        callers_found = [c for c in direct_callers if c in function_paths]
    
    error_parts = [
        f'未找到距离在{max_depth}层内的有效种子 SQL。',
        f'已遍历 {len(visited_funcs)} 个函数，'
    ]
    
    if callers_found:
        caller_name = callers_found[0].split("@")[0].replace("function:", "")
        error_parts.append(
            f'找到 {len(callers_found)} 个直接调用者（如 {caller_name}）在 function_paths 中，'
        )
        # 检查这些调用者的 SQL 节点情况
        nodes = load_nodes()
        total_sql_ids = 0
        missing_sql_count = 0
        for caller in callers_found[:3]:
            if caller in function_paths:
                for path_info in function_paths[caller]:
                    path_id = path_info['path_id']
                    if path_id in path_sqls:
                        sql_ids = path_sqls[path_id]
                        total_sql_ids += len(sql_ids)
                        for sql_id in sql_ids:
                            if sql_id not in nodes:
                                missing_sql_count += 1
        if total_sql_ids > 0:
            error_parts.append(
                f'但这些调用者关联的 {total_sql_ids} 个 SQL 节点都不在 nodes 中（SQL 节点可能尚未创建）。'
                f'\n提示：SQL 节点需要通过 Collect_Coverage 或 Run_SQL_Test 工具动态创建。'
            )
    else:
        # 改进错误信息：区分"没有调用者"和"调用者不在 function_paths 中"
        if reverse_call_graph is not None and target_func_id in reverse_call_graph:
            direct_callers = reverse_call_graph[target_func_id]
            if direct_callers:
                # 有调用者，但都不在 function_paths 中
                caller_names = [c.split("@")[0].replace("function:", "") for c in direct_callers[:3]]
                error_parts.append(
                    f'其中 {len(funcs_with_paths)} 个在 function_paths 中但未找到有效 SQL。'
                    f'\n目标函数有 {len(direct_callers)} 个直接调用者（如: {", ".join(caller_names)}），'
                    f'但这些调用者都没有 function_in_path 关系（未被 SQL 触发过）。'
                    f'\n提示：这些函数可能从未被 SQL 测试用例触发，或者需要先执行相关的 SQL 测试用例。'
                )
            else:
                # 没有调用者
                error_parts.append(
                    f'其中 {len(funcs_with_paths)} 个在 function_paths 中但未找到有效 SQL。'
                    f'\n目标函数没有调用者（是顶层函数），且本身没有 function_in_path 关系。'
                )
        else:
            # 没有调用关系
            error_parts.append(
                f'其中 {len(funcs_with_paths)} 个在 function_paths 中但未找到有效 SQL。'
                f'\n目标函数没有调用关系（reverse_call_graph 中不存在），且本身没有 function_in_path 关系。'
            )
    
    error_msg = ' '.join(error_parts)
    return {
        'status': 'Error',
        'error_message': error_msg,
        'seed_sql': '',
        'call_chain': [],
        'distance': -1,
        'nearest_function': ''
    }


@tool
def Search_Nearest_Seed(
    target_func_id: str,
    relations_file: str = DEFAULT_RELATIONS_FILE,
    nodes_file: str = DEFAULT_NODES_FILE
) -> str:
    """查找距离目标函数最近的种子SQL。
    
    功能：
    - 如果目标函数本身有SQL触发（function_in_path关系），返回距离=0的种子
    - 如果目标函数没有SQL触发，通过calls关系向上查找最近的被触发的函数
    - 返回找到的种子SQL、调用链和距离信息
    
    参数：
        target_func_id: 目标函数ID，格式如 "function:func_name@file_path:line"
    """
    try:
        if not target_func_id:
            return json5.dumps({
                'status': 'Error',
                'error_message': 'target_func_id参数为空',
                'seed_sql': '',
                'call_chain': [],
                'distance': -1,
                'nearest_function': ''
            }, ensure_ascii=False)
        
        # 构建索引
        nodes = load_nodes(nodes_file)
        reverse_call_graph, function_paths, path_sqls = get_seed_indices()
        
        # 验证目标函数是否存在
        normalized_func_id = normalize_func_id(target_func_id, nodes)
        
        # 调试信息：检查规范化后的函数 ID 是否在 function_paths 中
        # 确保 function_paths 不是 None
        if normalized_func_id and function_paths is not None and normalized_func_id not in function_paths:
            # 尝试查找相似的键（可能是格式问题）
            similar_keys = [k for k in function_paths.keys() if normalized_func_id.split('@')[0] in k]
            if similar_keys:
                # 如果找到相似的键，使用第一个
                print(f"[Search_Nearest_Seed] 警告: 规范化后的函数 ID {normalized_func_id} 不在 function_paths 中", flush=True)
                print(f"[Search_Nearest_Seed] 找到相似的键: {similar_keys[0]}", flush=True)
                normalized_func_id = similar_keys[0]
        
        if not normalized_func_id:
            func_name_match = re.search(r'function:([^@]+)', target_func_id)
            if func_name_match:
                func_name = func_name_match.group(1)
                matching_funcs = []
                for node_id, node_data in nodes.items():
                    if (node_data.get('type') == 'function' and 
                        node_data.get('name') == func_name):
                        matching_funcs.append({
                            'func_id': node_id,
                            'file_path': node_data.get('file_path', '')
                        })
                
                if matching_funcs:
                    func_list = '\n'.join([f"  - {f['func_id']}\n    文件: {f['file_path']}" 
                                          for f in matching_funcs[:5]])
                    return json5.dumps({
                        'status': 'Error',
                        'error_message': f'目标函数ID不存在: {target_func_id}\n\n找到以下同名函数，请使用正确的函数ID:\n{func_list}',
                        'seed_sql': '',
                        'call_chain': [],
                        'distance': -1,
                        'nearest_function': ''
                    }, ensure_ascii=False)
            
            return json5.dumps({
                'status': 'Error',
                'error_message': f'目标函数不存在: {target_func_id}',
                'seed_sql': '',
                'call_chain': [],
                'distance': -1,
                'nearest_function': ''
            }, ensure_ascii=False)
        
        target_func_id = normalized_func_id
        
        # 验证是否为函数节点
        node_data = nodes.get(target_func_id, {})
        if node_data.get('type') != 'function':
            return json5.dumps({
                'status': 'Error',
                'error_message': f'目标节点不是函数类型: {target_func_id}',
                'seed_sql': '',
                'call_chain': [],
                'distance': -1,
                'nearest_function': ''
            }, ensure_ascii=False)
        
        # 执行BFS查找（get_seed_indices 返回值可能为 None，用 or {} 保证类型安全）
        rcg = reverse_call_graph or {}
        fp = function_paths or {}
        ps = path_sqls or {}
        
        # 调试信息：检查传入的参数
        print(f"[Search_Nearest_Seed] reverse_call_graph 长度: {len(rcg)}", flush=True)
        print(f"[Search_Nearest_Seed] function_paths 长度: {len(fp)}", flush=True)
        print(f"[Search_Nearest_Seed] path_sqls 长度: {len(ps)}", flush=True)
        print(f"[Search_Nearest_Seed] 规范化后的函数 ID: {normalized_func_id}", flush=True)
        if fp:
            encode_keys = [k for k in fp.keys() if "EncodeSpecialDate" in k and "date.c" in k]
            print(f"[Search_Nearest_Seed] function_paths 中包含 EncodeSpecialDate 的键数量: {len(encode_keys)}", flush=True)
            if encode_keys:
                print(f"[Search_Nearest_Seed] 示例键: {encode_keys[0]}", flush=True)
                print(f"[Search_Nearest_Seed] 该键在 function_paths 中: {encode_keys[0] in fp}", flush=True)
        
        result = bfs_find_nearest_seed(target_func_id, max_depth=5,
                                       reverse_call_graph=rcg,
                                       function_paths=fp,
                                       path_sqls=ps)
        return json5.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json5.dumps({
            'status': 'Error',
            'error_message': f'查找最近种子时发生异常: {str(e)}',
            'seed_sql': '',
            'call_chain': [],
            'distance': -1,
            'nearest_function': ''
        }, ensure_ascii=False)
