#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享工具函数
"""

import os
import json
import re
from typing import Dict, Optional, List

# 默认配置路径
DEFAULT_RELATIONS_FILE = "/public/home/rongyankai/graph/source/postgresql_relations.json"
DEFAULT_NODES_FILE = "/public/home/rongyankai/graph/source/postgresql_nodes.json"
DEFAULT_POSTGRESQL_SRC_DIR = "/public/home/rongyankai/postgresql-17.6"
DEFAULT_PIN_LOG_DIR = "/public/home/rongyankai/pin_log"

# 全局缓存
_nodes_cache: Optional[Dict] = None
_edges_cache: Optional[List[Dict]] = None
_call_graph: Optional[Dict] = None
_reverse_call_graph: Optional[Dict] = None
_function_paths: Optional[Dict] = None
_path_sqls: Optional[Dict] = None
_uses_macro_graph: Optional[Dict] = None
_includes_graph: Optional[Dict] = None


def load_nodes(nodes_file: str = DEFAULT_NODES_FILE) -> Dict:
    """加载节点数据（带缓存）"""
    global _nodes_cache
    if _nodes_cache is None:
        try:
            with open(nodes_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _nodes_cache = data.get('nodes', {})
        except Exception as e:
            print(f"加载节点文件失败: {e}")
            _nodes_cache = {}
    return _nodes_cache if _nodes_cache is not None else {}


def load_edges(relations_file: str = DEFAULT_RELATIONS_FILE) -> List[Dict]:
    """加载边数据（带缓存）"""
    global _edges_cache
    if _edges_cache is None:
        try:
            with open(relations_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _edges_cache = data.get('edges', [])
        except Exception as e:
            print(f"加载关系文件失败: {e}")
            _edges_cache = []
    return _edges_cache if _edges_cache is not None else []


def normalize_func_id(func_id: str, nodes: Dict) -> Optional[str]:
    """规范化函数ID，处理行号不匹配的情况"""
    if func_id in nodes:
        return func_id
    match = re.match(r'function:([^@]+)@([^:]+):(\d+)', func_id)
    if not match:
        return None
    func_name = match.group(1)
    file_path = match.group(2)
    for node_id, node_data in nodes.items():
        if (node_data.get('type') == 'function' and 
            node_data.get('name') == func_name and
            node_data.get('file_path') == file_path):
            return node_id
    return None


def get_call_graphs():
    """获取或构建调用图（延迟初始化）"""
    global _call_graph, _reverse_call_graph, _uses_macro_graph, _includes_graph
    
    if _call_graph is None:
        edges = load_edges()
        _call_graph = {}
        _reverse_call_graph = {}
        _uses_macro_graph = {}
        _includes_graph = {}
        
        for edge in edges:
            edge_type = edge.get('type')
            source = edge['source']
            target = edge['target']
            
            if edge_type == 'calls':
                if source not in _call_graph:
                    _call_graph[source] = []
                if target not in _call_graph[source]:
                    _call_graph[source].append(target)
                
                if target not in _reverse_call_graph:
                    _reverse_call_graph[target] = []
                if source not in _reverse_call_graph[target]:
                    _reverse_call_graph[target].append(source)
            elif edge_type == 'uses_macro':
                if source not in _uses_macro_graph:
                    _uses_macro_graph[source] = []
                if target not in _uses_macro_graph[source]:
                    _uses_macro_graph[source].append(target)
            elif edge_type == 'includes':
                if source not in _includes_graph:
                    _includes_graph[source] = []
                if target not in _includes_graph[source]:
                    _includes_graph[source].append(target)
    
    return _call_graph, _reverse_call_graph, _uses_macro_graph, _includes_graph


def get_seed_indices():
    """获取或构建种子索引（延迟初始化）"""
    global _reverse_call_graph, _function_paths, _path_sqls
    
    # 检查是否需要初始化（任何一个为 None 都需要初始化）
    if _reverse_call_graph is None or _function_paths is None or _path_sqls is None:
        print("[get_seed_indices] 开始初始化索引...", flush=True)
        edges = load_edges()
        print(f"[get_seed_indices] 加载了 {len(edges)} 条边", flush=True)
        _reverse_call_graph = {}
        _function_paths = {}
        _path_sqls = {}
        
        function_in_path_count = 0
        sql_executes_path_count = 0
        calls_count = 0
        
        for edge in edges:
            if edge.get('type') == 'calls':
                caller = edge['source']
                callee = edge['target']
                if callee not in _reverse_call_graph:
                    _reverse_call_graph[callee] = []
                _reverse_call_graph[callee].append(caller)
                calls_count += 1
            elif edge.get('type') == 'function_in_path':
                func_id = edge['source']
                path_id = edge['target']
                if func_id not in _function_paths:
                    _function_paths[func_id] = []
                _function_paths[func_id].append({
                    'path_id': path_id,
                    'position': edge.get('position', 999)
                })
                function_in_path_count += 1
            elif edge.get('type') == 'sql_executes_path':
                sql_id = edge['source']
                path_id = edge['target']
                if path_id not in _path_sqls:
                    _path_sqls[path_id] = []
                _path_sqls[path_id].append(sql_id)
                sql_executes_path_count += 1
        
        print(f"[get_seed_indices] 初始化完成:", flush=True)
        print(f"  - calls: {calls_count}, reverse_call_graph 大小: {len(_reverse_call_graph)}", flush=True)
        print(f"  - function_in_path: {function_in_path_count}, function_paths 大小: {len(_function_paths)}", flush=True)
        print(f"  - sql_executes_path: {sql_executes_path_count}, path_sqls 大小: {len(_path_sqls)}", flush=True)
    else:
        print(f"[get_seed_indices] 使用缓存，function_paths 大小: {len(_function_paths) if _function_paths else 0}", flush=True)
    
    # 确保返回值不是 None（防御性编程）
    if _reverse_call_graph is None:
        _reverse_call_graph = {}
    if _function_paths is None:
        _function_paths = {}
    if _path_sqls is None:
        _path_sqls = {}
    
    return _reverse_call_graph, _function_paths, _path_sqls
