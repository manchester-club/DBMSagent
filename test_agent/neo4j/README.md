# Neo4j 知识图谱导入工具

本目录包含将PostgreSQL知识图谱导入到Neo4j图数据库的所有工具和文档。

## 文件说明

- **neo4j_import.py**: 主导入脚本，用于将JSON格式的知识图谱导入到Neo4j
- **neo4j_tools.py**: Neo4j工具封装类，提供与现有工具兼容的接口
- **neo4j_README.md**: 详细的使用文档和说明
- **install_neo4j_local.sh**: Neo4j本地安装自动化脚本
- **neo4j_quick_start.sh**: 快速启动脚本（一键导入）
- **requirements_neo4j.txt**: Python依赖包列表

## 快速开始

### 1. 安装Neo4j

```bash
sudo ./install_neo4j_local.sh
```

### 2. 安装Python依赖

```bash
pip install -r requirements_neo4j.txt
```

### 3. 导入数据

```bash
export NEO4J_PASSWORD=your_password
./neo4j_quick_start.sh
```

或者手动导入：

```bash
python3 neo4j_import.py \
    --password your_password \
    --batch-size 2000 \
    --clear
```

## 详细文档

请查看 [neo4j_README.md](./neo4j_README.md) 获取完整的使用说明。

## 目录结构

```
/public/home/rongyankai/test_agent/neo4j/
├── README.md                    # 本文件
├── neo4j_README.md             # 详细文档
├── neo4j_import.py             # 导入脚本
├── neo4j_tools.py              # 工具封装
├── install_neo4j_local.sh      # 安装脚本
├── neo4j_quick_start.sh       # 快速启动脚本
└── requirements_neo4j.txt      # Python依赖
```

## 数据源

导入脚本默认从以下位置读取数据：
- 节点文件: `/public/home/rongyankai/graph/source/postgresql_nodes.json`
- 关系文件: `/public/home/rongyankai/graph/source/postgresql_relations.json`

可以通过命令行参数修改这些路径。



