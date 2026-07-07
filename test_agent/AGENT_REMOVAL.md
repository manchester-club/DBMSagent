# 智能体移除完成 ✅

## 修改内容

### 后端修改

1. **移除注册**：在 `backend/agents/agent_manager.py` 的 `_register_agents()` 方法中注释掉了 `ollama_agent_with_tools` 的注册
2. **保留类定义**：`OllamaAgentWithToolsWrapper` 类定义保留但未使用，便于后续重新启用

### 前端更新

前端代码**无需修改**，因为：
- 前端通过 API (`/api/agents`) 动态获取智能体列表
- 后端已移除注册，API 不再返回 `ollama_agent_with_tools`
- 前端界面会自动更新，只显示可用的智能体

## 当前可用智能体

- **Coverage Multi-Agent**
  - ID: `coverage_multi_agent`
  - 描述: Supervisor协调多个专家Agent（SQL Tester、Code Explorer、Coverage Analyzer）
  - 工具: 5 个
    - Run_SQL_Test
    - Collect_Coverage
    - Get_Code_Context
    - Search_Nearest_Seed
    - Traverse_Call_Graph

## 验证

### 后端 API
```bash
curl http://localhost:8000/api/agents
```

返回结果只包含 `coverage_multi_agent`。

### 前端界面

1. 刷新浏览器页面（如果前端正在运行）
2. 智能体选择器将只显示 "Coverage Multi-Agent"
3. 智能体树（右侧面板）也只显示这一个智能体

## 如需重新启用

如果需要重新启用 PostgreSQL 代码分析智能体：

1. 在 `backend/agents/agent_manager.py` 的 `_register_agents()` 方法中取消注释：
   ```python
   self.agents["ollama_agent_with_tools"] = OllamaAgentWithToolsWrapper()
   ```

2. 重启后端服务：
   ```bash
   cd backend
   python3 main.py
   ```

3. 前端会自动显示新添加的智能体

## 总结

✅ 后端已移除 PostgreSQL 代码分析智能体的注册
✅ 后端服务已重启，API 已更新
✅ 前端界面会自动更新（刷新页面即可）
✅ 系统现在只使用 Coverage Multi-Agent
