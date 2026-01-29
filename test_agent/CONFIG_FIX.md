# 配置错误修复 ✅

## 错误信息

```
Missing required config key 'N/A' for 'tools'.
```

## 问题原因

LangGraph 在执行 `astream` 时需要提供配置参数，即使工具节点是自定义的。如果不提供配置或配置格式不正确，会出现此错误。

## 修复方案

### 修改位置：`backend/agents/agent_manager.py`

**之前（第93行）：**
```python
async for chunk in self.app.astream(initial_state):  # type: ignore[attr-defined]
```

**修复后：**
```python
# 使用空配置，因为工具节点是自定义的，不需要额外配置
config = {"configurable": {}}
async for chunk in self.app.astream(initial_state, config=config):  # type: ignore[attr-defined]
```

## 配置说明

LangGraph 的 `astream` 方法需要 `config` 参数，格式为：
```python
config = {
    "configurable": {
        # 可选的配置项
        "thread_id": "thread_123",  # 用于多轮对话
        # 其他配置...
    }
}
```

即使不需要特殊配置，也需要提供空的 `configurable` 字典：
```python
config = {"configurable": {}}
```

## 验证

修复后，代码可以正常初始化智能体并执行流式输出。

## 注意事项

1. **ollama_agent_with_tools**：使用自定义工具节点，只需要空配置
2. **coverage_multi_agent**：使用 LangGraph 的检查点功能，需要提供 `thread_id`

两个智能体现在都正确配置了。
