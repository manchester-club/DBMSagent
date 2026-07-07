#!/bin/bash
# 启动后端服务

cd "$(dirname "$0")/backend"
echo "启动后端服务..."
echo "后端将在 http://localhost:8000 启动"
echo "按 Ctrl+C 停止服务"
echo ""

python3 main.py
