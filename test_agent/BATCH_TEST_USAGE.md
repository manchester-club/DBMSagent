# 批量测试函数脚本使用说明

## 脚本功能

`batch_test_functions.py` 用于批量测试待测函数集合中的函数，自动为每个函数生成测试用例并执行。

## 使用方法

### 1. 基本用法

测试所有函数：
```bash
cd /public/home/rongyankai/test_agent
python3 batch_test_functions.py
```

### 2. 测试指定范围的函数

从第 0 个函数开始，测试前 5 个函数：
```bash
python3 batch_test_functions.py --start-index 0 --end-index 5
```

从第 10 个函数开始，测试到第 20 个函数：
```bash
python3 batch_test_functions.py --start-index 10 --end-index 20
```

### 3. 跳过零覆盖率函数

只测试覆盖率大于 0% 的函数：
```bash
python3 batch_test_functions.py --skip-zero
```

### 4. 指定输出目录

将结果保存到指定目录：
```bash
python3 batch_test_functions.py --output-dir my_results
```

### 5. 组合使用

测试前 10 个非零覆盖率函数：
```bash
python3 batch_test_functions.py --start-index 0 --end-index 10 --skip-zero
```

## 参数说明

- `--start-index N`: 从第 N 个函数开始测试（从0开始）
- `--end-index M`: 测试到第 M 个函数（不包含）
- `--skip-zero`: 跳过零覆盖率函数
- `--functions-file PATH`: 待测函数集合文件路径（默认：`待测函数集合.md`）
- `--output-dir DIR`: 结果输出目录（默认：`batch_test_results`）

## 输出说明

### 控制台输出

脚本运行时会实时显示：
- 当前测试的函数名称
- 初始覆盖率
- 测试进度
- 测试状态（成功/失败/中断）

### 结果文件

测试结果会保存到 `batch_test_results/` 目录下：
- `batch_test_summary_YYYYMMDD_HHMMSS.txt`: 包含所有测试的摘要信息

## 示例

### 示例 1: 测试前 3 个函数

```bash
python3 batch_test_functions.py --start-index 0 --end-index 3
```

输出示例：
```
================================================================================
批量测试函数
================================================================================
总函数数: 26
测试范围: 0 - 3 (共 3 个函数)
跳过零覆盖率: False
================================================================================

[1/3] 测试函数: overlaps_timetz
  初始覆盖率: 0.00%
  未覆盖行数: 48/48
  开始时间: 2026-01-27 13:30:00
--------------------------------------------------------------------------------
  ✅ 测试完成 (耗时: 45.23秒)

[2/3] 测试函数: timetz_smaller
  ...
```

### 示例 2: 只测试非零覆盖率函数

```bash
python3 batch_test_functions.py --skip-zero
```

这将跳过所有 0% 覆盖率的函数，只测试覆盖率大于 0% 的函数。

### 示例 3: 分批次测试

由于测试可能需要较长时间，可以分批次运行：

```bash
# 第一批：测试前 5 个函数
python3 batch_test_functions.py --start-index 0 --end-index 5

# 第二批：测试第 5-10 个函数
python3 batch_test_functions.py --start-index 5 --end-index 10

# 第三批：测试剩余函数
python3 batch_test_functions.py --start-index 10
```

## 注意事项

1. **测试时间**: 每个函数的测试可能需要几分钟到十几分钟，请合理安排时间
2. **日志文件**: 每个函数的测试过程会生成独立的日志文件，保存在 `test_agent/log/` 目录下
3. **中断恢复**: 如果测试被中断，可以使用 `--start-index` 参数从上次中断的位置继续
4. **资源占用**: 批量测试会占用较多系统资源，建议在系统负载较低时运行

## 故障排除

### 问题 1: 找不到函数列表文件

**错误**: `错误: 找不到文件 待测函数集合.md`

**解决**: 确保 `待测函数集合.md` 文件在 `test_agent` 目录下，或使用 `--functions-file` 参数指定正确路径。

### 问题 2: 导入错误

**错误**: `ModuleNotFoundError: No module named 'coverage_multi_agent'`

**解决**: 确保在 `test_agent` 目录下运行脚本，脚本会自动添加 `langgraph` 目录到 Python 路径。

### 问题 3: 测试超时

如果某个函数测试时间过长，可以：
1. 使用 `Ctrl+C` 中断当前测试
2. 使用 `--start-index` 跳过该函数，继续测试其他函数

## 后续处理

测试完成后，可以：
1. 查看 `batch_test_results/` 目录下的摘要文件
2. 查看 `log/` 目录下每个函数的详细日志
3. 根据测试结果，针对性地优化测试用例
