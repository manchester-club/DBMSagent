# Neo4j 导入状态报告

## 导入完成时间
2026-01-15

## 导入结果

### ✅ 成功导入

**节点**:
- Function节点: **10,996** 个

**关系**:
- CALLS关系: **24,763** 条
- INCLUDES关系: **7** 条

### ⚠️ 未导入的数据

根据JSON文件的metadata，应该有以下数据，但实际JSON文件中不存在：

**节点**（元数据中声明但文件中缺失）:
- Macro节点: 21,499 个（未找到）
- SQL节点: 18,998 个（未找到）
- Path节点: 12,936 个（未找到）

**关系**（元数据中声明但文件中缺失）:
- USES_MACRO关系: 168,902 条（未找到）
- SQL_EXECUTES_PATH关系: 18,998 条（未找到）
- FUNCTION_IN_PATH关系: 657,385 条（未找到）

## 原因分析

JSON文件 `/public/home/rongyankai/graph/source/postgresql_nodes.json` 的metadata显示应该有77,506个节点，但实际文件中只包含10,996个function节点。

可能的原因：
1. JSON文件不完整（被截断）
2. 数据生成时只导出了function节点
3. 其他类型的节点存储在单独的文件中

## 当前可用功能

虽然只导入了部分数据，但已导入的数据可以正常使用：

1. **函数节点查询**: 可以查询所有10,996个函数
2. **函数调用关系**: 可以查询CALLS关系（24,763条）
3. **函数包含关系**: 可以查询INCLUDES关系（7条）

## 下一步建议

1. **检查数据源**: 确认是否有完整的JSON文件包含所有节点类型
2. **补充导入**: 如果找到其他数据文件，可以继续导入
3. **使用现有数据**: 当前数据已可用于函数调用图分析

## 访问信息

- **Neo4j浏览器**: http://173.0.69.2:7474
- **Bolt连接**: bolt://173.0.69.2:7687
- **用户名**: neo4j
- **密码**: neo4j123

## 示例查询

```cypher
// 查找函数
MATCH (f:Function {name: "date2timestamptz_opt_overflow"})
RETURN f

// 查找函数的调用者
MATCH (caller:Function)-[:CALLS]->(callee:Function {name: "date2timestamptz_opt_overflow"})
RETURN caller.name, caller.file_path
LIMIT 10

// 查找函数的被调用者
MATCH (caller:Function {name: "date2timestamptz_opt_overflow"})-[:CALLS]->(callee:Function)
RETURN callee.name, callee.file_path
LIMIT 10
```



