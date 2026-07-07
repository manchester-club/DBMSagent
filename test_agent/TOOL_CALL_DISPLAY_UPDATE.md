# 工具调用显示优化 ✅

## 更新内容

优化了工具调用的显示，现在会显示工具的入参和输出。

### 后端更新

1. **agent_manager.py**
   - 在发送 TOOL 事件时，包含工具的 `args`（入参）
   - 使用 `tool_id` 来匹配工具调用的开始和完成
   - 在工具调用开始时发送 `args`
   - 在工具调用完成时发送 `result`（输出）

2. **事件格式**
   ```python
   # 工具调用开始
   {
       "type": "tool",
       "timestamp": 1234567890,
       "agent": "CODE EXPLORER",
       "tool_name": "Get_Code_Context",
       "tool_id": "call_xxx",
       "args": {
           "query_name": "date_pli",
           "query_type": "FUNCTION"
       },
       "status": "RUNNING"
   }
   
   # 工具调用完成
   {
       "type": "tool",
       "timestamp": 1234567890,
       "agent": "CODE EXPLORER",
       "tool_name": "Get_Code_Context",
       "tool_id": "call_xxx",
       "status": "COMPLETED",
       "duration": "123ms",
       "result": "工具执行结果..."
   }
   ```

### 前端更新

1. **useWebSocket.ts**
   - 处理工具调用的 `args` 和 `result`
   - 使用 `tool_id` 来匹配和更新同一条工具调用消息
   - 当收到 COMPLETED 状态时，更新现有消息而不是创建新消息

2. **ActivityLog.tsx**
   - 工具调用类型使用 `ToolCallCard` 组件显示
   - 显示工具名称、入参（args）和输出（result）
   - 支持展开/折叠查看详细信息

3. **ToolCallCard.tsx**
   - 显示工具名称
   - 展开后显示参数（args）和结果（result）
   - 使用 CodeViewer 组件格式化显示 JSON

### 显示效果

现在 Activity Log 中工具调用会显示：

1. **工具调用开始（RUNNING）**
   - 工具名称
   - Agent 标签
   - 状态：RUNNING
   - 可展开查看入参

2. **工具调用完成（COMPLETED）**
   - 工具名称
   - Agent 标签
   - 状态：COMPLETED
   - 持续时间（如 `123ms`）
   - 可展开查看入参和输出

### 使用方式

1. 工具调用会显示在 Activity Log 中
2. 点击"展开"按钮可以查看：
   - **参数**：工具的输入参数（JSON 格式）
   - **结果**：工具的执行结果（JSON 或文本格式）
3. 点击"折叠"按钮可以收起详细信息

现在工具调用的完整信息（入参和输出）都会正确显示！✅
