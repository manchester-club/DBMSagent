# 快速启动指南

## 当前状态

### ✅ 后端服务
后端服务已启动（后台运行）

**访问地址：**
- API 文档：http://localhost:8000/docs
- 智能体列表：http://localhost:8000/api/agents

### ⚠️ 前端服务
前端需要 Node.js 环境，当前系统未安装 Node.js。

## 启动步骤

### 1. 后端服务（已启动）

后端服务已在后台运行。如果未运行，可以手动启动：

```bash
cd /public/home/rongyankai/test_agent/backend
python3 main.py
```

或者使用启动脚本：
```bash
cd /public/home/rongyankai/test_agent
./start_backend.sh
```

### 2. 前端服务（需要 Node.js）

#### 选项A：安装 Node.js（推荐）

**使用 nvm 安装（推荐）：**
```bash
# 安装 nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# 重新加载 shell
source ~/.bashrc

# 安装 Node.js 18
nvm install 18
nvm use 18

# 验证安装
node --version
npm --version
```

**或使用系统包管理器：**
```bash
# CentOS/RHEL
sudo yum install nodejs npm

# Ubuntu/Debian
sudo apt-get install nodejs npm
```

#### 选项B：使用现有 Node.js（如果有）

如果系统其他地方有 Node.js，可以使用完整路径。

#### 安装前端依赖并启动

```bash
cd /public/home/rongyankai/test_agent/frontend
npm install
npm run dev
```

或使用启动脚本：
```bash
cd /public/home/rongyankai/test_agent
./start_frontend.sh
```

## 测试后端 API

### 1. 获取智能体列表

```bash
curl http://localhost:8000/api/agents
```

### 2. 测试非流式聊天

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "ollama_agent_with_tools",
    "message": "查询函数 date2timestamptz"
  }'
```

### 3. 访问 API 文档

在浏览器中打开：http://localhost:8000/docs

## 使用 WebSocket 测试（命令行）

如果安装了 `websocat` 或 `wscat`：

```bash
# 使用 websocat
echo '{"agent_id":"ollama_agent_with_tools","message":"查询函数 date2timestamptz"}' | \
  websocat ws://localhost:8000/ws/stream

# 或使用 wscat
wscat -c ws://localhost:8000/ws/stream
# 然后输入：
# {"agent_id":"ollama_agent_with_tools","message":"查询函数 date2timestamptz"}
```

## 当前可用功能

### 后端 API（已就绪）
- ✅ REST API：获取智能体列表、信息
- ✅ WebSocket API：流式输出
- ✅ 2 个智能体已注册

### 前端界面（需要 Node.js）
- ⚠️ 需要安装 Node.js 后才能使用
- ✅ 代码已就绪，安装依赖后即可使用

## 临时解决方案

如果暂时无法安装 Node.js，可以使用：

### 1. 直接测试后端 API

使用 `curl` 或 Postman 测试 REST API

### 2. 使用 Python 测试 WebSocket

创建测试脚本：

```python
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/stream"
    async with websockets.connect(uri) as websocket:
        # 发送消息
        message = {
            "agent_id": "ollama_agent_with_tools",
            "message": "查询函数 date2timestamptz"
        }
        await websocket.send(json.dumps(message))
        
        # 接收响应
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            print(f"收到: {data}")
            if data.get("type") == "done":
                break

asyncio.run(test_websocket())
```

## 下一步

1. **安装 Node.js**（如果还没有）
2. **启动前端**：`cd frontend && npm install && npm run dev`
3. **访问界面**：http://localhost:5173
4. **开始使用**：选择智能体，发送消息，查看流式输出
