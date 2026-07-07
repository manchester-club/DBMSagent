#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Neo4j导入验证测试脚本

运行此脚本验证数据导入是否成功
"""

from neo4j import GraphDatabase
import sys

def test_import():
    """测试导入结果"""
    try:
        driver = GraphDatabase.driver('bolt://173.0.69.2:7687', auth=('neo4j', 'neo4j123'))
        session = driver.session()
        
        print("=" * 60)
        print("Neo4j 导入验证测试")
        print("=" * 60)
        
        # 基本统计
        result = session.run("MATCH (n) RETURN count(n) as total")
        total_nodes = result.single()['total']
        print(f"\n✅ 节点总数: {total_nodes}")
        
        result = session.run("MATCH ()-[r]->() RETURN count(r) as total")
        total_rels = result.single()['total']
        print(f"✅ 关系总数: {total_rels}")
        
        # 验证特定函数
        result = session.run("""
            MATCH (f:Function {name: "date2timestamptz_opt_overflow"})
            RETURN f.name as name, f.file_path as file_path
        """)
        record = result.single()
        if record:
            print(f"\n✅ 验证函数存在: {record['name']}")
            print(f"   文件路径: {record['file_path']}")
        else:
            print("\n❌ 未找到测试函数")
            return False
        
        # 验证调用关系
        result = session.run("""
            MATCH (caller:Function)-[:CALLS]->(callee:Function {name: "date2timestamptz_opt_overflow"})
            RETURN count(caller) as count
        """)
        caller_count = result.single()['count']
        print(f"✅ 找到 {caller_count} 个调用者")
        
        session.close()
        driver.close()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！导入成功！")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_import()
    sys.exit(0 if success else 1)



