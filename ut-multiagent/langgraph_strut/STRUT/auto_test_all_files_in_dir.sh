#!/bin/bash

# 批量处理目录下所有C文件的自动化测试生成和优化脚本
# 使用方法（在 /usr/src/postgresql 目录下运行）:
#   bash STRUT/auto_test_all_files_in_dir.sh src/backend/utils/adt/
#   bash STRUT/auto_test_all_files_in_dir.sh src/backend/utils/adt/ 3
#   bash STRUT/auto_test_all_files_in_dir.sh src/backend/utils/adt/ 3 --exclude int.c,float.c

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_section() {
    echo -e "${CYAN}[SECTION]${NC} $1"
}

# 获取脚本所在目录（STRUT目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ==================== 目录级别实时状态跟踪功能 ====================

# 全局状态文件路径
DIR_PROGRESS_FILE=""

# 初始化目录进度文件
init_dir_progress_file() {
    local target_dir="$1"
    local max_rounds="$2"
    local exclude_files="$3"

    # 状态文件保存在目标目录下
    mkdir -p "$target_dir" 2>/dev/null || true

    DIR_PROGRESS_FILE="$target_dir/dir_test_progress.txt"

    # 创建初始状态文件
    cat > "$DIR_PROGRESS_FILE" << 'EOF'
################################################################################
#                     目录级别单元测试生成进度实时追踪
################################################################################
# 目录: {{TARGET_DIR}}
# 开始时间: {{START_TIME}}
# 最大优化轮次: {{MAX_ROUNDS}}
# 排除文件: {{EXCLUDE_FILES}}
# 状态: 运行中...
#
# 查看实时进度:
#   watch -n 1 cat {{DIR_PROGRESS_FILE}}
#   tail -f {{DIR_PROGRESS_FILE}}
#
################################################################################

EOF

    # 替换占位符
    sed -i "s|{{TARGET_DIR}}|$target_dir|g" "$DIR_PROGRESS_FILE" 2>/dev/null || \
        sed -i '' "s|{{TARGET_DIR}}|$target_dir|g" "$DIR_PROGRESS_FILE"

    sed -i "s|{{START_TIME}}|$(date '+%Y-%m-%d %H:%M:%S')|g" "$DIR_PROGRESS_FILE" 2>/dev/null || \
        sed -i '' "s|{{START_TIME}}|$(date '+%Y-%m-%d %H:%M:%S')|g" "$DIR_PROGRESS_FILE"

    sed -i "s|{{MAX_ROUNDS}}|$max_rounds|g" "$DIR_PROGRESS_FILE" 2>/dev/null || \
        sed -i '' "s|{{MAX_ROUNDS}}|$max_rounds|g" "$DIR_PROGRESS_FILE"

    sed -i "s|{{EXCLUDE_FILES}}|$exclude_files|g" "$DIR_PROGRESS_FILE" 2>/dev/null || \
        sed -i '' "s|{{EXCLUDE_FILES}}|$exclude_files|g" "$DIR_PROGRESS_FILE"

    sed -i "s|{{DIR_PROGRESS_FILE}}|$DIR_PROGRESS_FILE|g" "$DIR_PROGRESS_FILE" 2>/dev/null || \
        sed -i '' "s|{{DIR_PROGRESS_FILE}}|$DIR_PROGRESS_FILE|g" "$DIR_PROGRESS_FILE"

    log_info "📊 目录级别实时进度文件: $DIR_PROGRESS_FILE"
    log_info "💡 查看实时进度: watch -n 1 cat $DIR_PROGRESS_FILE"
}

# 更新目录进度统计
update_dir_progress_stats() {
    local total_files=$1
    local current_file=$2
    local success_files=$3
    local failed_files=$4
    local skipped_files=$5
    local total_functions=$6
    local processed_functions=$7

    if [ -z "$DIR_PROGRESS_FILE" ]; then
        return
    fi

    local file_percent=$((current_file * 100 / total_files))
    local running_files=$((current_file - success_files - failed_files - skipped_files))

    # 在文件末尾更新统计信息
    cat >> "$DIR_PROGRESS_FILE" << EOF

================================================================================
目录进度统计 (更新时间: $(date '+%H:%M:%S'))
================================================================================
总C文件数: $total_files
已处理文件: $current_file / $total_files ($file_percent%)
✓ 成功文件: $success_files
✗ 失败文件: $failed_files
⊗ 跳过文件: $skipped_files
▶ 运行中文件: $running_files

总函数数: $total_functions (已处理: $processed_functions)
文件进度条: $(printf '█%.0s' $(seq 1 $((file_percent/5))))$(printf '░%.0s' $(seq 1 $((20-file_percent/5)))) $file_percent%
================================================================================

EOF
}

# 记录C文件状态
log_file_status() {
    local c_file="$1"
    local status="$2"  # 开始/成功/失败/跳过
    local message="$3"

    if [ -z "$DIR_PROGRESS_FILE" ]; then
        return
    fi

    local timestamp=$(date '+%H:%M:%S')
    local status_icon=""
    local status_color=""

    case "$status" in
        "开始")
            status_icon="▶"
            status_color="RUNNING"
            ;;
        "成功")
            status_icon="✓"
            status_color="SUCCESS"
            ;;
        "失败")
            status_icon="✗"
            status_color="FAILED"
            ;;
        "跳过")
            status_icon="⊗"
            status_color="SKIPPED"
            ;;
    esac

    cat >> "$DIR_PROGRESS_FILE" << EOF
[$timestamp] $status_icon $(basename "$c_file") - $status_color
    详情: $message
EOF
}

# 完成目录进度文件
finalize_dir_progress_file() {
    local total_files=$1
    local success_files=$2
    local failed_files=$3
    local skipped_files=$4
    local total_functions=$5

    if [ -z "$DIR_PROGRESS_FILE" ]; then
        return
    fi

    local end_time=$(date '+%Y-%m-%d %H:%M:%S')

    cat >> "$DIR_PROGRESS_FILE" << EOF

################################################################################
#                         目录测试完成总结
################################################################################
结束时间: $end_time

最终统计:
  总C文件数: $total_files
  ✓ 成功文件: $success_files
  ✗ 失败文件: $failed_files
  ⊗ 跳过文件: $skipped_files
  总函数数: $total_functions

状态: 已完成
################################################################################
EOF

    log_info "📊 目录最终进度报告已保存: $DIR_PROGRESS_FILE"
}

# 检查是否为root用户
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "此脚本需要root权限运行"
        log_info "请使用: sudo $0 $@"
        exit 1
    fi
}

# 获取目录中所有C文件的列表
get_all_c_files() {
    local target_dir="$1"
    local exclude_pattern="$2"

    log_info "扫描目录中的C文件: $target_dir"

    # 查找所有 .c 文件
    local all_c_files=$(find "$target_dir" -name "*.c" -type f | sort)

    if [ -z "$all_c_files" ]; then
        log_error "在目录 $target_dir 中未找到任何 .c 文件"
        exit 1
    fi

    # 如果有排除模式，过滤文件
    local filtered_files=""
    if [ -n "$exclude_pattern" ]; then
        log_info "应用排除模式: $exclude_pattern"

        # 将排除模式转换为 find 命令的格式
        # 例如: "int.c,float.c" -> -name "int.c" -o -name "float.c"
        local find_exclude=""
        IFS=',' read -ra EXCLUDE_ARRAY <<< "$exclude_pattern"
        for exclude_file in "${EXCLUDE_ARRAY[@]}"; do
            exclude_file=$(echo "$exclude_file" | xargs)  # 去除空白字符
            if [ -n "$find_exclude" ]; then
                find_exclude="$find_exclude -o -name \"$exclude_file\""
            else
                find_exclude="-name \"$exclude_file\""
            fi
        done

        if [ -n "$find_exclude" ]; then
            # 使用 find 命令过滤排除的文件
            filtered_files=$(eval "find \"$target_dir\" -name \"*.c\" -type f $find_exclude -prune -o -name \"*.c\" -type f -print | sort")
        else
            filtered_files="$all_c_files"
        fi
    else
        filtered_files="$all_c_files"
    fi

    # 输出过滤后的文件列表
    echo "$filtered_files"
}

# 计算目录中所有函数的总数
count_total_functions() {
    local c_files="$1"
    local total_functions=0

    while IFS= read -r c_file; do
        if [ -n "$c_file" ]; then
            # 使用现有的函数获取单个文件的函数数量
            local temp_func_list=$(mktemp)
            cd "$SCRIPT_DIR"

            # 调用 get_all_functions 函数，但只统计数量
            if python3 - <<EOF > "$temp_func_list" 2>/dev/null
import sys
import os
import clang.cindex

sys.path.insert(0, "$SCRIPT_DIR")

from pg_clang_helper import get_pg_compiler_args

clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')

c_file = "$c_file"
pg_src_path = "/usr/src/postgresql"

index = clang.cindex.Index.create()
compiler_args = get_pg_compiler_args(c_file, pg_src_path)

try:
    tu = index.parse(c_file, args=compiler_args)
except Exception as e:
    print(f"ERROR: 解析文件失败: {e}", file=sys.stderr)
    sys.exit(1)

functions = []
for node in tu.cursor.get_children():
    if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.is_definition():
        if node.location.file and node.location.file.name == c_file:
            functions.append(node.spelling)

for func in functions:
    print(func)
EOF
            then
                local func_count=$(wc -l < "$temp_func_list")
                total_functions=$((total_functions + func_count))
                log_info "📊 $(basename "$c_file"): $func_count 个函数"
            else
                log_warning "⚠️ 无法统计 $(basename "$c_file") 的函数数量"
            fi

            rm -f "$temp_func_list"
            cd - > /dev/null
        fi
    done <<< "$c_files"

    echo $total_functions
}

# 主函数
main() {
    local target_dir="$1"
    local max_rounds="${2:-3}"
    shift 2

    # 解析排除参数
    local exclude_files=""
    while [[ $# -gt 0 ]]; do
        case $1 in
            --exclude)
                exclude_files="$2"
                shift 2
                ;;
            *)
                log_error "未知参数: $1"
                log_info "使用方法: $0 <目录路径> [最大优化轮次] [--exclude 文件列表]"
                log_info "例如: $0 src/backend/utils/adt/ 3 --exclude int.c,float.c"
                exit 1
                ;;
        esac
    done

    # 检查前置条件
    check_root

    if [ -z "$target_dir" ]; then
        log_error "使用方法: $0 <目录路径> [最大优化轮次] [--exclude 文件列表]"
        log_info "例如: $0 src/backend/utils/adt/ 3 --exclude int.c,float.c"
        exit 1
    fi

    if [ ! -d "$target_dir" ]; then
        log_error "目录不存在: $target_dir"
        exit 1
    fi

    # 获取绝对路径
    target_dir=$(readlink -f "$target_dir")

    # 保存原始工作目录（通常是 /usr/src/postgresql）
    local original_dir=$(pwd)

    log_info "=== 目录级别C文件批量测试生成系统 ==="
    log_info "STRUT工具目录: $SCRIPT_DIR"
    log_info "原始工作目录: $original_dir"
    log_info "目标目录: $target_dir"
    log_info "每个函数最大优化轮次: $max_rounds"
    if [ -n "$exclude_files" ]; then
        log_info "排除的文件: $exclude_files"
    fi
    log_info "=============================================="

    # 获取所有C文件列表
    log_section "步骤1: 扫描目录中的所有C文件"
    local c_files=$(get_all_c_files "$target_dir" "$exclude_files")

    if [ -z "$c_files" ]; then
        log_error "没有找到符合条件的C文件"
        exit 1
    fi

    # 计算文件数量
    local file_count=$(echo "$c_files" | wc -l)

    log_success "发现 $file_count 个C文件:"
    local i=1
    while IFS= read -r c_file; do
        if [ -n "$c_file" ]; then
            echo "   $i. $(basename "$c_file") ($c_file)"
            i=$((i + 1))
        fi
    done <<< "$c_files"

    # 统计总函数数
    log_section "步骤2: 统计所有函数数量"
    log_info "正在统计目录中所有函数的数量..."
    local total_functions=$(count_total_functions "$c_files")
    log_success "目录总计: $total_functions 个函数"

    # 批量处理每个C文件
    log_section "步骤3: 批量处理所有C文件"

    local success_files=0
    local failed_files=0
    local skipped_files=0
    local processed_functions=0
    declare -a failed_c_files
    declare -a skipped_c_files

    # 初始化目录进度跟踪
    init_dir_progress_file "$target_dir" "$max_rounds" "$exclude_files"

    local current_file=0
    while IFS= read -r c_file; do
        if [ -n "$c_file" ]; then
            current_file=$((current_file + 1))

            echo ""
            echo "##################################################################"
            echo "#  文件处理进度: $current_file/$file_count"
            echo "#  当前文件: $(basename "$c_file")"
            echo "#  文件路径: $c_file"
            echo "##################################################################"
            echo ""

            # 更新进度统计
            update_dir_progress_stats "$file_count" "$current_file" "$success_files" "$failed_files" "$skipped_files" "$total_functions" "$processed_functions"

            # 记录文件开始状态
            log_file_status "$c_file" "开始" "开始处理文件中的所有函数"

            # 检查是否已存在测试目录且所有函数都已处理
            local c_basename=$(basename "$c_file" .c)
            local c_dir=$(dirname "$c_file")
            local test_base_dir="$c_dir/my_$c_basename"

            if [ -d "$test_base_dir" ]; then
                log_info "检测到已存在的测试目录: $test_base_dir"

                # 获取该文件的实际函数列表
                local temp_func_list=$(mktemp)
                cd "$SCRIPT_DIR"

                # 获取函数列表
                if python3 - <<EOF > "$temp_func_list" 2>/dev/null
import sys
import os
import clang.cindex

sys.path.insert(0, "$SCRIPT_DIR")

from pg_clang_helper import get_pg_compiler_args

clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')

c_file = "$c_file"
pg_src_path = "/usr/src/postgresql"

index = clang.cindex.Index.create()
compiler_args = get_pg_compiler_args(c_file, pg_src_path)

try:
    tu = index.parse(c_file, args=compiler_args)
except Exception as e:
    print(f"ERROR: 解析文件失败: {e}", file=sys.stderr)
    sys.exit(1)

functions = []
for node in tu.cursor.get_children():
    if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.is_definition():
        if node.location.file and node.location.file.name == c_file:
            functions.append(node.spelling)

for func in functions:
    print(func)
EOF
                then
                    # 读取函数列表
                    local file_functions=()
                    while IFS= read -r func_name; do
                        if [ -n "$func_name" ]; then
                            file_functions+=("$func_name")
                        fi
                    done < "$temp_func_list"

                    rm -f "$temp_func_list"
                    cd - > /dev/null

                    local total_funcs=${#file_functions[@]}
                    local valid_suites=0

                    log_info "文件 $(basename "$c_file") 包含 $total_funcs 个函数，开始验证测试套件..."

                    # 验证每个函数的测试套件
                    for func in "${file_functions[@]}"; do
                        local suite_dir="$test_base_dir/test_${func}_suite"

                        if [ -d "$suite_dir" ] && [ -f "$suite_dir/Makefile" ]; then
                            # 检查是否有覆盖率文件
                            local gcov_file=$(find "$suite_dir" -maxdepth 1 -name "*.c.gcov" -type f | head -n 1)

                            if [ -n "$gcov_file" ]; then
                                valid_suites=$((valid_suites + 1))
                                log_info "✓ 函数 $func 的测试套件有效（有覆盖率文件）"
                            else
                                log_warning "⚠️ 函数 $func 的测试套件缺少覆盖率文件"
                            fi
                        else
                            log_warning "⚠️ 函数 $func 缺少测试套件目录: $suite_dir"
                        fi
                    done

                    # 如果所有函数都有有效的测试套件，则跳过整个文件
                    if [ $valid_suites -eq $total_funcs ]; then
                        log_success "✅ 文件 $(basename "$c_file") 的所有 $total_funcs 个函数测试套件都有效，跳过"
                        skipped_files=$((skipped_files + 1))
                        skipped_c_files+=("$c_file")
                        log_file_status "$c_file" "跳过" "所有函数测试套件都有效 ($valid_suites/$total_funcs)"
                        continue
                    else
                        log_warning "⚠️ 文件 $(basename "$c_file") 只有 $valid_suites/$total_funcs 个有效测试套件，需要重新处理"
                        # 继续执行 auto_test_all_functions.sh，它会智能处理已存在的套件
                    fi
                else
                    log_warning "⚠️ 无法获取 $(basename "$c_file") 的函数列表，继续处理"
                    rm -f "$temp_func_list"
                    cd - > /dev/null
                fi
            fi

            # 调用现有的 auto_test_all_functions.sh 处理单个C文件
            log_info "调用 auto_test_all_functions.sh 处理文件: $c_file"

            if bash "$SCRIPT_DIR/auto_test_all_functions.sh" "$c_file" "$max_rounds"; then
                log_success "✅ 文件 $(basename "$c_file") 处理成功"
                success_files=$((success_files + 1))

                # 获取该文件的函数数量并累加
                local file_functions=$(count_total_functions "$c_file")
                processed_functions=$((processed_functions + file_functions))

                log_file_status "$c_file" "成功" "所有函数测试生成成功"
            else
                log_error "❌ 文件 $(basename "$c_file") 处理失败"
                failed_files=$((failed_files + 1))
                failed_c_files+=("$c_file")

                log_file_status "$c_file" "失败" "部分或全部函数测试生成失败"
            fi

            echo ""
            echo "-------------------------------------------------------------------"
            echo "  文件进度: $current_file/$file_count  成功: $success_files  失败: $failed_files  跳过: $skipped_files"
            echo "-------------------------------------------------------------------"
        fi
    done <<< "$c_files"

    # 完成目录进度文件
    finalize_dir_progress_file "$file_count" "$success_files" "$failed_files" "$skipped_files" "$total_functions"

    # 输出最终统计
    echo ""
    echo "##################################################################"
    echo "#  🎉 目录批量处理完成！"
    echo "##################################################################"
    echo ""
    log_info "总计: $file_count 个C文件，$total_functions 个函数"
    log_success "✅ 成功文件: $success_files 个"
    log_error "❌ 失败文件: $failed_files 个"
    log_warning "⏭️  跳过文件: $skipped_files 个（已存在测试目录）"

    if [ $skipped_files -gt 0 ]; then
        echo ""
        log_warning "跳过的文件列表（已存在测试目录）:"
        for c_file in "${skipped_c_files[@]}"; do
            echo "   - $(basename "$c_file") ($c_file)"
        done
    fi

    if [ $failed_files -gt 0 ]; then
        echo ""
        log_error "失败的文件列表:"
        for c_file in "${failed_c_files[@]}"; do
            echo "   - $(basename "$c_file") ($c_file)"
        done
    fi

    echo ""
    log_info "所有测试套件已生成到各自的 my_* 目录下"
    echo ""
    log_info "📊 目录级别进度文件: $DIR_PROGRESS_FILE"
    log_info "下一步操作:"
    echo "   1. 查看目录进度报告: cat $DIR_PROGRESS_FILE"
    echo "   2. 查看每个文件的 my_*/test_progress.txt"
    echo "   3. 检查失败文件的错误日志"

    # 返回状态码
    if [ $failed_files -gt 0 ]; then
        exit 1
    else
        exit 0
    fi
}

# 脚本入口
main "$@"
