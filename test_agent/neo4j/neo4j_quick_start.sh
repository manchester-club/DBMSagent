#!/bin/bash
# Neo4j快速启动脚本

set -e

echo "=========================================="
echo "Neo4j 知识图谱导入快速启动"
echo "=========================================="

# 检查Neo4j连接
echo "1. 检查Neo4j连接..."
python3 -c "
from neo4j import GraphDatabase
import sys

try:
    driver = GraphDatabase.driver('bolt://173.0.69.2:7687', auth=('neo4j', '${NEO4J_PASSWORD:-neo4j}'))
    with driver.session() as session:
        result = session.run('RETURN 1 as test')
        if result.single()['test'] == 1:
            print('✅ Neo4j连接成功')
    driver.close()
except Exception as e:
    print(f'❌ Neo4j连接失败: {e}')
    print('请确保:')
    print('  1. Neo4j服务正在运行')
    print('  2. 端口7687可访问')
    print('  3. 用户名和密码正确')
    print('  4. 设置环境变量: export NEO4J_PASSWORD=your_password')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    exit 1
fi

# 检查依赖
echo ""
echo "2. 检查Python依赖..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! python3 -c "import neo4j, tqdm" 2>/dev/null; then
    echo "⚠️  缺少依赖，正在安装..."
    pip install -r "$SCRIPT_DIR/requirements_neo4j.txt"
fi

# 开始导入
echo ""
echo "3. 开始导入数据..."
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/neo4j_import.py" \
    --host 173.0.69.2 \
    --port 7687 \
    --user neo4j \
    --password "${NEO4J_PASSWORD:-neo4j}" \
    --batch-size 2000 \
    --clear

echo ""
echo "=========================================="
echo "✅ 导入完成！"
echo ""
echo "访问Neo4j浏览器: http://173.0.69.2:7474"
echo "用户名: neo4j"
echo "密码: ${NEO4J_PASSWORD:-neo4j}"
echo "=========================================="

