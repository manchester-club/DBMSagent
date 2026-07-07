#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collect_Coverage Node - 收集函数覆盖率
"""

import os
import re
import subprocess
import hashlib
import json
import json5
from datetime import datetime
from typing import Dict, Optional
from langchain_core.tools import tool
from .utils import (
    load_nodes, normalize_func_id, 
    DEFAULT_POSTGRESQL_SRC_DIR, DEFAULT_NODES_FILE, DEFAULT_PIN_LOG_DIR
)


def extract_function_coverage_from_gcov_output(gcov_output: str, func_name: str) -> Optional[float]:
    """从gcov -f的输出中提取指定函数的覆盖率百分比"""
    try:
        lines = gcov_output.split('\n')
        current_function = None
        
        for line in lines:
            line = line.strip()
            func_match = re.match(r"Function '([^']+)'", line)
            if func_match:
                current_function = func_match.group(1)
                continue
            
            if current_function == func_name and "Lines executed:" in line:
                coverage_match = re.search(r'Lines executed:(\d+\.?\d*)%', line)
                if coverage_match:
                    return float(coverage_match.group(1))
        
        return None
    except Exception as e:
        print(f"解析gcov输出失败: {e}")
        return None


def extract_coverage_details_from_gcov_output(gcov_output: str, func_name: str) -> Dict[str, int]:
    """从gcov输出中提取详细的覆盖率信息"""
    try:
        lines = gcov_output.split('\n')
        current_function = None
        covered_lines = 0
        total_lines = 0
        
        for line in lines:
            line = line.strip()
            func_match = re.match(r"Function '([^']+)'", line)
            if func_match:
                current_function = func_match.group(1)
                continue
            
            if current_function == func_name and "Lines executed:" in line:
                total_match = re.search(r'Lines executed:[\d.]+% of (\d+)', line)
                if total_match:
                    total_lines = int(total_match.group(1))
                    coverage_match = re.search(r'Lines executed:(\d+\.?\d*)%', line)
                    if coverage_match:
                        coverage_percent = float(coverage_match.group(1))
                        covered_lines = int(round(total_lines * coverage_percent / 100.0))
                break
        
        return {
            'covered_lines': covered_lines,
            'total_lines': total_lines
        }
    except Exception as e:
        print(f"提取覆盖率详细信息失败: {e}")
        return {
            'covered_lines': 0,
            'total_lines': 0
        }


def extract_function_gcov_content(gcov_file_path: str, func_name: str, source_file: str) -> Optional[str]:
    """从 .gcov 文件中提取指定函数的覆盖率内容"""
    if not os.path.exists(gcov_file_path):
        return None
    
    try:
        with open(gcov_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 查找函数定义行
        func_start_idx = None
        for i, line in enumerate(lines):
            if re.search(rf':\s+\d+:{re.escape(func_name)}\s*\(', line):
                func_start_idx = i
                break
        
        if func_start_idx is None:
            return None
        
        # 从函数定义行往前查找注释块
        comment_start_idx = func_start_idx
        comment_end_idx = None
        
        for i in range(func_start_idx - 1, max(0, func_start_idx - 50), -1):
            line = lines[i]
            stripped = line.strip()
            if '*/' in stripped:
                comment_end_idx = i
                break
        
        if comment_end_idx is not None:
            comment_start_idx = comment_end_idx
            for i in range(comment_end_idx - 1, max(0, comment_end_idx - 30), -1):
                line = lines[i]
                stripped = line.strip()
                if '/*' in stripped:
                    comment_start_idx = i
                    break
                elif stripped and ('*' in stripped or stripped.startswith('*')):
                    comment_start_idx = i
                else:
                    break
        
        start_idx = comment_start_idx if comment_end_idx is not None else func_start_idx
        
        # 从开始位置到函数结束
        func_lines = []
        brace_count = 0
        in_function = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            func_lines.append(line.rstrip('\n'))
            
            if i == func_start_idx:
                in_function = True
                brace_count += line.count('{') - line.count('}')
            elif i > func_start_idx:
                brace_count += line.count('{') - line.count('}')
            
            if in_function and brace_count == 0 and i > func_start_idx:
                break
        
        return '\n'.join(func_lines)
    
    except Exception as e:
        print(f"读取 gcov 文件失败 {gcov_file_path}: {e}")
        return None


def update_node_gcov_content(target_func_id: str, gcov_content: str, nodes_file: str):
    """更新节点文件中的 gcov_content 属性"""
    try:
        with open(nodes_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nodes = data.get('nodes', {})
        if target_func_id in nodes:
            nodes[target_func_id]['gcov_content'] = gcov_content
            with open(nodes_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"已更新节点 {target_func_id} 的 gcov_content 属性")
    except Exception as e:
        print(f"更新节点文件失败: {e}")


def write_to_pin_log(func_name: str, trigger_sql: str, entry_function: str = "exec_simple_query") -> tuple:
    """将SQL和目标函数写入pin_log文件"""
    os.makedirs(DEFAULT_PIN_LOG_DIR, exist_ok=True)
    pin_log_file = os.path.join(DEFAULT_PIN_LOG_DIR, f"{func_name}.log")
    
    entry_index = 1
    if os.path.exists(pin_log_file):
        with open(pin_log_file, 'r', encoding='utf-8') as f:
            content = f.read()
            entry_index = content.count('==== NEW STATEMENT ====') + 1
    
    log_entry = f"""==== NEW STATEMENT ====
SQL: {trigger_sql}
>>> ENTER {entry_function}
{func_name}

"""
    
    with open(pin_log_file, 'a', encoding='utf-8') as f:
        f.write(log_entry)
    
    return (pin_log_file, entry_index)


def generate_sql_node_id(sql: str, func_name: str, nodes_file: str) -> str:
    """生成 SQL 节点ID"""
    sql_hash = hashlib.md5(sql.encode('utf-8')).hexdigest()
    hash8 = sql_hash[:8]
    
    nodes = load_nodes(nodes_file)
    counter = 1
    for node_id in nodes.keys():
        if node_id.startswith(f'sql:{hash8}@{func_name}#'):
            match = re.search(rf'sql:{hash8}@{re.escape(func_name)}#(\d+)', node_id)
            if match:
                existing_counter = int(match.group(1))
                counter = max(counter, existing_counter + 1)
    
    return f"sql:{hash8}@{func_name}#{counter:06d}"


def create_or_update_sql_node(sql: str, func_name: str, func_id: str, improvement_info: Dict, nodes_file: str) -> str:
    """创建或更新 SQL 节点"""
    try:
        with open(nodes_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nodes = data.get('nodes', {})
        sql_hash = hashlib.md5(sql.encode('utf-8')).hexdigest()
        hash8 = sql_hash[:8]
        
        existing_sql_node_id = None
        for node_id, node_data in nodes.items():
            if (node_id.startswith(f'sql:{hash8}@{func_name}#') and
                node_data.get('type') == 'sql' and
                node_data.get('sql') == sql and
                node_data.get('target_function') == func_id):
                existing_sql_node_id = node_id
                break
        
        if existing_sql_node_id:
            sql_node = nodes[existing_sql_node_id]
            if 'coverage_improvements' not in sql_node:
                sql_node['coverage_improvements'] = []
            sql_node['coverage_improvements'].append(improvement_info)
            sql_node_id = existing_sql_node_id
        else:
            sql_node_id = generate_sql_node_id(sql, func_name, nodes_file)
            sql_node = {
                'id': sql_node_id,
                'type': 'sql',
                'name': sql_node_id,
                'file_path': '',
                'line_number': 0,
                'raw_source': sql,
                'signature': '',
                'sql': sql,
                'target_function': func_id,
                'created_at': datetime.now().isoformat(),
                'coverage_improvements': [improvement_info]
            }
            nodes[sql_node_id] = sql_node
        
        with open(nodes_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"已{'更新' if existing_sql_node_id else '创建'}SQL节点: {sql_node_id}")
        return sql_node_id
    except Exception as e:
        print(f"创建或更新SQL节点失败: {e}")
        raise


@tool
def Collect_Coverage(
    target_func_id: str,
    trigger_sql: Optional[str] = None,
    coverage_improved: Optional[bool] = None,
    previous_coverage: Optional[float] = None,
    entry_function: Optional[str] = None,
    postgresql_src_dir: str = DEFAULT_POSTGRESQL_SRC_DIR,
    nodes_file: str = DEFAULT_NODES_FILE
) -> str:
    """收集PostgreSQL目标函数的代码覆盖率信息。
    
    功能：
    - 根据函数ID查找函数信息
    - 运行gcov命令更新.gcov文件（包含行级别的覆盖率信息）
    - 运行gcov -f命令获取函数级别的覆盖率
    - 提取函数的gcov内容（包含函数定义前的注释）
    - 自动更新节点文件中的gcov_content属性
    - 返回覆盖率百分比、覆盖行数、总行数等信息
    
    参数：
        target_func_id: 目标函数ID，格式：function:name@file_path:line_number
        trigger_sql: 【可选】触发覆盖率提升的SQL语句
        coverage_improved: 【可选】是否覆盖率提升
        previous_coverage: 【可选】之前的覆盖率（0-100）
        entry_function: 【可选】入口函数名，默认：exec_simple_query
    """
    try:
        if not target_func_id:
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': '',
                'file_path': '',
                'status': 'Error',
                'error_message': 'target_func_id参数为空'
            }, ensure_ascii=False)
        
        # 验证函数ID格式
        if not target_func_id.startswith('function:'):
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': '',
                'file_path': '',
                'status': 'Error',
                'error_message': f'''函数ID格式错误：缺少"function:"前缀

您提供的ID：{target_func_id}

正确格式：function:name@file_path:line_number

示例：
- Get_Code_Context返回：name="date_pli", file_path="postgresql-17.6/src/backend/utils/adt/date.c", line_number=504
- 正确的函数ID：function:date_pli@postgresql-17.6/src/backend/utils/adt/date.c:504

提示：请使用Get_Code_Context获取函数信息，然后构造正确的函数ID'''
            }, ensure_ascii=False)
        
        # 获取函数信息
        nodes = load_nodes(nodes_file)
        normalized_id = normalize_func_id(target_func_id, nodes)
        if not normalized_id:
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': '',
                'file_path': '',
                'status': 'Error',
                'error_message': f'未找到函数: {target_func_id}'
            }, ensure_ascii=False)
        
        func_info = nodes[normalized_id]
        func_name = func_info.get('name', '')
        file_path = func_info.get('file_path', '')
        
        if not file_path:
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': func_name,
                'file_path': '',
                'status': 'Error',
                'error_message': f'函数 {func_name} 没有文件路径信息'
            }, ensure_ascii=False)
        
        # 构建完整的源文件路径
        if os.path.isabs(file_path):
            source_file = file_path
        else:
            if file_path.startswith('postgresql-17.6/'):
                relative_path = file_path[len('postgresql-17.6/'):]
                source_file = os.path.join(postgresql_src_dir, relative_path)
            else:
                source_file = os.path.join(postgresql_src_dir, file_path)
        
        # 确保文件以.c结尾
        if not source_file.endswith('.c'):
            source_file += '.c'
        
        if not os.path.exists(source_file):
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': func_name,
                'file_path': file_path,
                'status': 'Error',
                'error_message': f'源文件不存在: {source_file}'
            }, ensure_ascii=False)
        
        # 检查是否存在gcda文件
        file_dir = os.path.dirname(source_file)
        file_name = os.path.basename(source_file)
        gcda_file = os.path.join(file_dir, f"{os.path.splitext(file_name)[0]}.gcda")
        if not os.path.exists(gcda_file):
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': func_name,
                'file_path': file_path,
                'status': 'Error',
                'error_message': f'未找到gcda文件: {gcda_file}，函数可能未被执行'
            }, ensure_ascii=False)
        
        # 步骤1: 先运行gcov命令更新.gcov文件
        gcov_update_result = subprocess.run(
            ['gcov', file_name],
            cwd=file_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if gcov_update_result.returncode != 0:
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': func_name,
                'file_path': file_path,
                'status': 'Error',
                'error_message': f'gcov命令执行失败（更新.gcov文件）: {gcov_update_result.stderr}'
            }, ensure_ascii=False)
        
        # 步骤2: 运行gcov -f命令获取函数级别的覆盖率
        gcov_result = subprocess.run(
            ['gcov', '-f', file_name],
            cwd=file_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if gcov_result.returncode != 0:
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': func_name,
                'file_path': file_path,
                'status': 'Error',
                'error_message': f'gcov命令执行失败: {gcov_result.stderr}'
            }, ensure_ascii=False)
        
        # 解析gcov -f的输出，查找目标函数的覆盖率
        coverage_percent = extract_function_coverage_from_gcov_output(gcov_result.stdout, func_name)
        
        if coverage_percent is None:
            return json5.dumps({
                'coverage': 0.0,
                'covered_lines': 0,
                'total_lines': 0,
                'function_name': func_name,
                'file_path': file_path,
                'status': 'Error',
                'error_message': f'未找到函数 {func_name} 的覆盖率信息'
            }, ensure_ascii=False)
        
        # 从gcov输出中提取更详细的信息
        coverage_details = extract_coverage_details_from_gcov_output(gcov_result.stdout, func_name)
        
        # 步骤3: 读取.gcov文件中对应函数的内容
        gcov_file_path = os.path.join(file_dir, f"{file_name}.gcov")
        gcov_content = extract_function_gcov_content(gcov_file_path, func_name, source_file)
        
        # 步骤4: 更新节点文件
        if gcov_content and normalized_id:
            update_node_gcov_content(normalized_id, gcov_content, nodes_file)
        
        # 步骤5: 如果覆盖率提升且提供了trigger_sql，保存到pin_log和更新图
        pin_log_info = None
        sql_node_id = None
        
        if coverage_improved and trigger_sql and normalized_id:
            try:
                improvement = coverage_percent - (previous_coverage if previous_coverage is not None else 0.0)
                pin_log_file, entry_index = write_to_pin_log(
                    func_name, trigger_sql, entry_function or "exec_simple_query"
                )
                pin_log_info = {
                    'pin_log_file': os.path.basename(pin_log_file),
                    'pin_log_entry_index': entry_index
                }
                sql_node_id = create_or_update_sql_node(
                    trigger_sql, func_name, normalized_id,
                    {
                        'function_id': normalized_id,
                        'improvement': improvement,
                        'timestamp': datetime.now().isoformat(),
                        'previous_coverage': previous_coverage if previous_coverage is not None else 0.0,
                        'new_coverage': coverage_percent,
                        'pin_log_file': os.path.basename(pin_log_file),
                        'pin_log_entry_index': entry_index
                    },
                    nodes_file
                )
            except Exception as e:
                print(f"保存覆盖率提升信息时发生错误: {e}")
        
        result = {
            'coverage': coverage_percent,
            'covered_lines': coverage_details.get('covered_lines', 0),
            'total_lines': coverage_details.get('total_lines', 0),
            'function_name': func_name,
            'file_path': file_path,
            'status': 'Success',
            'error_message': '',
            'gcov_content': gcov_content if gcov_content else ''
        }
        
        if pin_log_info:
            result['pin_log_file'] = pin_log_info['pin_log_file']
            result['pin_log_entry_index'] = pin_log_info['pin_log_entry_index']
        if sql_node_id:
            result['sql_node_id'] = sql_node_id
        
        return json5.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json5.dumps({
            'coverage': 0.0,
            'covered_lines': 0,
            'total_lines': 0,
            'function_name': '',
            'file_path': '',
            'status': 'Error',
            'error_message': f'收集覆盖率时发生异常: {str(e)}'
        }, ensure_ascii=False)
