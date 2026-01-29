#!/bin/bash
# 启动前端服务

cd "$(dirname "$0")/frontend"

# 检查 node_modules 是否存在
if [ ! -d "node_modules" ]; then
    echo "检测到 node_modules 不存在，正在安装依赖..."
    if command -v npm &> /dev/null; then
        npm install
    else
        echo "错误: 未找到 npm，请先安装 Node.js"
        exit 1
    fi
fi

echo "启动前端开发服务器..."
echo "前端将在 http://localhost:5173 启动"
echo "按 Ctrl+C 停止服务"
echo ""

npm run dev
