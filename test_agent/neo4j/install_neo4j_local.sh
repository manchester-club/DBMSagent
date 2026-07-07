#!/bin/bash
# Neo4j本地安装脚本（Linux）

set -e

echo "=========================================="
echo "Neo4j 本地安装脚本"
echo "=========================================="

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  需要root权限，请使用sudo运行此脚本"
    exit 1
fi

# 安装目录
NEO4J_HOME="/opt/neo4j"
NEO4J_USER="neo4j"

# 检查是否已安装
if [ -d "$NEO4J_HOME" ]; then
    echo "⚠️  Neo4j已安装在 $NEO4J_HOME"
    read -p "是否重新安装？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    echo "正在停止现有服务..."
    $NEO4J_HOME/bin/neo4j stop 2>/dev/null || true
fi

# 创建neo4j用户（如果不存在）
if ! id "$NEO4J_USER" &>/dev/null; then
    echo "创建neo4j用户..."
    useradd -r -s /bin/false $NEO4J_USER
fi

# 下载Neo4j
echo "正在下载Neo4j..."
cd /tmp
NEO4J_VERSION="5.15.0"

# 尝试多个下载源
NEO4J_URLS=(
    "https://github.com/neo4j/neo4j/releases/download/${NEO4J_VERSION}/neo4j-community-${NEO4J_VERSION}-unix.tar.gz"
    "https://dist.neo4j.org/neo4j-community-${NEO4J_VERSION}-unix.tar.gz"
)

DOWNLOADED=false
for NEO4J_URL in "${NEO4J_URLS[@]}"; do
    echo "尝试从 $NEO4J_URL 下载..."
    if wget --no-check-certificate "$NEO4J_URL" 2>&1 | grep -q "200 OK\|saved"; then
        DOWNLOADED=true
        break
    fi
done

if [ "$DOWNLOADED" = false ] && [ ! -f "neo4j-community-${NEO4J_VERSION}-unix.tar.gz" ]; then
    echo "❌ 自动下载失败，请手动下载Neo4j:"
    echo "   1. 访问: https://neo4j.com/download-center/#community"
    echo "   2. 选择版本 ${NEO4J_VERSION}"
    echo "   3. 下载 Linux tar.gz 文件"
    echo "   4. 将文件放到 /tmp/neo4j-community-${NEO4J_VERSION}-unix.tar.gz"
    echo "   5. 然后重新运行此脚本"
    exit 1
fi

# 解压
echo "正在解压..."
tar -xzf neo4j-community-${NEO4J_VERSION}-unix.tar.gz

# 移动到安装目录
echo "正在安装到 $NEO4J_HOME..."
rm -rf $NEO4J_HOME
mv neo4j-community-${NEO4J_VERSION} $NEO4J_HOME

# 设置权限
chown -R $NEO4J_USER:$NEO4J_USER $NEO4J_HOME

# 配置Neo4j
echo "正在配置Neo4j..."
CONF_FILE="$NEO4J_HOME/conf/neo4j.conf"

# 备份原配置
cp $CONF_FILE ${CONF_FILE}.backup

# 修改配置
sed -i 's/#server.default_listen_address=0.0.0.0/server.default_listen_address=0.0.0.0/' $CONF_FILE || \
    echo "server.default_listen_address=0.0.0.0" >> $CONF_FILE

# 设置内存（根据系统内存调整）
TOTAL_MEM=$(free -g | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MEM" -ge 16 ]; then
    HEAP_SIZE="4g"
    PAGE_CACHE="2g"
elif [ "$TOTAL_MEM" -ge 8 ]; then
    HEAP_SIZE="2g"
    PAGE_CACHE="1g"
else
    HEAP_SIZE="1g"
    PAGE_CACHE="512m"
fi

sed -i "s/#dbms.memory.heap.initial_size=512m/dbms.memory.heap.initial_size=$HEAP_SIZE/" $CONF_FILE || \
    echo "dbms.memory.heap.initial_size=$HEAP_SIZE" >> $CONF_FILE

sed -i "s/#dbms.memory.heap.max_size=512m/dbms.memory.heap.max_size=$HEAP_SIZE/" $CONF_FILE || \
    echo "dbms.memory.heap.max_size=$HEAP_SIZE" >> $CONF_FILE

sed -i "s/#dbms.memory.pagecache.size=512m/dbms.memory.pagecache.size=$PAGE_CACHE/" $CONF_FILE || \
    echo "dbms.memory.pagecache.size=$PAGE_CACHE" >> $CONF_FILE

# 创建systemd服务文件（可选）
SYSTEMD_FILE="/etc/systemd/system/neo4j.service"
if [ ! -f "$SYSTEMD_FILE" ]; then
    echo "创建systemd服务..."
    cat > $SYSTEMD_FILE <<EOF
[Unit]
Description=Neo4j Graph Database
After=network.target

[Service]
Type=forking
User=$NEO4J_USER
ExecStart=$NEO4J_HOME/bin/neo4j start
ExecStop=$NEO4J_HOME/bin/neo4j stop
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable neo4j
    echo "✅ systemd服务已创建并启用"
fi

# 启动Neo4j
echo "正在启动Neo4j..."
sudo -u $NEO4J_USER $NEO4J_HOME/bin/neo4j start

# 等待启动
echo "等待Neo4j启动..."
sleep 10

# 检查状态
if $NEO4J_HOME/bin/neo4j status | grep -q "running"; then
    echo "✅ Neo4j安装并启动成功！"
    echo ""
    echo "访问信息:"
    echo "  - Neo4j浏览器: http://localhost:7474"
    echo "  - Bolt端口: localhost:7687"
    echo "  - 默认用户名: neo4j"
    echo "  - 默认密码: neo4j（首次登录需要修改）"
    echo ""
    echo "管理命令:"
    echo "  - 启动: sudo $NEO4J_HOME/bin/neo4j start"
    echo "  - 停止: sudo $NEO4J_HOME/bin/neo4j stop"
    echo "  - 状态: sudo $NEO4J_HOME/bin/neo4j status"
    echo "  - 重启: sudo $NEO4J_HOME/bin/neo4j restart"
    echo ""
    echo "或使用systemd:"
    echo "  - 启动: sudo systemctl start neo4j"
    echo "  - 停止: sudo systemctl stop neo4j"
    echo "  - 状态: sudo systemctl status neo4j"
else
    echo "❌ Neo4j启动失败，请检查日志:"
    echo "   tail -f $NEO4J_HOME/logs/neo4j.log"
    exit 1
fi

echo ""
echo "=========================================="
echo "安装完成！"
echo "=========================================="

