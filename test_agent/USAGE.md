# 使用指南

## ✅ 当前状态

### 后端服务
**✅ 已启动并运行中**

- **服务地址**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **进程 ID**: 1073116 (后台运行)

### 可用智能体
1. **ollama_agent_with_tools** - PostgreSQL代码分析智能体
   - 工具：query_function_info, query_function_callers, query_function_callees, search_functions_by_keyword, get_call_graph

2. **coverage_multi_agent** - Coverage Multi-Agent
   - 工具：Run_SQL_Test, Collect_Coverage, Get_Code_Context, Search_Nearest_Seed, Traverse_Call_Graph

## 🚀 使用方式

### 方式1: 使用前端界面（推荐）

**前提条件：** 需要安装 Node.js

```bash
# 1. 安装 Node.js（如果未安装）
# 使用 nvm:
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 18

# 2. 安装前端依赖
cd /public/home/rongyankai/test_agent/frontend
npm install

# 3. 启动前端
npm run dev

# 4. 访问界面
# 浏览器打开: http://localhost:5173
```

### 方式2: 使用 API 文档（无需前端）

直接在浏览器中访问：**http://localhost:8000/docs**

这是 FastAPI 自动生成的交互式 API 文档，可以：
- 查看所有 API 接口
- 直接测试 API
- 查看请求/响应格式

### 方式3: 使用 curl 测试

#### 获取智能体列表
```bash
curl http://localhost:8000/api/agents
```

#### 发送消息（非流式）
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "ollama_agent_with_tools",
    "message": "查询函数 date2timestamptz"
  }'
```

### 方式4: 使用 Python 测试 WebSocket

创建测试脚本 `test_ws.py`:

```python
import asyncio
import websockets
import json

async def test():
    uri = "ws://localhost:8000/ws/stream"
    async with websockets.connect(uri) as ws:
        # 发送消息
        msg = {
            "agent_id": "ollama_agent_with_tools",
            "message": "查询函数 date2timestamptz"
        }
        await ws.send(json.dumps(msg))
        
        # 接收流式响应
        while True:
            response = await ws.recv()
            data = json.loads(response)
            print(f"收到: {data}")
            if data.get("type") == "done":
                break

asyncio.run(test())
```

运行：
```bash
pip install websockets
python3 test_ws.py
```

## 📋 快速测试

### 测试后端是否正常

```bash
cd /public/home/rongyankai/test_agent
python3 test_backend.py
```

### 查看服务日志

```bash
tail -f backend/server.log
```

### 停止后端服务

```bash
# 查找进程
ps aux | grep "python.*main.py"

# 停止服务（替换 PID）
kill <PID>
```

## 🎯 下一步

1. **如果已安装 Node.js**：
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   然后访问 http://localhost:5173

2. **如果未安装 Node.js**：
   - 使用 API 文档：http://localhost:8000/docs
   - 或安装 Node.js 后使用前端界面

3. **开始对话**：
   - 选择智能体
   - 发送消息
   - 查看流式输出和工具调用

## 📝 注意事项

1. **Neo4j 服务**：确保 Neo4j 正在运行（如果使用相关智能体）
   ```bash
   cd neo4j
   bash start_neo4j.sh status
   ```

2. **Ollama 服务**：确保 Ollama 正在运行并已安装模型
   ```bash
   ollama list
   ```

3. **端口占用**：
   - 后端：8000
   - 前端：5173
   - 如果端口被占用，可以修改配置

## 🔧 故障排查

### 后端无法启动
- 检查端口 8000 是否被占用：`netstat -tlnp | grep 8000`
- 查看日志：`tail -f backend/server.log`
- 检查依赖：`pip list | grep fastapi`

### 前端无法启动
- 检查 Node.js：`node --version`（需要 16+）
- 清除缓存：`rm -rf node_modules package-lock.json && npm install`
- 检查端口 5173 是否被占用

### API 请求失败
- 确认后端服务正在运行
- 检查 CORS 配置
- 查看后端日志
