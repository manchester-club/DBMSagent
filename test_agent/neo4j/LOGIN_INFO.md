# Neo4j 登录信息

## 默认登录信息

**用户名**: `neo4j`

**密码**: 
- 如果是首次安装，默认密码是 `neo4j`
- 首次登录后，系统会要求您更改密码

## 登录方式

### 方式1: 通过浏览器登录

**推荐访问路径**: http://173.0.69.2:7474/browser/preview/

或者尝试：
- http://173.0.69.2:7474/browser/
- http://173.0.69.2:7474/

首次登录时：
1. 用户名: `neo4j`
2. 密码: `neo4j`
3. 系统会提示您设置新密码

> **注意**: 如果根路径 `/` 无法访问，请使用 `/browser/preview/` 路径

### 方式2: 通过 Cypher Shell 登录

```bash
cd /public/home/rongyankai/test_agent/neo4j/neo4j-server
export NEO4J_HOME=$(pwd)
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
./bin/cypher-shell -a bolt://173.0.69.2:7687 -u neo4j -p neo4j
```

### 方式3: 通过 Python 驱动连接

```python
from neo4j import GraphDatabase

uri = "bolt://173.0.69.2:7687"
driver = GraphDatabase.driver(uri, auth=("neo4j", "neo4j"))

with driver.session() as session:
    result = session.run("MATCH (n) RETURN count(n)")
    print(result.single()[0])
```

## 修改密码

### 通过 Cypher Shell

```bash
cd /public/home/rongyankai/test_agent/neo4j/neo4j-server
export NEO4J_HOME=$(pwd)
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
./bin/cypher-shell -a bolt://173.0.69.2:7687 -u neo4j -p neo4j

# 在cypher-shell中执行
ALTER CURRENT USER SET PASSWORD FROM 'neo4j' TO '新密码';
```

### 通过 REST API

```bash
curl -X POST http://173.0.69.2:7474/user/neo4j/password \
  -H "Content-Type: application/json" \
  -d '{"password":"新密码"}' \
  -u neo4j:neo4j
```

## 当前状态

- ✅ Neo4j服务已启动
- ✅ 认证已启用 (`dbms.security.auth_enabled=true`)
- ✅ HTTP服务: http://173.0.69.2:7474
- ✅ Bolt服务: bolt://173.0.69.2:7687

## 注意事项

1. **首次登录**: 如果这是首次安装，默认密码是 `neo4j`，登录后必须更改密码
2. **忘记密码**: 如果忘记密码，需要重置数据库或使用恢复模式
3. **安全建议**: 生产环境请使用强密码，并考虑启用SSL/TLS

