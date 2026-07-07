#!/usr/bin/env python3
"""
Neo4j Cypher Shell 替代工具
使用方法: python3 cypher_shell.py
"""
from neo4j import GraphDatabase

uri = "bolt://173.0.69.2:7687"
user = "neo4j"
password = "neo4j123"

print("=" * 70)
print("Neo4j Cypher Shell (Python 替代)")
print("=" * 70)
print(f"连接到: {uri}")
print("输入 Cypher 查询（输入 'exit' 或 'quit' 退出）")
print("=" * 70)

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print("✅ 连接成功！\n")
    
    while True:
        try:
            query = input("cypher> ").strip()
            if not query:
                continue
            if query.lower() in ['exit', 'quit', 'q']:
                break
            
            with driver.session() as session:
                result = session.run(query)
                records = list(result)
                
                if records:
                    # 打印列名
                    keys = records[0].keys()
                    print("\n" + " | ".join(keys))
                    print("-" * 70)
                    
                    # 打印数据（限制显示50行）
                    for record in records[:50]:
                        values = [str(record[key])[:50] for key in keys]  # 限制列长度
                        print(" | ".join(values))
                    
                    if len(records) > 50:
                        print(f"\n... (共 {len(records)} 行，仅显示前50行)")
                    print()
                else:
                    print("(无结果)\n")
                    
        except KeyboardInterrupt:
            print("\n\n中断")
            break
        except Exception as e:
            print(f"❌ 错误: {e}\n")
            
finally:
    driver.close()
    print("✅ 连接已关闭")

