#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run_SQL_Test Node - 执行SQL测试
"""

import os
import sys
import json5
from langchain_core.tools import tool

# 添加必要的路径以导入 DatabaseExecutor
_code_dir = os.path.join(os.path.dirname(__file__), '../../../code')
if os.path.exists(_code_dir):
    sys.path.insert(0, _code_dir)
try:
    from ai_sql_validator import DatabaseExecutor  # type: ignore
except ImportError:
    DatabaseExecutor = None


@tool
def Run_SQL_Test(sql_script: str) -> str:
    """在PostgreSQL数据库中执行SQL脚本并返回执行结果。
    
    功能：
    - 执行SQL语句（支持多行SQL，用分号分隔）
    - 返回执行状态（Success/SQL Error/Crash）
    - 返回错误信息（如果有）
    - 返回执行结果数据（如果有）
    
    使用场景：
    - 测试SQL语句是否正确
    - 验证SQL是否能触发目标函数
    - 检查SQL执行结果
    
    参数：
        sql_script: 要执行的SQL脚本文本（可以是多行SQL，用分号分隔）
    """
    try:
        if not sql_script:
            return json5.dumps({
                'status': 'SQL Error',
                'error_message': 'SQL脚本为空',
                'executed': False,
                'raw_result': 'SQL脚本为空'
            }, ensure_ascii=False)
        
        if DatabaseExecutor is None:
            return json5.dumps({
                'status': 'Crash',
                'error_message': 'DatabaseExecutor未找到，请检查ai_sql_validator.py是否存在',
                'executed': False,
                'raw_result': '工具初始化失败'
            }, ensure_ascii=False)
        
        # 默认数据库配置
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'postgres',
            'user': 'rongyankai',
            'password': ''
        }
        
        # 创建数据库执行器
        db_executor = DatabaseExecutor(db_config)
        
        # 连接数据库（带重试机制）
        if not db_executor.connect(max_retries=3, retry_delay=1.0):
            return json5.dumps({
                'status': 'Crash',
                'error_message': '数据库连接失败（已重试3次）',
                'executed': False,
                'raw_result': '数据库连接失败'
            }, ensure_ascii=False)
        
        try:
            # 执行SQL并获取原始结果
            success, message, db_results = db_executor.execute_sql(sql_script)
            
            # 构建返回结果
            if success:
                if db_results:
                    raw_result = f"执行成功: {message}\n返回数据: {str(db_results)}"
                    status = 'Success'
                else:
                    raw_result = f"执行成功: {message}"
                    status = 'Success'
            else:
                raw_result = f"执行失败: {message}"
                status = 'SQL Error'
            
            result = {
                'status': status,
                'error_message': '' if success else message,
                'executed': True,
                'raw_result': raw_result,
                'message': message
            }
            
            # 如果有返回数据，添加到结果中（限制大小以避免JSON过大）
            if db_results:
                try:
                    limited_results = list(db_results)[:100] if isinstance(db_results, list) else db_results
                    result['db_results'] = str(limited_results)
                    if isinstance(db_results, list) and len(db_results) > 100:
                        result['db_results'] += f'\n... (共{len(db_results)}行，仅显示前100行)'
                except:
                    result['db_results'] = '结果无法序列化'
            
            return json5.dumps(result, ensure_ascii=False)
            
        finally:
            # 确保关闭数据库连接
            db_executor.close()
            
    except Exception as e:
        return json5.dumps({
            'status': 'Crash',
            'error_message': f"执行异常: {str(e)}",
            'executed': True,
            'raw_result': f"执行异常: {str(e)}",
            'message': str(e)
        }, ensure_ascii=False)
