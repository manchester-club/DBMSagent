#!/bin/bash
# 一键启动脚本（后端 + 前端）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 设置 Node.js 路径
export PATH="$HOME/.local/nodejs/node-v18.20.0-linux-x64/bin:$PATH"

echo "=========================================="
echo "启动 LangGraph 智能体平台"
echo "=========================================="
echo ""

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 未安装，正在安装..."
    bash install_nodejs.sh
    export PATH="$HOME/.local/nodejs/node-v18.20.0-linux-x64/bin:$PATH"
fi

echo "✅ Node.js: $(node --version)"
echo "✅ npm: $(npm --version)"
echo ""

# 检查后端是否运行
if ! curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "启动后端服务..."
    cd backend
    nohup python3 main.py > server.log 2>&1 &
    BACKEND_PID=$!
    echo "后端服务已启动 (PID: $BACKEND_PID)"
    sleep 2
    cd ..
else
    echo "✅ 后端服务已在运行"
fi

# 检查前端依赖
if [ ! -d "frontend/node_modules" ]; then
    echo "安装前端依赖..."
    cd frontend
    npm install
    cd ..
fi

# 启动前端
echo ""
echo "启动前端服务..."
echo "前端将在 http://localhost:5173 启动"
echo "按 Ctrl+C 停止服务"
echo ""

cd frontend
npm run dev
