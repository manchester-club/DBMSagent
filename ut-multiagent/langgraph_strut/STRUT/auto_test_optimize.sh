# auto_test_optimize.sh 

#!/bin/bash

# 自动化测试用例生成和优化脚本
# 使用方法（在 /usr/src/postgresql 目录下运行）:
#   bash STRUT/auto_test_optimize.sh src/backend/utils/adt/int.c -f int2out
#   bash STRUT/auto_test_optimize.sh src/backend/utils/adt/int.c -f int2out 5
#
# 或指定完整路径:
#   ./auto_test_optimize.sh /path/to/function.c -f int2out 3
#   ./auto_test_optimize.sh /path/to/function.c 3

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
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

log_round() {
    echo -e "${PURPLE}[ROUND $1]${NC} $2"
}

# 获取脚本所在目录（STRUT目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 检查是否为root用户
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "此脚本需要root权限运行"
        log_info "请使用: sudo $0 $@"
        exit 1
    fi
}

# 检查参数
check_arguments() {
    if [ $# -lt 1 ]; then
        log_error "使用方法: $0 <C文件路径> [-f 函数名] [最大优化轮次]"
        log_info "例如: $0 /path/to/function.c -f int2out 3"
        log_info "      $0 /path/to/function.c 3"
        exit 1
    fi
}

# 检查覆盖率是否达到100%
check_coverage() {
    local suite_path="$1"
    local json_out="$suite_path/uncover_branches.json"
    
    log_info "正在进行覆盖率检查..."
    
    # 调用 old_coverage.py 生成 JSON 报告
    local coverage_output
    # 将可选参数放在最前面，这是 argparse 最稳妥的处理方式
    coverage_output=$(python3 "$SCRIPT_DIR/old_coverage.py" --json-out "$json_out" suite "$suite_path" 2>&1)
    echo "$coverage_output"
    
    if [ ! -f "$json_out" ]; then
        log_warning "未能生成 uncover_branches.json 文件"
    fi
    
    # 提取行覆盖率和分支覆盖率
    # 示例输出: ✅ Line coverage: 10/10 (100.00%)
    local line_cov=$(echo "$coverage_output" | grep "Line coverage:" | grep -oE "[0-9.]+" | tail -n 1)
    local branch_cov=$(echo "$coverage_output" | grep "Branch coverage (effective):" | grep -oE "[0-9.]+" | tail -n 1)
    
    # 处理分支覆盖率为 N/A 的情况
    if echo "$coverage_output" | grep -q "No effective branch edges found"; then
        branch_cov="100.00"
    fi
    
    # 如果提取不到覆盖率，说明分析失败
    if [ -z "$line_cov" ]; then
        log_warning "未能从 coverage 报告中提取行覆盖率"
        return 1
    fi
    
    if [ -z "$branch_cov" ]; then
        log_warning "未能从 coverage 报告中提取分支覆盖率"
        return 1
    fi

    log_info "覆盖率统计: 行覆盖率 ${line_cov}%, 分支覆盖率 ${branch_cov}%"
    
    # 检查是否都达到 100%
    # 使用 awk 进行浮点数比较
    local is_full_coverage=$(awk "BEGIN {if ($line_cov == 100.00 && $branch_cov == 100.00) print \"1\"; else print \"0\"}")
    
    if [ "$is_full_coverage" = "1" ]; then
        return 0 # 100% 覆盖
    else
        return 1 # 未达到 100% 覆盖
    fi
}

# 运行测试套件并检查结果
run_test_suite() {
    local test_suite_path="$1"
    local round_num="$2"
    local source_file="$3"  # 新增参数：源文件路径

    log_round "$round_num" "运行测试套件: $test_suite_path"

    # 运行测试套件脚本（使用SCRIPT_DIR中的脚本）
    # 传递源文件信息用于覆盖率报告
    if [ -n "$source_file" ]; then
        SOURCE_DIR="$(dirname "$source_file")" SOURCE_FILE="$(basename "$source_file")" \
        bash "$SCRIPT_DIR/run_test_suite.sh" "$test_suite_path"
    else
        bash "$SCRIPT_DIR/run_test_suite.sh" "$test_suite_path"
    fi

    # 检查是否有错误文件且文件不为空
    local error_file="$test_suite_path/test_errors.txt"

    if [ -f "$error_file" ] && [ -s "$error_file" ]; then
        # -s 检查文件存在且大小不为0
        log_warning "测试运行完成，但发现错误"
        return 1  # 有错误
    else
        log_success "测试运行成功，编译和运行均通过"
        
        # 增加覆盖率检查逻辑
        if check_coverage "$test_suite_path"; then
            log_success "✅ 覆盖率达到100%，测试生成成功！"
            return 0
        else
            log_warning "⚠️ 覆盖率未达到100%，将继续进行优化"
            return 1
        fi
    fi
}

# 执行优化轮次
run_optimization_round() {
    local c_file="$1"
    local round_num="$2"
    local uncover_file="$3"
    local func_name="$4"
    
    log_round "$round_num" "开始优化轮次"
    
    # 执行优化（使用SCRIPT_DIR中的main.py）
    # 参数顺序：python3 main.py <c_file> [uncover_file] -f <func_name> --optimize
    local cmd="python3 \"$SCRIPT_DIR/main.py\" \"$c_file\""
    
    # 如果有未覆盖分支文件，添加它
    if [ -n "$uncover_file" ] && [ -f "$uncover_file" ]; then
        cmd="$cmd \"$uncover_file\""
        log_info "使用未覆盖分支文件: $uncover_file"
    else
        # 如果没有未覆盖分支文件，使用 --optimize 标志
        log_info "未提供未覆盖分支文件，使用通用优化模式"
    fi
    
    # 添加函数名参数
    [ -n "$func_name" ] && cmd="$cmd -f \"$func_name\""
    
    # 添加 --optimize 标志（强制进入优化模式）
    cmd="$cmd --optimize"
    
    log_info "执行命令: $cmd"
    
    if eval $cmd; then
        log_success "优化轮次 $round_num 执行成功"
        return 0
    else
        log_error "优化轮次 $round_num 执行失败"
        return 1
    fi
}

# 创建未覆盖分支文件
create_uncover_branches_file() {
    local output_file="$1"
    local error_type="$2"
    
    cat > "$output_file" << EOF
{
    "branches": [
        {
            "branch": "$error_type",
            "condition": "Previous test execution encountered errors"
        },
        {
            "branch": "error_handling",
            "condition": "Need to handle compilation and runtime errors"
        }
    ]
}
EOF
}

# 主函数
main() {
    local c_file=""
    local func_name=""
    local max_rounds=3

    # 解析参数
    while [ $# -gt 0 ]; do
        case "$1" in
            -f|--function)
                func_name="$2"
                shift 2
                ;;
            [0-9]*)
                max_rounds="$1"
                shift
                ;;
            *)
                # 第一个非选项参数作为C文件
                if [ -z "$c_file" ]; then
                    c_file="$1"
                else
                    log_error "未知参数: $1"
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # 检查前置条件
    check_root
    check_arguments "$c_file"
    
    # 检查C文件是否存在
    if [ ! -f "$c_file" ]; then
        log_error "C文件不存在: $c_file"
        exit 1
    fi
    
    # 获取绝对路径
    c_file=$(readlink -f "$c_file")
    
    log_info "=== 自动化测试用例生成和优化系统 ==="
    log_info "STRUT工具目录: $SCRIPT_DIR"
    log_info "当前工作目录: $(pwd)"
    log_info "C文件: $c_file"
    [ -n "$func_name" ] && log_info "目标函数: $func_name"
    log_info "最大优化轮次: $max_rounds"
    log_info "================================================"
    
    local c_dir=$(dirname "$c_file")
    local current_round=1
    local success=false
    
    # 第一轮：初始生成
    log_round "$current_round" "初始测试用例生成"
    
    # 使用SCRIPT_DIR中的main.py
    local init_cmd="python3 \"$SCRIPT_DIR/main.py\" \"$c_file\""
    [ -n "$func_name" ] && init_cmd="$init_cmd -f \"$func_name\""
    
    log_info "执行命令: $init_cmd"
    if ! eval $init_cmd; then
        log_error "初始测试用例生成失败"
        exit 1
    fi
    
    # 基于文件夹命名规则构建测试套件路径
    local c_basename=$(basename "$c_file" .c)
    local outer_dir="$c_dir/my_$c_basename"
    
    # 根据目标函数名构建测试套件路径
    local current_suite_path=""
    if [ -n "$func_name" ]; then
        # 如果指定了函数名，直接构建路径
        current_suite_path="$outer_dir/test_${func_name}_suite"
    else
        # 如果没有指定函数名，查找第一个存在的测试套件目录
    for suite_dir in "$outer_dir"/test_*_suite; do
        if [ -d "$suite_dir" ]; then
            current_suite_path="$suite_dir"
            break
        fi
    done
    fi
    
    if [ -z "$current_suite_path" ]; then
        log_error "未找到测试套件目录，请先运行第一轮生成"
        exit 1
    fi
    
    # 确保测试套件路径也是绝对路径
    current_suite_path=$(readlink -f "$current_suite_path")
    log_info "测试套件路径: $current_suite_path"
    
    # 运行第一轮测试
    if run_test_suite "$current_suite_path" "$current_round" "$c_file"; then
        log_success "第一轮测试成功完成！"
        success=true
    else
        log_warning "第一轮测试失败，需要优化"
    fi
    
    # 优化轮次循环
    local extra_round_added=false
    while [ "$success" = false ]; do
        # 检查是否达到最大轮次
        if [ $current_round -ge $max_rounds ]; then
            # 如果是因为覆盖率没达到100%导致的失败，且还没有增加过额外轮次
            if [ "$success" = false ] && [ "$extra_round_added" = false ] && [ -f "$current_suite_path/uncover_branches.json" ]; then
                log_info "⚠️ 达到最大轮次，但覆盖率未达标，增加一轮额外优化..."
                max_rounds=$((max_rounds + 1))
                extra_round_added=true
            else
                break
            fi
        fi

        current_round=$((current_round + 1))

        # 检查是否有数据库错误时间需要扣除
        # ... (keep existing db error logic)
        local db_error_start_file="$current_suite_path/.db_error_start"
        if [ -f "$db_error_start_file" ]; then
            local db_error_start_time=$(cat "$db_error_start_file")
            local current_time=$(date +%s)
            local db_error_duration=$((current_time - db_error_start_time))

            if [ $db_error_duration -gt 0 ] && [ $db_error_duration -lt 120 ]; then  # 假设数据库错误时间不会超过2分钟
                log_info "检测到数据库错误等待时间: ${db_error_duration}秒，记录到统计信息中"
                # 将数据库错误时间写入统计文件，父脚本会处理
                echo "DB_ERROR_TIME:$db_error_duration" >> "$current_suite_path/.stats"
            fi

            # 删除标记文件，避免重复计算
            rm -f "$db_error_start_file"
        fi

        log_round "$current_round" "开始优化轮次"
        
        # 检查是否有上一轮生成的未覆盖信息
        local uncover_file=""
        if [ -f "$current_suite_path/uncover_branches.json" ]; then
            uncover_file=$(readlink -f "$current_suite_path/uncover_branches.json")
            log_info "发现上一轮的未覆盖信息，将传递给模型进行针对性优化: $uncover_file"
        fi
        
        if [ -z "$uncover_file" ]; then
            log_info "使用通用优化模式（基于测试错误信息）"
        fi
        
        # 执行优化
        if ! run_optimization_round "$c_file" "$current_round" "$uncover_file" "$func_name"; then
            log_error "优化轮次 $current_round 失败"
            break
        fi
        
        # 重新扫描测试套件目录，找到最新的
        local new_suite_path=""
        local latest_time=0
        for suite_dir in "$outer_dir"/test_*_suite; do
            if [ -d "$suite_dir" ]; then
                local dir_time=$(stat -c %Y "$suite_dir" 2>/dev/null || stat -f %m "$suite_dir" 2>/dev/null || echo 0)
                if [ "$dir_time" -gt "$latest_time" ]; then
                    latest_time="$dir_time"
                    new_suite_path="$suite_dir"
                fi
            fi
        done
        
        if [ -z "$new_suite_path" ]; then
            log_error "未找到新的测试套件目录"
            break
        fi
        
        current_suite_path=$(readlink -f "$new_suite_path")
        log_info "新测试套件路径: $current_suite_path"
        
        # 运行优化后的测试
        if run_test_suite "$current_suite_path" "$current_round" "$c_file"; then
            log_success "优化轮次 $current_round 测试成功！"
            success=true
        else
            log_warning "优化轮次 $current_round 测试仍有问题，继续下一轮"
        fi
    done
    
    # 输出最终结果
    log_info "================================================"
    if [ "$success" = true ]; then
        log_success "🎉 测试用例生成和优化成功完成！"
        log_info "最终测试套件: $current_suite_path"
        log_info "总共执行了 $current_round 轮"
    else
        log_warning "⚠️  达到最大优化轮次 ($max_rounds) 或优化失败"
        log_info "最后的测试套件: $current_suite_path"
        log_info "可以手动检查错误信息: $current_suite_path/test_errors.txt"
    fi
    
    log_info "================================================"
    log_info "相关文件位置:"
    log_info "- 测试套件: $current_suite_path"
    log_info "- Prompt历史: $current_suite_path/prompt.txt"
    log_info "- 响应历史: $current_suite_path/response.txt"
    log_info "- 错误信息: $current_suite_path/test_errors.txt"
    log_info "- 未覆盖分支: $current_suite_path/uncover_branches.json"
    log_info "- 测试套件目录: $outer_dir/"

    # 输出统计信息到文件（用于父脚本读取）
    local stats_file="$current_suite_path/.stats"
    cat > "$stats_file" << EOF
ROUNDS:$current_round
SUCCESS:$([ "$success" = true ] && echo "1" || echo "0")
TOKENS_INPUT:0
TOKENS_OUTPUT:0
DB_ERROR_TIME:0
EOF
}

# 脚本入口
main "$@"
