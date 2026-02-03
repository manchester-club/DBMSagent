# auto_test_all_functions.sh

#!/bin/bash

# 批量处理C文件中所有函数的自动化测试生成和优化脚本
# 使用方法（在 /usr/src/postgresql 目录下运行）:
#   bash STRUT/auto_test_all_functions.sh src/backend/utils/adt/int.c
#   bash STRUT/auto_test_all_functions.sh src/backend/utils/adt/int.c 3

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

# ==================== 中断处理和统计功能 ====================

# 中断处理函数
handle_interrupt() {
    echo ""
    log_warning "⚠️  检测到中断信号，正在计算当前统计信息..."
    calculate_and_display_current_stats
    log_info "📊 统计信息已保存到进度文件中"
    exit 1
}

# 计算并显示当前统计信息
calculate_and_display_current_stats() {
    if [ -z "$PROGRESS_FILE" ]; then
        return
    fi

    # 计算当前统计信息
    local current_total_duration=$(( $(date +%s) - total_start_time ))
    local current_avg_function_time=0
    if [ $processed_functions_count -gt 0 ]; then
        current_avg_function_time=$((total_function_time / processed_functions_count))
    fi

    local current_effective_time=$((total_function_time - total_db_error_time))

    echo ""
    echo "##################################################################"
    echo "#  ⏸️  程序中断 - 当前统计信息"
    echo "##################################################################"
    echo ""
    log_info "⏱️  当前性能统计 (已处理 $processed_functions_count 个函数):"
    log_info "   当前总耗时: ${current_total_duration}秒"
    log_info "   函数总耗时: ${total_function_time}秒"
    log_info "   数据库错误等待时间: ${total_db_error_time}秒"
    log_info "   有效处理时间: ${current_effective_time}秒"
    log_info "   平均函数耗时: ${current_avg_function_time}秒/函数"
    echo ""
    log_info "📊 进度概览:"
    log_info "   成功: $success_count 个函数"
    log_info "   失败: $failed_count 个函数"
    log_info "   跳过: $skipped_count 个函数"

    # 将统计信息写入进度文件
    cat >> "$PROGRESS_FILE" << EOF

================================================================================
程序中断统计信息 (中断时间: $(date '+%H:%M:%S'))
================================================================================
已处理函数数: $processed_functions_count
当前总耗时: ${current_total_duration}秒
函数总耗时: ${total_function_time}秒
数据库错误等待时间: ${total_db_error_time}秒
有效处理时间: ${current_effective_time}秒
平均函数耗时: ${current_avg_function_time}秒/函数

进度概览:
  ✓ 成功: $success_count
  ✗ 失败: $failed_count
  ⊗ 跳过: $skipped_count

================================================================================
EOF

    log_info "📈 统计信息已记录到: $PROGRESS_FILE"
}

# ==================== 实时状态跟踪功能 ====================

# 全局状态文件路径
PROGRESS_FILE=""

# 初始化状态文件
init_progress_file() {
    local c_file="$1"
    local c_dir=$(dirname "$c_file")
    local c_basename=$(basename "$c_file" .c)
    
    # 状态文件保存在 my_XXX 目录下
    local status_dir="$c_dir/my_$c_basename"
    mkdir -p "$status_dir" 2>/dev/null || true
    
    PROGRESS_FILE="$status_dir/test_progress.txt"
    
    # 创建初始状态文件
    cat > "$PROGRESS_FILE" << 'EOF'
################################################################################
#                     单元测试生成进度实时追踪
################################################################################
# 文件: {{C_FILE}}
# 开始时间: {{START_TIME}}
# 状态: 运行中...
#
# 查看实时进度:
#   watch -n 1 cat {{PROGRESS_FILE}}
#   tail -f {{PROGRESS_FILE}}
#
################################################################################

EOF
    
    # 替换占位符
    sed -i "s|{{C_FILE}}|$c_file|g" "$PROGRESS_FILE" 2>/dev/null || \
        sed -i '' "s|{{C_FILE}}|$c_file|g" "$PROGRESS_FILE"
    
    sed -i "s|{{START_TIME}}|$(date '+%Y-%m-%d %H:%M:%S')|g" "$PROGRESS_FILE" 2>/dev/null || \
        sed -i '' "s|{{START_TIME}}|$(date '+%Y-%m-%d %H:%M:%S')|g" "$PROGRESS_FILE"
    
    sed -i "s|{{PROGRESS_FILE}}|$PROGRESS_FILE|g" "$PROGRESS_FILE" 2>/dev/null || \
        sed -i '' "s|{{PROGRESS_FILE}}|$PROGRESS_FILE|g" "$PROGRESS_FILE"
    
    log_info "📊 实时进度文件: $PROGRESS_FILE"
    log_info "💡 查看实时进度: watch -n 1 cat $PROGRESS_FILE"
}

# 更新进度统计
update_progress_stats() {
    local total=$1
    local current=$2
    local success=$3
    local failed=$4
    local skipped=$5
    
    if [ -z "$PROGRESS_FILE" ]; then
        return
    fi
    
    local percent=$((current * 100 / total))
    local running=$((current - success - failed - skipped))
    
    # 在文件末尾更新统计信息
    cat >> "$PROGRESS_FILE" << EOF

================================================================================
进度统计 (更新时间: $(date '+%H:%M:%S'))
================================================================================
总函数数: $total
已处理: $current / $total ($percent%)
✓ 成功: $success
✗ 失败: $failed
⊗ 跳过: $skipped
▶ 运行中: $running

进度条: $(printf '█%.0s' $(seq 1 $((percent/5))))$(printf '░%.0s' $(seq 1 $((20-percent/5)))) $percent%
================================================================================

EOF
}

# 检查覆盖率是否达到100%
check_coverage_100() {
    local suite_path="$1"
    
    # 如果没有 old_coverage.py，无法检查，视作不满足100%覆盖（保守策略）
    if [ ! -f "$SCRIPT_DIR/old_coverage.py" ]; then
        return 1
    fi
    
    # 调用 old_coverage.py
    # 我们不需要 JSON 输出，只是为了检查百分比
    local coverage_output
    coverage_output=$(python3 "$SCRIPT_DIR/old_coverage.py" suite "$suite_path" 2>&1)
    echo "$coverage_output"
    
    # 提取行覆盖率和分支覆盖率
    local line_cov=$(echo "$coverage_output" | grep "Line coverage:" | grep -oE "[0-9.]+" | tail -n 1)
    local branch_cov=$(echo "$coverage_output" | grep "Branch coverage (effective):" | grep -oE "[0-9.]+" | tail -n 1)
    
    # 处理分支覆盖率为 N/A 的情况
    if echo "$coverage_output" | grep -q "No effective branch edges found"; then
        branch_cov="100.00"
    fi
    
    if [ -z "$line_cov" ] || [ -z "$branch_cov" ]; then
        return 1
    fi
    
    # 检查是否都达到 100%
    local is_full=$(awk "BEGIN {if ($line_cov == 100.00 && $branch_cov == 100.00) print \"1\"; else print \"0\"}")
    
    if [ "$is_full" = "1" ]; then
        return 0
    else
        return 1
    fi
}

# 记录函数状态
log_function_status() {
    local func_name="$1"
    local status="$2"  # 开始/成功/失败/跳过
    local message="$3"
    
    if [ -z "$PROGRESS_FILE" ]; then
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
    
    cat >> "$PROGRESS_FILE" << EOF
[$timestamp] $status_icon $func_name - $status_color
    详情: $message
EOF
}

# 完成状态文件
finalize_progress_file() {
    local total=$1
    local success=$2
    local failed=$3
    local skipped=$4
    
    if [ -z "$PROGRESS_FILE" ]; then
        return
    fi
    
    local end_time=$(date '+%Y-%m-%d %H:%M:%S')
    
    cat >> "$PROGRESS_FILE" << EOF

################################################################################
#                         测试完成总结
################################################################################
结束时间: $end_time

最终统计:
  总函数数: $total
  ✓ 成功: $success
  ✗ 失败: $failed
  ⊗ 跳过: $skipped

状态: 已完成
################################################################################
EOF
    
    log_info "📊 最终进度报告已保存: $PROGRESS_FILE"
}

# 检查是否为root用户
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "此脚本需要root权限运行"
        log_info "请使用: sudo $0 $@"
        exit 1
    fi
}

# 获取C文件中所有函数列表
get_all_functions() {
    local c_file="$1"
    local pg_src_path="${2:-/usr/src/postgresql}"
    
    # 注意：不在这里输出日志，因为会混入函数列表
    # 日志应该在调用此函数前输出
    
    # 使用 Python 脚本调用 Clang 获取函数列表
    # 注意：调用此函数前应该已经 cd 到 SCRIPT_DIR
    python3 - <<EOF
import sys
import os
import clang.cindex

# 添加当前目录到 Python 路径，以便导入 pg_clang_helper
sys.path.insert(0, "$SCRIPT_DIR")

# 重定向 stdout 到 stderr，这样 pg_clang_helper 的日志不会混入函数列表
# 保存原始 stdout
original_stdout = sys.stdout
sys.stdout = sys.stderr

from pg_clang_helper import get_pg_compiler_args

clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')

c_file = "$c_file"
pg_src_path = "$pg_src_path"

index = clang.cindex.Index.create()
compiler_args = get_pg_compiler_args(c_file, pg_src_path)

try:
    tu = index.parse(c_file, args=compiler_args)
except Exception as e:
    print(f"ERROR: 解析文件失败: {e}", file=sys.stderr)
    sys.exit(1)

# 恢复 stdout 用于输出函数列表
sys.stdout = original_stdout

functions = []
for node in tu.cursor.get_children():
    if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.is_definition():
        if node.location.file and node.location.file.name == c_file:
            functions.append(node.spelling)

if functions:
    for func in functions:
        print(func)  # 输出到真正的 stdout
else:
    sys.stdout = sys.stderr  # 切换回 stderr 输出错误
    print("ERROR: 未在文件中找到任何函数定义", file=sys.stderr)
    print(f"INFO: 文件路径: {c_file}", file=sys.stderr)
    print(f"INFO: 请确认文件中有函数定义（不是只有声明）", file=sys.stderr)
    sys.exit(1)
EOF
}

# 主函数
main() {
    local c_file="$1"
    local max_rounds="${2:-3}"

    # ==================== 计时器功能 ====================
    # 记录总开始时间
    local total_start_time=$(date +%s)
    local processed_functions_count=0
    local total_function_time=0

    # ==================== LLM统计功能 ====================
    local total_rounds=0
    local total_input_tokens=0
    local total_output_tokens=0
    local total_db_error_time=0  # 数据库错误等待时间

    # 设置中断处理
    trap handle_interrupt SIGINT

    log_info "💡 提示: 按 Ctrl+C 可中断程序并查看当前统计信息"

    # 检查前置条件
    check_root
    
    if [ -z "$c_file" ]; then
        log_error "使用方法: $0 <C文件路径> [最大优化轮次]"
        log_info "例如: $0 src/backend/utils/adt/int.c 3"
        exit 1
    fi
    
    if [ ! -f "$c_file" ]; then
        log_error "C文件不存在: $c_file"
        exit 1
    fi
    
    # 获取绝对路径
    c_file=$(readlink -f "$c_file")
    
    # 保存原始工作目录（通常是 /usr/src/postgresql）
    local original_dir=$(pwd)
    
    log_info "=== C文件所有函数批量测试生成系统 ==="
    log_info "STRUT工具目录: $SCRIPT_DIR"
    log_info "原始工作目录: $original_dir"
    log_info "C文件: $c_file"
    log_info "每个函数最大优化轮次: $max_rounds"
    log_info "================================================"
    
    # 获取所有函数列表
    log_section "步骤1: 扫描C文件中的所有函数"
    log_info "正在扫描C文件中的所有函数..."
    
    local temp_func_list=$(mktemp)
    
    # 🔍 调试信息：切换目录前
    log_info "🔍 [调试] 切换目录前："
    log_info "   - 当前目录: $(pwd)"
    log_info "   - SCRIPT_DIR: $SCRIPT_DIR"
    log_info "   - C文件路径: $c_file"
    log_info "   - 临时文件: $temp_func_list"
    
    # 切换到 SCRIPT_DIR 以便 Python 能导入 pg_clang_helper
    cd "$SCRIPT_DIR"
    log_info "🔍 [调试] 切换目录后: $(pwd)"
    
    # 只重定向 stdout（纯函数列表）到临时文件，stderr（日志）直接显示
    if ! get_all_functions "$c_file" > "$temp_func_list"; then
        log_error "扫描函数失败"
        log_error "临时文件内容："
        cat "$temp_func_list"
        rm -f "$temp_func_list"
        cd "$original_dir"
        exit 1
    fi
    
    # 切换回原始目录
    cd "$original_dir"
    log_info "🔍 [调试] 恢复目录后: $(pwd)"
    
    # 🔍 调试信息：显示临时文件内容
    log_info "🔍 [调试] 临时文件内容（前10行）："
    head -10 "$temp_func_list" | while read line; do
        log_info "   >>> $line"
    done
    
    # 读取函数列表
    log_info "🔍 [调试] 准备读取临时文件: $temp_func_list"
    log_info "🔍 [调试] 临时文件是否存在: $([ -f "$temp_func_list" ] && echo '是' || echo '否')"
    log_info "🔍 [调试] 临时文件大小: $(wc -l < "$temp_func_list" 2>/dev/null || echo '无法读取') 行"
    
    mapfile -t functions < "$temp_func_list"
    
    log_info "🔍 [调试] mapfile 执行后，数组元素个数: ${#functions[@]}"
    
    rm -f "$temp_func_list"
    
    # 🔍 调试信息：显示读取的函数列表
    log_info "🔍 [调试] 读取到的函数数组（前5个）："
    for i in {0..4}; do
        if [ $i -lt ${#functions[@]} ]; then
            log_info "   [$i] = '${functions[$i]}'"
        fi
    done
    
    if [ ${#functions[@]} -eq 0 ]; then
        log_error "未在文件中找到任何函数"
        exit 1
    fi
    
    log_success "发现 ${#functions[@]} 个函数:"
    for i in "${!functions[@]}"; do
        echo "   $((i+1)). ${functions[$i]}"
    done
    
    # 批量处理每个函数
    log_section "步骤2: 批量处理所有函数"
    
    local success_count=0
    local failed_count=0
    local skipped_count=0
    declare -a failed_functions
    declare -a skipped_functions
    
    log_info "🔍 [调试] 开始 for 循环，函数总数: ${#functions[@]}"
    
    # 初始化实时进度跟踪
    init_progress_file "$c_file"
    
    # 使用 C 风格的 for 循环代替 "${!functions[@]}"
    # 因为 "${!functions[@]}" 在某些情况下展开有问题
    for ((i=0; i<${#functions[@]}; i++)); do
        log_info "🔍 [调试] === 循环迭代开始 ==="
        log_info "🔍 [调试] 当前索引 i = $i"
        local func="${functions[$i]}"
        local current=$((i+1))
        local total=${#functions[@]}
        
        # 更新进度统计
        update_progress_stats "$total" "$current" "$success_count" "$failed_count" "$skipped_count"
        
        echo ""
        echo "##################################################################"
        echo "#  处理进度: $current/$total"
        echo "#  当前函数: $func"
        echo "##################################################################"
        echo ""
        
        # 🔍 调试信息：函数名检查
        log_info "🔍 [调试] 当前处理的函数："
        log_info "   - 函数名: '$func'"
        log_info "   - 函数名长度: ${#func}"
        # xxd 可能不存在，使用 || true 防止脚本退出
        log_info "   - 函数名（十六进制）: $(echo -n "$func" | xxd -p 2>/dev/null | head -c 60 || echo 'xxd命令不可用')"

        # 检查并处理之前的数据库错误时间
        # 查找所有测试套件目录中的数据库错误开始时间文件
        local db_error_time=0
        if [ -d "$c_dir/my_$c_basename" ]; then
            while IFS= read -r -d '' db_error_file; do
                if [ -f "$db_error_file" ]; then
                    local error_start_time=$(cat "$db_error_file" 2>/dev/null || echo "0")
                    local current_time=$(date +%s)
                    if [ "$error_start_time" -gt 0 ] && [ "$current_time" -gt "$error_start_time" ]; then
                        local this_error_time=$((current_time - error_start_time))
                        db_error_time=$((db_error_time + this_error_time))
                        log_info "检测到数据库错误等待时间: ${this_error_time}秒 (文件: $db_error_file)"
                        # 清理错误开始时间文件
                        rm -f "$db_error_file"
                    fi
                fi
            done < <(find "$c_dir/my_$c_basename" -name ".db_error_start" -type f -print0 2>/dev/null)
        fi

        # 从总时间中减去数据库错误等待时间
        if [ $db_error_time -gt 0 ]; then
            total_function_time=$((total_function_time - db_error_time))
            log_info "从总时间中减去数据库错误等待时间: ${db_error_time}秒"
        fi

        # 记录函数处理开始时间
        local func_start_time=$(date +%s)

        # 检查是否已存在测试套件
        local c_basename=$(basename "$c_file" .c)
        local c_dir=$(dirname "$c_file")
        local suite_dir="$c_dir/my_$c_basename/test_${func}_suite"
        
        # 🔍 调试信息：路径信息
        log_info "🔍 [调试] 路径信息："
        log_info "   - C文件: $c_file"
        log_info "   - C文件基名: $c_basename"
        log_info "   - C文件目录: $c_dir"
        log_info "   - 测试套件目录: $suite_dir"
        log_info "   - 当前工作目录: $(pwd)"
        
        if [ -d "$suite_dir" ] && [ -f "$suite_dir/Makefile" ]; then
            # 测试套件已存在，检查是否有覆盖率文件
            log_info "检测到已存在的测试套件: $suite_dir"
            
            # 查找覆盖率文件 (test_*.c.gcov 或 *.c.gcov)
            local gcov_file=$(find "$suite_dir" -maxdepth 1 -name "*.c.gcov" -type f | head -n 1)
            
            if [ -n "$gcov_file" ]; then
                # 有覆盖率文件，进一步检查是否达到 100% 覆盖
                if check_coverage_100 "$suite_dir"; then
                    log_success "✓ 测试套件有效且达到 100% 覆盖，跳过: $suite_dir"
                    skipped_count=$((skipped_count + 1))
                    skipped_functions+=("$func")
                    processed_functions_count=$((processed_functions_count + 1))

                    # 计算跳过函数的耗时
                    local skip_func_duration=0
                    total_function_time=$((total_function_time + skip_func_duration))
                    total_rounds=$((total_rounds + 1))

                    log_function_status "$func" "跳过" "测试套件有效且覆盖率100%: $suite_dir"

                    echo ""
                    echo "-------------------------------------------------------------------"
                    echo "  进度: $current/$total  成功: $success_count  失败: $failed_count  跳过: $skipped_count"
                    echo "  函数耗时: ${skip_func_duration}秒 (跳过)"
                    echo "-------------------------------------------------------------------"

                    continue
                else
                    log_warning "⚠ 测试套件存在但覆盖率未达到 100%，尝试优化..."
                fi
            else
                log_warning "⚠ 测试套件缺少覆盖率文件，需要重新验证和优化"
                log_info "重新运行测试套件以收集错误信息..."
                
                # 先运行一次测试套件，收集错误信息
                if SOURCE_DIR="$c_dir" SOURCE_FILE="$c_basename.c" \
                   bash "$SCRIPT_DIR/run_test_suite.sh" "$suite_dir"; then
                    # 运行成功，检查覆盖率
                    gcov_file=$(find "$suite_dir" -maxdepth 1 -name "*.c.gcov" -type f | head -n 1)
                    if [ -n "$gcov_file" ] && check_coverage_100 "$suite_dir"; then
                        log_success "✓ 测试套件验证成功且达到 100% 覆盖"
                        skipped_count=$((skipped_count + 1))
                        skipped_functions+=("$func")
                        processed_functions_count=$((processed_functions_count + 1))

                        # 计算验证函数的耗时（设为0，因为是快速验证）
                        local verify_func_duration=0
                        total_function_time=$((total_function_time + verify_func_duration))

                        # 验证成功函数的统计信息（假设验证时有1轮）
                        total_rounds=$((total_rounds + 1))  # 假设验证时有1轮
                        # input_tokens 和 output_tokens 保持为0，因为跳过了实际生成

                        log_function_status "$func" "跳过" "测试套件验证成功: $suite_dir"

                        echo ""
                        echo "-------------------------------------------------------------------"
                        echo "  进度: $current/$total  成功: $success_count  失败: $failed_count  跳过: $skipped_count"
                        echo "  函数耗时: ${verify_func_duration}秒 (验证)"
                        echo "-------------------------------------------------------------------"

                        continue
                    else
                        log_warning "⚠ 测试套件运行成功但未生成覆盖率文件，尝试优化..."
                    fi
                else
                    log_warning "⚠ 测试套件运行失败，需要优化"
                fi
                
                # 需要优化：调用 auto_test_optimize.sh
                log_info "开始优化已存在的测试套件..."
                log_function_status "$func" "优化" "重新优化测试套件: $suite_dir"
                
                # 继续执行后面的 auto_test_optimize.sh（不要 continue）
            fi
        fi
        
        # 调用 auto_test_optimize.sh 处理单个函数
        log_info "调用 auto_test_optimize.sh 处理函数: $func"

        # 记录开始状态
        log_function_status "$func" "开始" "开始生成单元测试..."

        # 🔍 调试信息：即将执行的命令
        log_info "🔍 [调试] 执行命令："
        log_info "   bash \"$SCRIPT_DIR/auto_test_optimize.sh\" \"$c_file\" -f \"$func\" \"$max_rounds\""

        # 执行 auto_test_optimize.sh
        if bash "$SCRIPT_DIR/auto_test_optimize.sh" "$c_file" -f "$func" "$max_rounds"; then
            log_success "✅ 函数 $func 处理成功"
            success_count=$((success_count + 1))  # 使用赋值而不是 ((++))
            processed_functions_count=$((processed_functions_count + 1))

            # 记录成功状态
            log_function_status "$func" "成功" "测试套件生成成功: $suite_dir"
        else
            log_error "❌ 函数 $func 处理失败"
            failed_count=$((failed_count + 1))  # 使用赋值而不是 ((++))
            failed_functions+=("$func")
            processed_functions_count=$((processed_functions_count + 1))

            # 记录失败状态
            log_function_status "$func" "失败" "测试套件生成失败，请查看错误日志"
        fi

        # 从统计文件读取统计信息
        local stats_file="$suite_dir/.stats"
        local func_rounds=1  # 默认至少1轮（初始生成）
        local func_input_tokens=0
        local func_output_tokens=0
        local func_db_error_time=0

        if [ -f "$stats_file" ]; then
            # 安全地读取统计信息，如果读取失败使用默认值
            func_rounds=$(grep "ROUNDS:" "$stats_file" 2>/dev/null | cut -d: -f2 2>/dev/null || echo "1")
            func_input_tokens=$(grep "TOKENS_INPUT:" "$stats_file" 2>/dev/null | cut -d: -f2 2>/dev/null || echo "0")
            func_output_tokens=$(grep "TOKENS_OUTPUT:" "$stats_file" 2>/dev/null | cut -d: -f2 2>/dev/null || echo "0")
            func_db_error_time=$(grep "DB_ERROR_TIME:" "$stats_file" 2>/dev/null | cut -d: -f2 2>/dev/null || echo "0")
        else
            log_warning "⚠️ 统计文件不存在: $stats_file，使用默认值"
        fi

        # 累加统计信息
        if [ -n "$func_rounds" ]; then
            total_rounds=$((total_rounds + func_rounds))
        fi
        if [ -n "$func_input_tokens" ]; then
            total_input_tokens=$((total_input_tokens + func_input_tokens))
        fi
        if [ -n "$func_output_tokens" ]; then
            total_output_tokens=$((total_output_tokens + func_output_tokens))
        fi
        if [ -n "$func_db_error_time" ] && [ "$func_db_error_time" -gt 0 ]; then
            total_db_error_time=$((total_db_error_time + func_db_error_time))
        fi

        # 计算函数处理耗时
        local func_end_time=$(date +%s)
        local func_duration=$((func_end_time - func_start_time))

        # 检查是否有数据库错误等待时间需要扣除
        local db_error_start_file="$suite_dir/.db_error_start"
        if [ -f "$db_error_start_file" ]; then
            local db_error_start_time=$(cat "$db_error_start_file")
            local db_error_duration=$((func_end_time - db_error_start_time))
            if [ $db_error_duration -gt 0 ]; then
                log_info "检测到数据库错误等待时间: ${db_error_duration}秒，从总时间中扣除"
                func_duration=$((func_duration - db_error_duration))
                total_db_error_time=$((total_db_error_time + db_error_duration))
                # 确保函数耗时不为负数
                if [ $func_duration -lt 0 ]; then
                    func_duration=0
                fi
            fi
            # 删除标记文件，避免重复计算
            rm -f "$db_error_start_file"
        fi

        total_function_time=$((total_function_time + func_duration))

        echo ""
        echo "-------------------------------------------------------------------"
        echo "  进度: $current/$total  成功: $success_count  失败: $failed_count  跳过: $skipped_count"
        echo "  函数耗时: ${func_duration}秒"
        echo "-------------------------------------------------------------------"
        
        log_info "🔍 [调试] 循环迭代结束，准备处理下一个函数..."
    done
    
    log_info "🔍 [调试] for 循环已完成！"
    
    # 完成进度文件
    finalize_progress_file "${#functions[@]}" "$success_count" "$failed_count" "$skipped_count"

    # 将最终统计信息也写入进度文件
    cat >> "$PROGRESS_FILE" << EOF

================================================================================
最终统计信息 (完成时间: $(date '+%H:%M:%S'))
================================================================================
总函数数: ${#functions[@]}
处理函数数: $processed_functions_count
总耗时: ${total_duration}秒
函数总耗时: ${total_function_time}秒
数据库错误等待时间: ${total_db_error_time}秒
有效处理时间: $((total_function_time - total_db_error_time))秒
平均函数耗时: ${avg_function_time}秒/函数

✓ 成功: $success_count
✗ 失败: $failed_count
⊗ 跳过: $skipped_count

LLM统计:
总迭代轮次: $total_rounds
平均每函数迭代: ${avg_rounds_per_function}
输入总token数: $total_input_tokens
平均输入token: ${avg_input_tokens_per_function}
输出总token数: $total_output_tokens
平均输出token: ${avg_output_tokens_per_function}
================================================================================
EOF
    
    # 计算总耗时
    local total_end_time=$(date +%s)
    local total_duration=$((total_end_time - total_start_time))

    # 计算平均耗时（只计算实际处理的函数）
    local avg_function_time=0
    if [ $processed_functions_count -gt 0 ]; then
        avg_function_time=$((total_function_time / processed_functions_count))
    fi

    # 计算平均统计信息
    local avg_rounds_per_function=0
    local avg_input_tokens_per_function=0
    local avg_output_tokens_per_function=0

    if [ $processed_functions_count -gt 0 ]; then
        avg_rounds_per_function=$((total_rounds / processed_functions_count))
        avg_input_tokens_per_function=$((total_input_tokens / processed_functions_count))
        avg_output_tokens_per_function=$((total_output_tokens / processed_functions_count))
    fi

    # 输出最终统计
    echo ""
    echo "##################################################################"
    echo "#  🎉 批量处理完成！"
    echo "##################################################################"
    echo ""
    log_info "总计: ${#functions[@]} 个函数"
    log_success "✅ 成功: $success_count 个函数"
    log_error "❌ 失败: $failed_count 个函数"
    log_warning "⏭️  跳过: $skipped_count 个函数（已存在）"
    echo ""
    log_info "⏱️  性能统计:"
    log_info "   总耗时: ${total_duration}秒"
    log_info "   处理函数数: $processed_functions_count 个"
    log_info "   函数总耗时: ${total_function_time}秒"
    log_info "   数据库错误等待时间: ${total_db_error_time}秒"
    log_info "   有效处理时间: $((total_function_time - total_db_error_time))秒"
    log_info "   平均函数耗时: ${avg_function_time}秒/函数"
    echo ""
    log_info "🤖 LLM统计:"
    log_info "   总迭代轮次: $total_rounds 轮"
    log_info "   平均每函数迭代: ${avg_rounds_per_function} 轮/函数"
    log_info "   输入总token数: $total_input_tokens"
    log_info "   平均输入token: ${avg_input_tokens_per_function} token/函数"
    log_info "   输出总token数: $total_output_tokens"
    log_info "   平均输出token: ${avg_output_tokens_per_function} token/函数"
    
    if [ $skipped_count -gt 0 ]; then
        echo ""
        log_warning "跳过的函数列表（已存在测试套件）:"
        for func in "${skipped_functions[@]}"; do
            echo "   - $func"
        done
    fi
    
    if [ $failed_count -gt 0 ]; then
        echo ""
        log_error "失败的函数列表:"
        for func in "${failed_functions[@]}"; do
            echo "   - $func"
        done
    fi
    
    echo ""
    log_info "所有测试套件已生成到:"
    local c_basename=$(basename "$c_file" .c)
    local c_dir=$(dirname "$c_file")
    local outer_dir="$c_dir/my_$c_basename"
    echo "   $outer_dir/"
    
    # 生成统计报告文件
    local stats_file="$outer_dir/batch_processing_stats.txt"
    log_info "📊 生成统计报告文件: $stats_file"

    cat > "$stats_file" << EOF
================================================================================
批量测试生成统计报告
================================================================================
生成时间: $(date '+%Y-%m-%d %H:%M:%S')
C文件: $c_file
最大优化轮次: $max_rounds

基本统计:
----------
总函数数: ${#functions[@]}
处理函数数: $processed_functions_count
成功函数数: $success_count
失败函数数: $failed_count
跳过函数数: $skipped_count

时间统计:
----------
总耗时: ${total_duration}秒
函数总耗时: ${total_function_time}秒
数据库错误等待时间: ${total_db_error_time}秒
有效处理时间: $((total_function_time - total_db_error_time))秒
平均函数耗时: ${avg_function_time}秒/函数

LLM统计:
----------
总迭代轮次: $total_rounds
平均每函数迭代: ${avg_rounds_per_function}
输入总token数: $total_input_tokens
平均输入token: ${avg_input_tokens_per_function}
输出总token数: $total_output_tokens
平均输出token: ${avg_output_tokens_per_function}

详细信息:
----------
EOF

    # 添加失败的函数列表
    if [ $failed_count -gt 0 ]; then
        echo "失败的函数:" >> "$stats_file"
        for func in "${failed_functions[@]}"; do
            echo "  - $func" >> "$stats_file"
        done
        echo "" >> "$stats_file"
    fi

    # 添加跳过的函数列表
    if [ $skipped_count -gt 0 ]; then
        echo "跳过的函数:" >> "$stats_file"
        for func in "${skipped_functions[@]}"; do
            echo "  - $func" >> "$stats_file"
        done
        echo "" >> "$stats_file"
    fi

    echo "================================================================================
统计报告已保存至: $stats_file
================================================================================
" >> "$stats_file"

    echo ""
    log_info "📊 实时进度文件: $PROGRESS_FILE"
    log_info "📈 统计报告文件: $stats_file"
    log_info "下一步操作:"
    echo "   1. 查看进度报告: cat $PROGRESS_FILE"
    echo "   2. 查看统计报告: cat $stats_file"
    echo "   3. 查看每个函数的测试套件目录"
    echo "   4. 检查失败函数的错误日志: test_*_suite/test_errors.txt"
    echo "   5. 手动优化失败的函数"
    
    # 返回状态码
    if [ $failed_count -gt 0 ]; then
        exit 1
    else
        exit 0
    fi
}

# 脚本入口
main "$@"

