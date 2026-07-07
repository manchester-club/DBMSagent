# Search_Nearest_Seed 调试说明

## 问题现象

从执行日志（858-1024行）看到：
```
[bfs_find_nearest_seed] function_paths 中有 0 个函数
[bfs_find_nearest_seed] 目标函数在 function_paths 中: False
```

但是直接测试时，`function_paths` 有 10112 个函数，且包含 `EncodeSpecialDate`。

## 可能的原因

1. **模块导入问题**：不同模块实例的全局变量可能不共享
2. **初始化检查不完整**：只检查了 `_reverse_call_graph`，没有检查 `_function_paths` 和 `_path_sqls`
3. **缓存被意外清空**：某些操作可能清空了缓存

## 修复措施

### 1. 改进初始化检查

**之前：**
```python
if _reverse_call_graph is None:
    # 初始化所有三个字典
```

**修复后：**
```python
# 检查是否需要初始化（任何一个为 None 都需要初始化）
if _reverse_call_graph is None or _function_paths is None or _path_sqls is None:
    # 初始化所有三个字典
```

### 2. 添加防御性检查

在返回前确保返回值不是 None：
```python
# 确保返回值不是 None（防御性编程）
if _reverse_call_graph is None:
    _reverse_call_graph = {}
if _function_paths is None:
    _function_paths = {}
if _path_sqls is None:
    _path_sqls = {}
```

### 3. 添加详细调试日志

在 `get_seed_indices()` 和 `Search_Nearest_Seed` 中添加调试日志：
- 初始化时打印加载的边数和各字典大小
- 使用缓存时打印缓存大小
- 在 `Search_Nearest_Seed` 中打印传入的参数

## 验证

修复后，重新运行应该能看到：
1. `[get_seed_indices]` 的初始化日志
2. `[Search_Nearest_Seed]` 的参数检查日志
3. `[bfs_find_nearest_seed]` 应该显示正确的 `function_paths` 大小

如果问题仍然存在，调试日志会帮助我们定位问题所在。
