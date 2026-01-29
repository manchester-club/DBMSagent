# 循环检测逻辑修复

## 问题分析

从执行日志（133-258行）发现以下问题：

### 1. Code Explorer 被误判为连续调用 3 次

**问题现象：**
```
[Supervisor] ⚠️ 检测到 code_explorer 连续调用 3 次，结束流程避免无限循环
```

**根本原因：**
- Code Explorer 在一次派发中调用了多个工具：
  1. `Get_Code_Context`（成功）
  2. `Traverse_Call_Graph`（第一次失败，函数ID格式不对）
  3. `Traverse_Call_Graph`（第二次成功）
- 循环检测逻辑基于工具调用次数，而不是 Agent 派发次数
- 因此，3 个工具调用被误判为 3 次 Agent 派发

### 2. 流程提前结束

**问题现象：**
- Code Explorer 完成后，应该派发到 Coverage Analyzer
- 但是因为误判为循环，流程提前结束
- 用户要求的 `Collect_Coverage` 和 `Search_Nearest_Seed` 都没有执行

## 修复措施

### 1. 添加 Agent 派发历史记录

在 `State` 中添加 `agent_history` 字段，记录 Agent 的派发历史：

```python
class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    next_agent: Route
    agent_history: Annotated[List[str], lambda x, y: y]  # 记录 Agent 派发历史
```

### 2. 改进循环检测逻辑

**之前的问题：**
- 基于工具调用次数判断循环
- 一个 Agent 调用多个工具会被误判为多次派发

**修复后：**
- 基于 Agent 派发历史判断循环
- 只有当同一个 Agent 连续派发 3 次时才判定为循环
- 一个 Agent 调用多个工具不会影响判断

```python
def supervisor_node(state: State) -> dict:
    # 检查最近的 Agent 派发历史（使用 State 中的 agent_history，更准确）
    agent_history = state.get("agent_history", [])
    
    # 检查是否达到循环限制（同一个 Agent 连续派发 3 次以上）
    if len(agent_history) >= 3:
        last_three = agent_history[-3:]
        if last_three[0] == last_three[1] == last_three[2]:
            print(f"\n[Supervisor] ⚠️ 检测到 {last_three[0]} 连续派发 3 次，结束流程避免无限循环", flush=True)
            route = "__end__"
            return {"next_agent": route, "agent_history": agent_history}
    
    # ... 路由逻辑 ...
    
    # 更新 Agent 派发历史
    agent_history = state.get("agent_history", [])
    if route != "__end__":
        agent_history = agent_history + [route]
        # 只保留最近 10 次派发记录
        agent_history = agent_history[-10:]
    return {"next_agent": route, "agent_history": agent_history}
```

### 3. 初始化 agent_history

在创建初始状态时，添加 `agent_history` 字段：

```python
initial: State = {
    "messages": [HumanMessage(content=user_input)],
    "next_agent": "__end__",
    "agent_history": [],
}
```

## 修复效果

修复后应该能够：
1. ✅ 正确区分 Agent 派发次数和工具调用次数
2. ✅ 一个 Agent 调用多个工具不会被误判为循环
3. ✅ 只有当同一个 Agent 连续派发 3 次时才判定为循环
4. ✅ 流程能够正常继续，不会提前结束

## 测试建议

1. 测试 Code Explorer 调用多个工具的情况
2. 测试 Coverage Analyzer 调用多个工具的情况
3. 测试真正的循环情况（同一个 Agent 连续派发 3 次）
4. 验证流程能够正常完成所有步骤
