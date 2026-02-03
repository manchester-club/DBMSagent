#!/bin/bash
# 使用方法：
#   bash STRUT/help_functions/make_clean.sh src/backend/utils/adt/my_int/

# 检查输入参数
if [ -z "$1" ]; then
    echo "用法: $0 <目标目录>"
    exit 1
fi

# 转换为绝对路径
TARGET_DIR="$(cd "$1" 2>/dev/null && pwd)"
if [ ! -d "$TARGET_DIR" ]; then
    echo "错误: 目录不存在: $TARGET_DIR"
    exit 1
fi

echo "目标目录: $TARGET_DIR"

# 遍历以 test_ 开头的子目录
for dir in "$TARGET_DIR"/test_*; do
    # 跳过不存在的匹配（避免 'test_*' 没有匹配时报错）
    [ -d "$dir" ] || continue

    echo "进入目录: $dir"
    cd "$dir" || continue

    if [ -f Makefile ]; then
        echo "运行 make clean ..."
        make clean
    else
        echo "跳过: 未找到 Makefile"
    fi

    # 返回上级目录
    cd "$TARGET_DIR" || exit 1

    echo "删除目录: $dir"
    rm -rf "$dir"
done

echo "✅ 所有 test_ 开头的目录已清理完成。"