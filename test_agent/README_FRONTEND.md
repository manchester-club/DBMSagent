# LangGraph 智能体前端平台

## 功能特性

- ✅ 多智能体切换（ollama_agent_with_tools, coverage_multi_agent 等）
- ✅ 实时流式输出（WebSocket）
- ✅ 工具调用可视化（可展开/折叠）
- ✅ 代码高亮显示（Monaco Editor）
- ✅ 对话记录导出（TXT 格式）
- ✅ 响应式界面（Ant Design）

## 快速开始

### 1. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 启动后端服务

```bash
cd backend
python main.py
```

后端将在 `http://localhost:8000` 启动

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

### 4. 启动前端开发服务器

```bash
cd frontend
npm run dev
```

前端将在 `http://localhost:5173` 启动

## 使用说明

1. **选择智能体**：在顶部选择要使用的智能体
2. **发送消息**：在输入框中输入问题，按 Enter 或点击发送
3. **查看工具调用**：工具调用会显示为可展开的卡片
4. **导出对话**：点击"导出"按钮保存对话记录

## 项目结构

```
test_agent/
├── backend/              # FastAPI 后端
│   ├── main.py          # 主服务器
│   ├── agents/          # 智能体封装
│   └── requirements.txt
├── frontend/            # React 前端
│   ├── src/
│   │   ├── components/  # UI 组件
│   │   ├── hooks/       # React Hooks
│   │   └── types/       # TypeScript 类型
│   └── package.json
└── langgraph/           # 智能体实现（现有代码）
```

## API 接口

### REST API

- `GET /api/agents` - 获取所有智能体列表
- `GET /api/agents/{agent_id}` - 获取特定智能体信息
- `POST /api/chat` - 非流式聊天（测试用）

### WebSocket API

- `ws://localhost:8000/ws/stream` - 流式输出

**发送消息格式**：
```json
{
  "agent_id": "ollama_agent_with_tools",
  "message": "查询函数 date2timestamptz"
}
```

**接收事件格式**：
```json
{
  "type": "text_chunk",
  "content": "根据您的查询..."
}
```

## 注意事项

1. 确保 Neo4j 服务正在运行（如果使用相关智能体）
2. 确保 Ollama 服务正在运行并已安装模型
3. 后端和前端需要同时运行

## 开发

### 添加新智能体

1. 在 `backend/agents/agent_manager.py` 中创建新的 Wrapper 类
2. 在 `_register_agents()` 中注册新智能体
3. 前端会自动显示新智能体

### 自定义样式

修改 `frontend/src/index.css` 和组件样式
