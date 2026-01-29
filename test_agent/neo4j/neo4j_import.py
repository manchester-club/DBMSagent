#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将PostgreSQL知识图谱导入到Neo4j图数据库

使用方法:
    python3 neo4j_import.py [--host localhost] [--port 7687] [--user neo4j] [--password password] [--batch-size 1000]

功能:
    1. 从JSON文件加载节点和边数据
    2. 批量导入到Neo4j
    3. 创建索引以优化查询性能
    4. 支持断点续传（如果导入中断，可以继续）
"""

import json
import argparse
import sys
from typing import Dict, List, Optional
from tqdm import tqdm
import time

try:
    from neo4j import GraphDatabase
except ImportError:
    print("错误: 需要安装neo4j驱动")
    print("请运行: pip install neo4j")
    sys.exit(1)


class Neo4jImporter:
    """Neo4j导入器"""
    
    def __init__(self, uri: str, user: str, password: str, batch_size: int = 1000):
        """
        初始化Neo4j导入器
        
        Args:
            uri: Neo4j连接URI（如 bolt://localhost:7687）
            user: 用户名
            password: 密码
            batch_size: 批量导入大小
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = batch_size
        self.session = None
    
    def __enter__(self):
        self.session = self.driver.session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
        self.driver.close()
    
    def clear_database(self):
        """清空数据库（可选，用于重新导入）"""
        print("⚠️  清空数据库...")
        self.session.run("MATCH (n) DETACH DELETE n")
        print("✅ 数据库已清空")
    
    def create_indexes(self):
        """创建索引以优化查询性能"""
        print("📊 创建索引...")
        
        indexes = [
            # 节点ID索引（用于快速查找节点）
            "CREATE INDEX node_id_index IF NOT EXISTS FOR (n:Node) ON (n.id)",
            # 函数名索引
            "CREATE INDEX function_name_index IF NOT EXISTS FOR (f:Function) ON (f.name)",
            # 文件路径索引
            "CREATE INDEX file_path_index IF NOT EXISTS FOR (n:Node) ON (n.file_path)",
            # 宏名索引
            "CREATE INDEX macro_name_index IF NOT EXISTS FOR (m:Macro) ON (m.name)",
        ]
        
        for index_query in indexes:
            try:
                self.session.run(index_query)
            except Exception as e:
                # 如果索引已存在，忽略错误
                if "already exists" not in str(e).lower():
                    print(f"⚠️  创建索引时出错: {e}")
        
        print("✅ 索引创建完成")
    
    def import_nodes(self, nodes_file: str, clear_first: bool = False):
        """
        导入节点
        
        Args:
            nodes_file: 节点JSON文件路径
            clear_first: 是否先清空数据库
        """
        if clear_first:
            self.clear_database()
        
        print(f"📥 加载节点文件: {nodes_file}")
        with open(nodes_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nodes = data.get('nodes', {})
        total_nodes = len(nodes)
        print(f"📊 总节点数: {total_nodes}")
        
        # 按类型分组导入
        node_types = {
            'function': 'Function',
            'macro': 'Macro',
            'sql': 'SQL',
            'path': 'Path'
        }
        
        for node_type, label in node_types.items():
            type_nodes = {k: v for k, v in nodes.items() if v.get('type') == node_type}
            if not type_nodes:
                continue
            
            print(f"\n📦 导入 {label} 节点 ({len(type_nodes)} 个)...")
            self._import_nodes_by_type(type_nodes, label)
        
        # 创建索引
        self.create_indexes()
        print("\n✅ 节点导入完成")
    
    def _import_nodes_by_type(self, nodes: Dict, label: str):
        """按类型导入节点（批量）"""
        batch = []
        total = len(nodes)
        
        with tqdm(total=total, desc=f"导入 {label}") as pbar:
            for node_id, node_data in nodes.items():
                # 准备节点属性
                props = {
                    'id': node_id,
                    'name': node_data.get('name', ''),
                    'file_path': node_data.get('file_path', ''),
                    'line_number': node_data.get('line_number', 0),
                }
                
                # 添加可选属性
                if 'raw_source' in node_data:
                    # 限制raw_source长度（Neo4j属性值有大小限制）
                    raw_source = node_data.get('raw_source', '')
                    if len(raw_source) > 100000:  # 限制为100KB
                        props['raw_source'] = raw_source[:100000] + '... [truncated]'
                    else:
                        props['raw_source'] = raw_source
                
                if 'signature' in node_data:
                    props['signature'] = node_data.get('signature', '')
                
                if 'gcov_content' in node_data:
                    gcov_content = node_data.get('gcov_content', '')
                    if len(gcov_content) > 100000:  # 限制为100KB
                        props['gcov_content'] = gcov_content[:100000] + '... [truncated]'
                    else:
                        props['gcov_content'] = gcov_content
                
                # SQL节点特殊属性
                if label == 'SQL':
                    if 'sql' in node_data:
                        props['sql'] = node_data.get('sql', '')
                    if 'target_function' in node_data:
                        props['target_function'] = node_data.get('target_function', '')
                    if 'created_at' in node_data:
                        props['created_at'] = node_data.get('created_at', '')
                    if 'coverage_improvements' in node_data:
                        # 将数组转换为JSON字符串
                        props['coverage_improvements'] = json.dumps(node_data.get('coverage_improvements', []))
                
                # Path节点特殊属性
                if label == 'Path':
                    if 'path' in node_data:
                        # 将数组转换为JSON字符串
                        props['path'] = json.dumps(node_data.get('path', []))
                
                batch.append((node_id, props))
                
                # 批量导入
                if len(batch) >= self.batch_size:
                    self._create_nodes_batch(batch, label)
                    pbar.update(len(batch))
                    batch = []
            
            # 导入剩余节点
            if batch:
                self._create_nodes_batch(batch, label)
                pbar.update(len(batch))
    
    def _create_nodes_batch(self, batch: List[tuple], label: str):
        """批量创建节点"""
        query = f"""
        UNWIND $batch AS node
        MERGE (n:Node:{label} {{id: node.id}})
        SET n += node.props
        """
        
        params = {
            'batch': [{'id': node_id, 'props': props} for node_id, props in batch]
        }
        
        self.session.run(query, params)
    
    def import_edges(self, relations_file: str):
        """
        导入边（关系）
        
        Args:
            relations_file: 关系JSON文件路径
        """
        print(f"\n📥 加载关系文件: {relations_file}")
        with open(relations_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        edges = data.get('edges', [])
        total_edges = len(edges)
        print(f"📊 总边数: {total_edges}")
        
        # 按类型分组导入
        edge_types = {
            'calls': 'CALLS',
            'uses_macro': 'USES_MACRO',
            'includes': 'INCLUDES',
            'sql_executes_path': 'SQL_EXECUTES_PATH',
            'function_in_path': 'FUNCTION_IN_PATH'
        }
        
        for edge_type, rel_type in edge_types.items():
            type_edges = [e for e in edges if e.get('type') == edge_type]
            if not type_edges:
                continue
            
            print(f"\n🔗 导入 {rel_type} 关系 ({len(type_edges)} 条)...")
            self._import_edges_by_type(type_edges, rel_type)
        
        print("\n✅ 边导入完成")
    
    def _import_edges_by_type(self, edges: List[Dict], rel_type: str):
        """按类型导入边（批量）"""
        batch = []
        total = len(edges)
        
        with tqdm(total=total, desc=f"导入 {rel_type}") as pbar:
            for edge in edges:
                source = edge.get('source')
                target = edge.get('target')
                
                if not source or not target:
                    continue
                
                # 准备关系属性
                props = {}
                if 'position' in edge:
                    props['position'] = edge.get('position')
                
                batch.append({
                    'source': source,
                    'target': target,
                    'props': props
                })
                
                # 批量导入
                if len(batch) >= self.batch_size:
                    self._create_relationships_batch(batch, rel_type)
                    pbar.update(len(batch))
                    batch = []
            
            # 导入剩余边
            if batch:
                self._create_relationships_batch(batch, rel_type)
                pbar.update(len(batch))
    
    def _create_relationships_batch(self, batch: List[Dict], rel_type: str):
        """批量创建关系"""
        query = f"""
        UNWIND $batch AS rel
        MATCH (source:Node {{id: rel.source}})
        MATCH (target:Node {{id: rel.target}})
        MERGE (source)-[r:{rel_type}]->(target)
        SET r += rel.props
        """
        
        params = {'batch': batch}
        
        try:
            self.session.run(query, params)
        except Exception as e:
            # 如果节点不存在，尝试逐条创建（跳过不存在的节点）
            error_count = 0
            for rel in batch:
                try:
                    single_query = f"""
                    MATCH (source:Node {{id: $source}})
                    MATCH (target:Node {{id: $target}})
                    MERGE (source)-[r:{rel_type}]->(target)
                    SET r += $props
                    """
                    self.session.run(single_query, 
                                   source=rel['source'],
                                   target=rel['target'],
                                   props=rel['props'])
                except:
                    error_count += 1
                    continue
            if error_count > 0:
                print(f"⚠️  跳过 {error_count} 条关系（节点不存在）")
    
    def verify_import(self):
        """验证导入结果"""
        print("\n🔍 验证导入结果...")
        
        # 统计节点数
        node_counts = {}
        for label in ['Function', 'Macro', 'SQL', 'Path']:
            result = self.session.run(f"MATCH (n:{label}) RETURN count(n) as count")
            count = result.single()['count']
            node_counts[label] = count
            print(f"  {label}: {count} 个节点")
        
        # 统计边数
        edge_counts = {}
        for rel_type in ['CALLS', 'USES_MACRO', 'INCLUDES', 'SQL_EXECUTES_PATH', 'FUNCTION_IN_PATH']:
            result = self.session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count")
            count = result.single()['count']
            edge_counts[rel_type] = count
            print(f"  {rel_type}: {count} 条关系")
        
        print("\n✅ 验证完成")
        return node_counts, edge_counts


def main():
    parser = argparse.ArgumentParser(description='将PostgreSQL知识图谱导入到Neo4j')
    parser.add_argument('--host', default='173.0.69.2', help='Neo4j主机地址')
    parser.add_argument('--port', type=int, default=7687, help='Neo4j端口')
    parser.add_argument('--user', default='neo4j', help='Neo4j用户名')
    parser.add_argument('--password', required=True, help='Neo4j密码')
    parser.add_argument('--batch-size', type=int, default=1000, help='批量导入大小')
    parser.add_argument('--nodes-file', default='/public/home/rongyankai/graph/source/postgresql_nodes.json',
                       help='节点JSON文件路径')
    parser.add_argument('--relations-file', default='/public/home/rongyankai/graph/source/postgresql_relations.json',
                       help='关系JSON文件路径')
    parser.add_argument('--clear', action='store_true', help='导入前清空数据库')
    parser.add_argument('--skip-nodes', action='store_true', help='跳过节点导入（仅导入边）')
    parser.add_argument('--skip-edges', action='store_true', help='跳过边导入（仅导入节点）')
    
    args = parser.parse_args()
    
    uri = f"bolt://{args.host}:{args.port}"
    
    print("=" * 60)
    print("PostgreSQL 知识图谱 Neo4j 导入工具")
    print("=" * 60)
    print(f"Neo4j URI: {uri}")
    print(f"批量大小: {args.batch_size}")
    print("=" * 60)
    
    start_time = time.time()
    
    try:
        with Neo4jImporter(uri, args.user, args.password, args.batch_size) as importer:
            # 导入节点
            if not args.skip_nodes:
                importer.import_nodes(args.nodes_file, clear_first=args.clear)
            else:
                print("⏭️  跳过节点导入")
            
            # 导入边
            if not args.skip_edges:
                importer.import_edges(args.relations_file)
            else:
                print("⏭️  跳过边导入")
            
            # 验证导入结果
            importer.verify_import()
        
        elapsed_time = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"✅ 导入完成！总耗时: {elapsed_time:.2f} 秒")
        print("=" * 60)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  导入被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

