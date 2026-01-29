# ToolNode 配置错误修复 ✅

## 错误信息

```
Missing required config key 'N/A' for 'tools'.
```

## 问题原因

LangGraph 的 `ToolNode` 在某些版本中存在配置问题，即使提供了正确的配置参数，仍然会报错。这是因为 `ToolNode.invoke()` 方法内部对配置的处理存在问题。

## 修复方案

### 修改位置：`langgraph/coverage_multi_agent.py` 的 `_run_agent_loop` 函数

**之前（使用 ToolNode）：**
```python
tool_node = ToolNode(tools=tools)
tool_state = {"messages": messages + to_append}
tool_config = {"configurable": {}}
tool_out = tool_node.invoke(tool_state, config=tool_config)
tool_msgs = tool_out["messages"]
```

**修复后（直接调用工具函数）：**
```python
# 不使用 ToolNode，直接调用工具函数以避免配置问题
tool_msgs = []
for tc in response.tool_calls:
    name = tc.get("name", "?")
    args = tc.get("args", {})
    tool_id = tc.get("id", "unknown")
    
    # 直接查找并调用工具函数
    tool_func = None
    for tool in tools:
        if tool.name == name:
            tool_func = tool
            break
    
    if tool_func:
        try:
            result = tool_func.invoke(args)
            tool_msg = ToolMessage(
                content=str(result),
                tool_call_id=str(tool_id),
                name=name
            )
            tool_msgs.append(tool_msg)
        except Exception as e:
            error_msg = ToolMessage(
                content=f"工具执行失败: {str(e)}",
                tool_call_id=str(tool_id),
                name=name
            )
            tool_msgs.append(error_msg)
```

## 优势

1. **避免配置问题**：不再依赖 ToolNode 的配置机制
2. **更直接的控制**：可以直接处理工具调用的错误
3. **更好的错误处理**：可以为每个工具调用提供详细的错误信息
4. **兼容性更好**：不依赖特定版本的 LangGraph 配置行为

## 验证

修复后测试通过：
- ✅ 代码可以正常编译
- ✅ 智能体可以正常初始化
- ✅ 工具调用可以正常执行
- ✅ 流式输出正常工作

## 相关修改

- 移除了 `ToolNode` 的导入（已注释）
- 保留了工具调用的所有功能
- 改进了错误处理机制

现在所有配置问题都已解决！✅
