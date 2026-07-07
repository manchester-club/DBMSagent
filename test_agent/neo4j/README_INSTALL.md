# Neo4j 安装完成

## 安装信息

- **版本**: Neo4j 2025.05.0 Community Edition
- **安装位置**: `/public/home/rongyankai/test_agent/neo4j/neo4j-server`
- **Java版本**: OpenJDK 21
- **状态**: ✅ 已启动

## 访问信息

- **Neo4j浏览器**: http://173.0.69.2:7474
- **Bolt端口**: 173.0.69.2:7687
- **默认用户名**: `neo4j`
- **默认密码**: `neo4j`（首次登录需要修改）

> 注意：IP地址为当前机器IP，如果IP变化，需要更新 `neo4j-server/conf/neo4j.conf` 中的 `server.default_advertised_address` 配置

## 管理命令

### 使用启动脚本（推荐）

```bash
cd /public/home/rongyankai/test_agent/neo4j

# 启动
./start_neo4j.sh start

# 停止
./start_neo4j.sh stop

# 状态
./start_neo4j.sh status

# 重启
./start_neo4j.sh restart

# 查看版本
./start_neo4j.sh version
```

### 直接使用neo4j命令

```bash
cd /public/home/rongyankai/test_agent/neo4j/neo4j-server

export NEO4J_HOME=$(pwd)
export NEO4J_CONF=$(pwd)/conf
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64

# 启动
./bin/neo4j start

# 停止
./bin/neo4j stop

# 状态
./bin/neo4j status
```

## 目录结构

```
neo4j/
├── neo4j-server/          # Neo4j主目录
│   ├── bin/              # 可执行文件
│   ├── lib/              # Java库文件
│   ├── conf/             # 配置文件
│   ├── data/             # 数据库文件
│   ├── logs/             # 日志文件
│   └── plugins/          # 插件目录
├── neo4j-extracted/      # RPM包提取的原始文件
├── neo4j-*.rpm          # RPM安装包
└── start_neo4j.sh       # 启动脚本
```

## 下一步

1. **修改默认密码**: 访问 http://localhost:7474 首次登录时修改
2. **导入数据**: 使用 `neo4j_import.py` 导入知识图谱
3. **配置优化**: 编辑 `neo4j-server/conf/neo4j.conf` 调整内存等设置

## 注意事项

- Neo4j需要Java 21运行环境
- 确保端口7474和7687未被占用
- 数据存储在 `neo4j-server/data/` 目录
- 日志文件在 `neo4j-server/logs/` 目录
