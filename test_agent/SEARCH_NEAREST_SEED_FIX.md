# Search_Nearest_Seed 工具修复

## 问题分析

从用户提供的错误信息看：
```
[Tool: Search_Nearest_Seed]  {status: "Error", error_message: "未找到距离在5层内的有效种子 SQL。 已遍历 77 个函数， 其中 0 个在 function_paths 中但未找到有效 SQL。\n目标函数有 2 个直接调用者（如: JsonEncodeDateTime, date_out），但这些调用者都没有 function_in_path 关系（未被 SQL 触发过）。\n提示：这些...
```

这个错误说明：
1. 工具没有在 `function_paths` 中找到目标函数
2. 所以它开始向上查找调用者
3. 遍历了 77 个函数，但都没有找到有效的 SQL

## 根本原因

问题可能在于：
1. **函数 ID 格式不匹配**：从 `Get_Code_Context` 返回的函数 ID 可能是 `function:EncodeSpecialDate@postgresql-17.6/src/backend/utils/adt/date.c:294`，而 `function_paths` 中的键是 `function:EncodeSpecialDate@postgresql-17.6/src/backend/utils/adt/date.c:0`
2. **规范化失败**：虽然 `normalize_func_id` 应该能处理行号不匹配的情况，但在某些边界情况下可能失败

## 修复措施

### 1. 增强函数 ID 规范化逻辑

在 `Search_Nearest_Seed` 工具中，如果 `normalize_func_id` 失败，尝试从 `function_paths` 中查找相似的键：

```python
# 如果规范化失败，但 function_paths 中有相似的键，尝试使用相似的键
if not normalized_func_id:
    # 尝试从 function_paths 中查找相似的键
    func_name_match = re.search(r'function:([^@]+)@([^:]+)', target_func_id)
    if func_name_match:
        func_name = func_name_match.group(1)
        file_path = func_name_match.group(2)
        # 在 function_paths 中查找匹配的键
        for key in function_paths.keys():
            if (key.startswith(f"function:{func_name}@") and 
                file_path in key):
                normalized_func_id = key
                break
```

### 2. 添加调试日志

在 `bfs_find_nearest_seed` 函数中添加详细的调试日志，帮助诊断问题：

```python
print(f"[bfs_find_nearest_seed] 目标函数: {target_func_id}", flush=True)
print(f"[bfs_find_nearest_seed] function_paths 中有 {len(function_paths)} 个函数", flush=True)
print(f"[bfs_find_nearest_seed] 目标函数在 function_paths 中: {in_paths}", flush=True)
```

## 验证

修复后，工具应该能够：
1. ✅ 正确处理不同格式的函数 ID（带行号或不带行号）
2. ✅ 在 `function_paths` 中正确找到目标函数
3. ✅ 返回有效的 SQL 种子，而不是错误信息

## 测试建议

1. 使用不同的函数 ID 格式测试工具
2. 检查调试日志，确认函数 ID 是否正确规范化
3. 验证工具能否正确找到 SQL 种子
