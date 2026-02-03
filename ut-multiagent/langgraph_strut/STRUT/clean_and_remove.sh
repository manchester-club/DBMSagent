#!/bin/bash

# ===============================
# 脚本功能：
# 1. 遍历指定路径下所有以 test_ 开头的目录
# 2. 在每个目录中执行 `make clean`
# 3. 执行完成后删除所有 test_* 目录
# ===============================

# 目标路径通过脚本参数传入
TARGET_DIR="$1"

# 判断参数是否为空
if [ -z "$TARGET_DIR" ]; then
    echo "❌ 使用方法: $0 <目标路径>"
    exit 1
fi

# 判断路径是否存在
if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ 错误: 目录不存在: $TARGET_DIR"
    exit 1
fi

echo "✅ 目标目录: $TARGET_DIR"
echo "🔍 正在查找 test_* 文件夹..."

# 遍历 test_* 目录并执行 make clean
for dir in "$TARGET_DIR"/test_*; do
    if [ -d "$dir" ]; then
        echo "🧹 执行 make clean in $dir"
        (cd "$dir" && make clean)
    fi
done

echo "🗑️  清理完成，开始删除 test_* 目录..."

# 删除所有 test_* 目录
for dir in "$TARGET_DIR"/test_*; do
    if [ -d "$dir" ]; then
        echo "❌ 删除目录: $dir"
        rm -rf "$dir"
    fi
done

echo "✅ 所有 test_* 目录已删除完毕！"