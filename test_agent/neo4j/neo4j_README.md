# Neo4j 知识图谱导入指南

## 一、概述

本指南介绍如何将PostgreSQL知识图谱从JSON格式导入到Neo4j图数据库中。

## 二、Neo4j数据模型

### 2.1 节点标签（Node Labels）

- **Function**: 函数节点
- **Macro**: 宏节点
- **SQL**: SQL语句节点
- **Path**: 执行路径节点
- **Node**: 所有节点的基标签（用于通用查询）

### 2.2 关系类型（Relationship Types）

- **CALLS**: 函数调用关系（Function → Function）
- **USES_MACRO**: 函数使用宏（Function → Macro）
- **INCLUDES**: 包含关系（Function → Node）
- **SQL_EXECUTES_PATH**: SQL执行路径（SQL → Path）
- **FUNCTION_IN_PATH**: 函数在路径中（Function → Path）

### 2.3 节点属性

#### Function节点
- `id`: 节点ID（唯一标识）
- `name`: 函数名
- `file_path`: 文件路径
- `line_number`: 行号
- `raw_source`: 源代码（限制100KB）
- `signature`: 函数签名
- `gcov_content`: 覆盖率信息（限制100KB）

#### Macro节点
- `id`: 节点ID
- `name`: 宏名
- `file_path`: 文件路径
- `line_number`: 行号
- `raw_source`: 宏定义
- `signature`: 宏签名

#### SQL节点
- `id`: 节点ID
- `name`: 节点ID（同id）
- `sql`: SQL语句
- `target_function`: 目标函数ID
- `created_at`: 创建时间
- `coverage_improvements`: 覆盖率提升记录（JSON字符串）

#### Path节点
- `id`: 节点ID
- `name`: 路径ID
- `path`: 函数调用路径（JSON字符串数组）

### 2.4 关系属性

#### FUNCTION_IN_PATH关系
- `position`: 函数在路径中的位置

## 三、安装和配置

### 3.1 安装Neo4j

#### 方式1: 本地安装（推荐）

**Linux系统（CentOS/RHEL）**:

1. 下载Neo4j Community Edition:
```bash
cd /tmp
wget https://neo4j.com/artifact.php?name=neo4j-community-5.15.0-unix.tar.gz
# 或者使用最新版本链接
```

2. 解压并安装:
```bash
tar -xzf neo4j-community-*.tar.gz
sudo mv neo4j-community-* /opt/neo4j
```

3. 配置环境变量（可选）:
```bash
echo 'export NEO4J_HOME=/opt/neo4j' >> ~/.bashrc
echo 'export PATH=$PATH:$NEO4J_HOME/bin' >> ~/.bashrc
source ~/.bashrc
```

4. 配置Neo4j:
```bash
cd /opt/neo4j
sudo nano conf/neo4j.conf
```

修改以下配置:
```properties
# 允许远程连接
server.default_listen_address=0.0.0.0

# 设置初始密码（首次启动后需要修改）
dbms.security.auth_enabled=true

# 内存配置（根据系统调整）
dbms.memory.heap.initial_size=2g
dbms.memory.heap.max_size=4g
dbms.memory.pagecache.size=2g
```

5. 启动Neo4j:
```bash
# 前台运行（测试用）
sudo /opt/neo4j/bin/neo4j console

# 后台运行（生产用）
sudo /opt/neo4j/bin/neo4j start
```

6. 检查状态:
```bash
sudo /opt/neo4j/bin/neo4j status
```

7. 访问Neo4j浏览器:
- 打开浏览器访问: http://localhost:7474
- 默认用户名: `neo4j`
- 默认密码: `neo4j`（首次登录会要求修改）

**使用包管理器安装（如果可用）**:

某些Linux发行版可能提供Neo4j包，但通常版本较旧，建议使用官方tar包。

#### 方式2: Docker安装（可选）

如果更喜欢使用Docker:
```bash
docker run \
    --name neo4j-postgresql-graph \
    -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/your_password \
    -e NEO4J_PLUGINS='["apoc"]' \
    -v neo4j_data:/data \
    neo4j:latest
```

#### 方式3: Neo4j Desktop（图形界面，适合开发）

访问 [Neo4j Desktop](https://neo4j.com/download/) 下载桌面版（支持Windows、macOS、Linux）。

### 3.2 安装Python依赖

```bash
cd /public/home/rongyankai/test_agent/neo4j
pip install -r requirements_neo4j.txt
# 或者手动安装
pip install neo4j tqdm
```

## 四、启动和管理Neo4j

### 4.1 启动Neo4j服务

**使用systemd（如果已配置）**:
```bash
sudo systemctl start neo4j
sudo systemctl status neo4j
```

**直接启动**:
```bash
sudo /opt/neo4j/bin/neo4j start
sudo /opt/neo4j/bin/neo4j status
```

### 4.2 停止Neo4j服务

```bash
sudo /opt/neo4j/bin/neo4j stop
# 或
sudo systemctl stop neo4j
```

### 4.3 查看日志

```bash
tail -f /opt/neo4j/logs/neo4j.log
```

## 五、导入数据

### 5.1 基本导入

```bash
python3 neo4j_import.py \
    --host localhost \
    --port 7687 \
    --user neo4j \
    --password your_password \
    --batch-size 1000
```

### 5.2 参数说明

- `--host`: Neo4j主机地址（默认: localhost）
- `--port`: Neo4j端口（默认: 7687）
- `--user`: 用户名（默认: neo4j）
- `--password`: 密码（必需）
- `--batch-size`: 批量导入大小（默认: 1000）
- `--nodes-file`: 节点JSON文件路径（默认: `graph/source/postgresql_nodes.json`）
- `--relations-file`: 关系JSON文件路径（默认: `graph/source/postgresql_relations.json`）
- `--clear`: 导入前清空数据库
- `--skip-nodes`: 跳过节点导入（仅导入边）
- `--skip-edges`: 跳过边导入（仅导入节点）

### 5.3 导入示例

#### 完整导入（清空后重新导入）
```bash
python3 neo4j_import.py \
    --password your_password \
    --clear \
    --batch-size 2000
```

#### 仅导入节点（不导入边）
```bash
python3 neo4j_import.py \
    --password your_password \
    --skip-edges
```

#### 仅导入边（节点已存在）
```bash
python3 neo4j_import.py \
    --password your_password \
    --skip-nodes
```

## 六、性能优化

### 6.1 批量大小调整

根据系统内存和Neo4j配置调整 `--batch-size`：
- 小内存系统: 500-1000
- 中等内存系统: 1000-2000
- 大内存系统: 2000-5000

### 6.2 Neo4j配置优化

编辑 `neo4j.conf` 文件：

```properties
# 增加堆内存
dbms.memory.heap.initial_size=2g
dbms.memory.heap.max_size=4g

# 增加页面缓存
dbms.memory.pagecache.size=2g

# 批量导入优化
dbms.transaction.timeout=600s
```

### 6.3 导入时间估算

- 节点导入: 约 5-10 分钟（77,506个节点）
- 边导入: 约 30-60 分钟（955,678条边）
- 总耗时: 约 40-70 分钟

## 七、验证导入

### 7.1 使用导入脚本验证

导入完成后，脚本会自动验证并显示统计信息。

### 7.2 使用Cypher查询验证

连接到Neo4j浏览器（http://localhost:7474）或使用cypher-shell：

```cypher
// 统计节点数
MATCH (n) RETURN labels(n) as label, count(n) as count ORDER BY count DESC;

// 统计关系数
MATCH ()-[r]->() RETURN type(r) as rel_type, count(r) as count ORDER BY count DESC;

// 查找特定函数
MATCH (f:Function {name: "date2timestamptz_opt_overflow"}) RETURN f;

// 查找函数的调用者
MATCH (caller:Function)-[:CALLS]->(callee:Function {name: "date2timestamptz_opt_overflow"})
RETURN caller.name, caller.file_path LIMIT 10;

// 查找函数的被调用者
MATCH (caller:Function {name: "date2timestamptz_opt_overflow"})-[:CALLS]->(callee:Function)
RETURN callee.name, callee.file_path LIMIT 10;
```

## 八、使用Neo4j工具

### 8.1 测试连接

```bash
python3 neo4j_tools.py
```

### 8.2 在Python中使用

```python
from neo4j_tools import Neo4jGraphDB

# 初始化连接
db = Neo4jGraphDB(uri="bolt://localhost:7687", 
                  user="neo4j", 
                  password="your_password")

# 获取函数节点
func = db.get_function_by_name("date2timestamptz_opt_overflow")
print(func)

# 获取调用者
callers = db.get_callers("function:date2timestamptz_opt_overflow@...")
print(f"调用者数量: {len(callers)}")

# 查找最近的SQL种子
seed = db.find_nearest_sql_seed("function:date2timestamptz_opt_overflow@...")
if seed:
    print(f"SQL: {seed['seed_sql']}")
    print(f"距离: {seed['distance']}")

# 关闭连接
db.close()
```

## 九、常见问题

### 9.1 导入失败：内存不足

**解决方案**:
1. 减小 `--batch-size` 参数
2. 增加Neo4j堆内存配置
3. 分批导入（先导入节点，再导入边）

### 9.2 导入失败：节点不存在

**原因**: 边引用的节点在节点文件中不存在

**解决方案**: 
- 脚本会自动跳过不存在的节点关系
- 检查JSON文件是否完整

### 9.3 属性值过大

**原因**: Neo4j属性值有大小限制（默认约100KB）

**解决方案**: 
- 脚本会自动截断超过100KB的属性值
- 大文本内容（如完整源代码）可以存储在外部文件或使用Neo4j的文本索引

### 9.4 导入速度慢

**优化建议**:
1. 增加批量大小（如果内存允许）
2. 优化Neo4j配置（增加内存）
3. 使用SSD存储
4. 关闭Neo4j的日志记录（仅用于导入）

## 十、后续工作

### 10.1 修改现有工具使用Neo4j

可以将 `tools.py` 中的工具修改为使用Neo4j而不是JSON文件：

```python
# 在 tools.py 中
from neo4j_tools import Neo4jGraphDB

class SearchNearestSeed(BaseTool):
    def __init__(self, ...):
        self.db = Neo4jGraphDB(...)
    
    def call(self, params, **kwargs):
        # 使用Neo4j查询替代JSON文件查询
        seed = self.db.find_nearest_sql_seed(target_func_id)
        ...
```

### 10.2 创建Neo4j查询工具

可以创建新的工具，利用Neo4j的强大查询能力：

- 复杂路径查询
- 图算法（如PageRank、社区检测）
- 模式匹配
- 实时图分析

### 10.3 性能监控

使用Neo4j的监控工具跟踪查询性能：
- Neo4j Browser（内置）
- Neo4j Desktop
- APOC插件

## 十一、参考资源

- [Neo4j官方文档](https://neo4j.com/docs/)
- [Cypher查询语言](https://neo4j.com/developer/cypher/)
- [Neo4j Python驱动](https://neo4j.com/docs/python-manual/current/)
- [Neo4j性能调优](https://neo4j.com/docs/operations-manual/current/performance/)

---

**文档版本**: 1.0  
**最后更新**: 2026-01-14

