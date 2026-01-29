#!/usr/bin/env python3
"""检查Neo4j数据库状态"""
from neo4j import GraphDatabase

uri = "bolt://173.0.69.2:7687"
user = "neo4j"
password = "neo4j123"

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print("=" * 70)
    print("Neo4j 数据库状态")
    print("=" * 70)
    
    with driver.session() as session:
        # 基本统计
        print("\n【基本统计】")
        result = session.run("MATCH (n) RETURN count(n) as node_count")
        node_count = result.single()["node_count"]
        print(f"  节点总数: {node_count:,}")
        
        result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
        rel_count = result.single()["rel_count"]
        print(f"  关系总数: {rel_count:,}")
        
        # 节点标签统计
        print("\n【节点标签统计】")
        result = session.run("CALL db.labels() YIELD label RETURN collect(label) as labels")
        labels = result.single()["labels"]
        for label in sorted(labels):
            result = session.run(f"MATCH (n:{label}) RETURN count(n) as count")
            count = result.single()["count"]
            print(f"  {label}: {count:,}")
        
        # 关系类型统计
        print("\n【关系类型统计】")
        result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) as types")
        types = result.single()["types"]
        for rel_type in sorted(types):
            result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count")
            count = result.single()["count"]
            print(f"  {rel_type}: {count:,}")
        
        # 数据库信息
        print("\n【数据库信息】")
        try:
            result = session.run("CALL db.info() YIELD name, currentTime, uptime, storeSize, pageCacheSize, freeSpace RETURN name, currentTime, uptime, storeSize, pageCacheSize, freeSpace")
            info = result.single()
            if info:
                print(f"  数据库名称: {info.get('name', 'N/A')}")
                print(f"  当前时间: {info.get('currentTime', 'N/A')}")
                print(f"  运行时间: {info.get('uptime', 'N/A')}")
                print(f"  存储大小: {info.get('storeSize', 'N/A')}")
                print(f"  页面缓存: {info.get('pageCacheSize', 'N/A')}")
                print(f"  可用空间: {info.get('freeSpace', 'N/A')}")
        except Exception as e:
            print(f"  无法获取详细信息: {e}")
        
        # 示例节点
        print("\n【示例节点（前5个）】")
        result = session.run("MATCH (n) RETURN labels(n) as labels, n.name as name, n.id as id LIMIT 5")
        for record in result:
            labels_str = ":".join(record["labels"]) if record["labels"] else "Node"
            name = record.get("name") or record.get("id") or "N/A"
            print(f"  [{labels_str}] {name}")
        
        # 示例关系
        print("\n【示例关系（前5个）】")
        result = session.run("MATCH (a)-[r]->(b) RETURN type(r) as type, labels(a)[0] as from_label, a.name as from_name, labels(b)[0] as to_label, b.name as to_name LIMIT 5")
        for record in result:
            from_label = record.get("from_label") or "Node"
            from_name = record.get("from_name") or "N/A"
            to_label = record.get("to_label") or "Node"
            to_name = record.get("to_name") or "N/A"
            rel_type = record["type"]
            print(f"  [{from_label}] {from_name} -[{rel_type}]-> [{to_label}] {to_name}")
    
    print("\n" + "=" * 70)
    print("✅ 状态检查完成")
    driver.close()
    
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()

