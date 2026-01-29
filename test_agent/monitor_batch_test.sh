#!/bin/bash
# 监控批量测试进度

cd /public/home/rongyankai/test_agent

echo "=== 批量测试监控 ==="
echo ""

# 检查进程是否运行
if pgrep -f "batch_test_functions.py" > /dev/null; then
    echo "✅ 测试进程正在运行"
    echo ""
else
    echo "❌ 测试进程未运行"
    exit 1
fi

# 显示最新日志
echo "📝 最新日志文件:"
ls -lth log/*.log 2>/dev/null | head -3
echo ""

# 显示测试进度
echo "📊 测试进度:"
if [ -f batch_test_all.log ]; then
    current=$(grep -c "测试函数:" batch_test_all.log 2>/dev/null || echo "0")
    echo "  当前测试函数数: $current / 26"
fi
echo ""

# 显示最新摘要
echo "📋 最新测试摘要:"
latest_summary=$(ls -t batch_test_results/batch_test_summary_*.txt 2>/dev/null | head -1)
if [ -n "$latest_summary" ]; then
    tail -10 "$latest_summary"
else
    echo "  摘要文件尚未生成"
fi
