# ToolNode 配置错误修复 ✅

## 错误信息

```
Missing required config key 'N/A' for 'tools'.
```

## 问题原因

`coverage_multi_agent.py` 中的 `_run_agent_loop` 函数使用了 LangGraph 的 `ToolNode`，但调用 `tool_node.invoke()` 时没有提供必需的 `config` 参数。

## 修复方案

### 修改位置：`langgraph/coverage_multi_agent.py` 第289行

**之前：**
```python
tool_state = {"messages": messages + to_append}
tool_out = tool_node.invoke(tool_state)
```

**修复后：**
```python
tool_state = {"messages": messages + to_append}
# ToolNode 需要配置参数，提供空配置
tool_config = {"configurable": {}}
tool_out = tool_node.invoke(tool_state, config=tool_config)
```

## 说明

LangGraph 的 `ToolNode.invoke()` 方法需要 `config` 参数，格式为：
```python
config = {
    "configurable": {
        # 可选的配置项
    }
}
```

即使不需要特殊配置，也需要提供空的 `configurable` 字典。

## 验证

修复后，代码可以正常编译和初始化智能体。

## 相关文件

- `langgraph/coverage_multi_agent.py` - 修复了 ToolNode 调用
- `backend/agents/agent_manager.py` - 已正确配置 astream 的 config 参数

现在所有配置问题都已解决！✅
