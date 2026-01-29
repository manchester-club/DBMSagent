#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Neo4j工具集 - 用于替代现有的JSON文件查询

提供与现有工具接口兼容的Neo4j实现
"""

import os
import sys
from typing import Dict, Optional, Any, List
import json5

try:
    from neo4j import GraphDatabase
except ImportError:
    print("错误: 需要安装neo4j驱动")
    print("请运行: pip install neo4j")
    sys.exit(1)


class Neo4jGraphDB:
    """Neo4j图数据库封装类"""
    
    def __init__(self, uri: str = "bolt://173.0.69.2:7687", 
                 user: str = "neo4j", 
                 password: str = ""):
        """
        初始化Neo4j连接
        
        Args:
            uri: Neo4j连接URI
            user: 用户名
            password: 密码
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        """关闭连接"""
        self.driver.close()
    
    def get_node_by_id(self, node_id: str) -> Optional[Dict]:
        """
        根据节点ID获取节点
        
        Args:
            node_id: 节点ID
        
        Returns:
            节点数据字典，如果未找到返回None
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (n:Node {id: $node_id}) RETURN n",
                node_id=node_id
            )
            record = result.single()
            if record:
                node = dict(record['n'])
                return node
            return None
    
    def get_function_by_name(self, func_name: str) -> Optional[Dict]:
        """
        根据函数名获取函数节点
        
        Args:
            func_name: 函数名
        
        Returns:
            函数节点数据字典，如果未找到返回None
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (f:Function {name: $func_name}) RETURN f LIMIT 1",
                func_name=func_name
            )
            record = result.single()
            if record:
                node = dict(record['f'])
                return node
            return None
    
    def get_callers(self, func_id: str, max_depth: int = 5) -> List[Dict]:
        """
        获取调用指定函数的所有函数（向上遍历）
        
        Args:
            func_id: 函数ID
            max_depth: 最大深度
        
        Returns:
            调用者函数列表
        """
        with self.driver.session() as session:
            query = """
            MATCH path = (caller:Function)-[:CALLS*1..%d]->(callee:Function {id: $func_id})
            RETURN DISTINCT caller
            LIMIT 100
            """ % max_depth
            
            result = session.run(query, func_id=func_id)
            callers = []
            for record in result:
                callers.append(dict(record['caller']))
            return callers
    
    def get_callees(self, func_id: str, max_depth: int = 5) -> List[Dict]:
        """
        获取指定函数调用的所有函数（向下遍历）
        
        Args:
            func_id: 函数ID
            max_depth: 最大深度
        
        Returns:
            被调用函数列表
        """
        with self.driver.session() as session:
            query = """
            MATCH path = (caller:Function {id: $func_id})-[:CALLS*1..%d]->(callee:Function)
            RETURN DISTINCT callee
            LIMIT 100
            """ % max_depth
            
            result = session.run(query, func_id=func_id)
            callees = []
            for record in result:
                callees.append(dict(record['callee']))
            return callees
    
    def find_nearest_sql_seed(self, func_id: str, max_depth: int = 5) -> Optional[Dict]:
        """
        查找距离目标函数最近的SQL种子
        
        Args:
            func_id: 目标函数ID
            max_depth: 最大搜索深度
        
        Returns:
            包含seed_sql、call_chain、distance的字典，如果未找到返回None
        """
        with self.driver.session() as session:
            # 首先检查函数是否直接有SQL触发
            query1 = """
            MATCH (f:Function {id: $func_id})-[:FUNCTION_IN_PATH]->(p:Path)<-[:SQL_EXECUTES_PATH]-(s:SQL)
            RETURN s.sql as seed_sql, p.path as call_chain, 0 as distance
            ORDER BY s.created_at DESC
            LIMIT 1
            """
            
            result = session.run(query1, func_id=func_id)
            record = result.single()
            if record:
                return {
                    'seed_sql': record['seed_sql'],
                    'call_chain': json5.loads(record['call_chain']) if isinstance(record['call_chain'], str) else record['call_chain'],
                    'distance': 0
                }
            
            # 如果直接没有，向上查找调用者
            query2 = """
            MATCH path = (caller:Function)-[:CALLS*1..%d]->(target:Function {id: $func_id})
            MATCH (caller)-[:FUNCTION_IN_PATH]->(p:Path)<-[:SQL_EXECUTES_PATH]-(s:SQL)
            WITH caller, s, p, length(path) as distance
            ORDER BY distance ASC, s.created_at DESC
            LIMIT 1
            RETURN s.sql as seed_sql, p.path as call_chain, distance
            """ % max_depth
            
            result = session.run(query2, func_id=func_id)
            record = result.single()
            if record:
                return {
                    'seed_sql': record['seed_sql'],
                    'call_chain': json5.loads(record['call_chain']) if isinstance(record['call_chain'], str) else record['call_chain'],
                    'distance': record['distance']
                }
            
            return None
    
    def get_functions_using_macro(self, macro_id: str) -> List[Dict]:
        """
        获取使用指定宏的所有函数
        
        Args:
            macro_id: 宏ID
        
        Returns:
            函数列表
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (f:Function)-[:USES_MACRO]->(m:Macro {id: $macro_id}) RETURN f",
                macro_id=macro_id
            )
            functions = []
            for record in result:
                functions.append(dict(record['f']))
            return functions
    
    def get_macros_used_by_function(self, func_id: str) -> List[Dict]:
        """
        获取指定函数使用的所有宏
        
        Args:
            func_id: 函数ID
        
        Returns:
            宏列表
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (f:Function {id: $func_id})-[:USES_MACRO]->(m:Macro) RETURN m",
                func_id=func_id
            )
            macros = []
            for record in result:
                macros.append(dict(record['m']))
            return macros


def test_connection():
    """测试Neo4j连接"""
    try:
        db = Neo4jGraphDB()
        with db.driver.session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            if record and record['test'] == 1:
                print("✅ Neo4j连接成功")
                return True
    except Exception as e:
        print(f"❌ Neo4j连接失败: {e}")
        return False
    finally:
        db.close()


if __name__ == '__main__':
    if test_connection():
        print("Neo4j工具已就绪")
    else:
        print("请检查Neo4j连接配置")

