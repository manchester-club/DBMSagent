#!/bin/bash
# 快速检查批量测试进度

cd /public/home/rongyankai/test_agent

echo "=== 批量测试进度检查 ==="
echo ""

# 检查进程
if pgrep -f "batch_test_functions.py" > /dev/null; then
    echo "✅ 测试进程运行中"
    PID=$(pgrep -f "batch_test_functions.py" | head -1)
    echo "   PID: $PID"
else
    echo "❌ 测试进程未运行"
fi
echo ""

# 统计已完成的测试
completed=$(ls -1 log/*.log 2>/dev/null | wc -l)
echo "📊 已完成测试: $completed 个函数"
echo ""

# 显示最新的3个日志文件
echo "📝 最新日志文件:"
ls -lth log/*.log 2>/dev/null | head -3 | awk '{print "   " $9 " (" $5 ")"}'
echo ""

# 显示最新摘要
latest_summary=$(ls -t batch_test_results/batch_test_summary_*.txt 2>/dev/null | head -1)
if [ -n "$latest_summary" ]; then
    echo "📋 最新测试摘要:"
    tail -15 "$latest_summary" | grep -E "\[|状态|耗时|日志文件" | head -10
fi
