# 后端服务运行指南

## 运行方式

### 方式 1：使用启动脚本（推荐）

在项目根目录运行：
```bash
cd /public/home/rongyankai/test_agent
bash start_backend.sh
```

或者直接运行：
```bash
./start_backend.sh
```

### 方式 2：在 backend 目录运行

```bash
cd /public/home/rongyankai/test_agent/backend
python3 main.py
```

或者使用 backend 目录下的启动脚本：
```bash
cd /public/home/rongyankai/test_agent/backend
bash start.sh
```

### 方式 3：后台运行（生产环境）

```bash
cd /public/home/rongyankai/test_agent/backend
nohup python3 main.py > server.log 2>&1 &
```

查看日志：
```bash
tail -f /public/home/rongyankai/test_agent/backend/server.log
```

停止服务：
```bash
pkill -f "python.*main.py"
```

## 服务信息

- **服务地址**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **WebSocket**: ws://localhost:8000/ws/stream
- **智能体列表**: http://localhost:8000/api/agents

## 依赖检查

确保已安装所有依赖：
```bash
cd /public/home/rongyankai/test_agent/backend
pip3 install -r requirements.txt
```

## 测试后端

运行测试脚本：
```bash
cd /public/home/rongyankai/test_agent
python3 test_backend.py
```

测试 WebSocket：
```bash
cd /public/home/rongyankai/test_agent
python3 test_websocket.py
```

## 常见问题

### 1. 端口被占用
如果 8000 端口被占用，可以修改 `main.py` 中的端口配置，或停止占用端口的进程：
```bash
lsof -i :8000
kill -9 <PID>
```

### 2. 依赖缺失
如果遇到导入错误，检查 Python 路径和依赖：
```bash
cd /public/home/rongyankai/test_agent/backend
python3 check_imports.py
```

### 3. 查看日志
如果服务启动失败，查看日志：
```bash
tail -50 /public/home/rongyankai/test_agent/backend/server.log
```
