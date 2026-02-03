import json
import os
import re
import shutil
import clang.cindex
from datetime import datetime

# ===============================
# 🔧 兼容补丁：为 Cursor 增加可哈希键
# ===============================
def _cursor_key(cur):
    try:
        usr = cur.get_usr() if hasattr(cur, "get_usr") else None
    except Exception:
        usr = None
    try:
        file_name = cur.location.file.name if (cur.location and cur.location.file) else None
        line = cur.location.line if cur.location else None
        col = cur.location.column if cur.location else None
    except Exception:
        file_name, line, col = None, None, None
    return (cur.spelling, str(cur.kind), usr, file_name, line, col)

# 给 clang.cindex.Cursor 动态添加 __hash__ / __eq__，使其可放入 set/dict
if not hasattr(clang.cindex.Cursor, "__hash__"):
    def _cursor_hash(self):
        return hash(_cursor_key(self))
    def _cursor_eq(self, other):
        return isinstance(other, clang.cindex.Cursor) and _cursor_key(self) == _cursor_key(other)
    clang.cindex.Cursor.__hash__ = _cursor_hash
    clang.cindex.Cursor.__eq__ = _cursor_eq

# ===============================
# 继续加载项目模块
# ===============================
from get_dependencies import remove_function_declarations, remove_global_variable_assignments
from delete_useless_info import simplify_file
from util import get_args, get_file, write_file
from generator import case_generator, prompt_generator, opti_generator
from model import access_model
from test_case import make_case_list
from seed_case_generator import generate_seed_case
from pg_regress_generator import generate_pg_regress_suite

# 配置 libclang 库的路径
clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')

# 用于优化模式下的对话历史
conversation_history = []


def clean_llm_response(response_text):
    """
    清理LLM响应，去掉markdown代码块标记
    """
    # 去掉开头和结尾的markdown标记
    cleaned = response_text.strip()
    
    # 去掉开头的 ```c 或 ```
    if cleaned.startswith('```c'):
        cleaned = cleaned[4:].strip()
    elif cleaned.startswith('```'):
        cleaned = cleaned[3:].strip()
    
    # 去掉结尾的 ```
    if cleaned.endswith('```'):
        cleaned = cleaned[:-3].strip()
    
    return cleaned

def supplement_missing_includes(c_code, case_template):
    """
    重新整理所有头文件，按照PostgreSQL严格的头文件包含顺序：
    1. postgres.h (必须第一)
    2. fmgr.h (必须紧随其后)
    3. 其他PostgreSQL内部头文件
    4. C标准库头文件
    
    Args:
        c_code (str): LLM生成的C代码
        case_template (str): JSON格式的种子用例模板
    
    Returns:
        str: 重新整理头文件顺序的C代码
    """
    try:
        case_data = json.loads(case_template)
        direct_includes = case_data.get('direct_includes', [])
        
        # 提取C代码中已有的include语句并移除它们
        include_pattern = r'#include\s*[<"][^>"]+[>"]\s*\n?'
        existing_include_matches = re.findall(include_pattern, c_code)
        
        # 从代码中移除所有现有的include语句
        c_code_without_includes = re.sub(include_pattern, '', c_code).strip()
        
        # 收集所有需要的头文件（现有的 + 种子用例的）
        all_includes = set()
        
        # 添加现有的include
        for match in existing_include_matches:
            include_match = re.search(r'#include\s*[<"]([^>"]+)[>"]', match)
            if include_match:
                all_includes.add(include_match.group(1))
        
        # 添加种子用例中的include
        for include_item in direct_includes:
            include_file = include_item.strip('"<>')
            all_includes.add(include_file)
        
        # 按PostgreSQL头文件包含顺序分类
        postgres_h = None
        fmgr_h = None
        pg_internal_includes = []  # PostgreSQL内部头文件
        c_standard_includes = []   # C标准库头文件
        
        for include_file in all_includes:
            # 根据文件名决定格式
            if include_file in ['limits.h', 'ctype.h', 'math.h', 'stdio.h', 'stdlib.h', 'string.h', 'unistd.h', 'errno.h'] or include_file.startswith('sys/'):
                formatted_include = f'#include <{include_file}>'
            else:
                formatted_include = f'#include "{include_file}"'
            
            # 按PostgreSQL头文件包含顺序分类
            if include_file == 'postgres.h':
                postgres_h = formatted_include
            elif include_file == 'fmgr.h':
                fmgr_h = formatted_include
            elif include_file in ['limits.h', 'ctype.h', 'math.h', 'stdio.h', 'stdlib.h', 'string.h', 'unistd.h', 'errno.h'] or include_file.startswith('sys/'):
                # C标准库头文件
                c_standard_includes.append(formatted_include)
            else:
                # PostgreSQL内部头文件
                pg_internal_includes.append(formatted_include)
        
        # 按PostgreSQL严格的头文件包含顺序组织
        ordered_includes = []
        
        # 1. postgres.h 必须第一
        if postgres_h:
            ordered_includes.append(postgres_h)
        
        # 2. fmgr.h 必须紧随其后
        if fmgr_h:
            ordered_includes.append(fmgr_h)
        
        # 3. 其他PostgreSQL内部头文件
        if pg_internal_includes:
            if ordered_includes:  # 如果前面有头文件，添加空行分隔
                ordered_includes.append('')
                ordered_includes.append('// 其他 PostgreSQL 内部头文件')
            # 按字母顺序排序，保持一致性
            pg_internal_includes.sort()
            ordered_includes.extend(pg_internal_includes)
        
        # 4. C标准库头文件放在最后
        if c_standard_includes:
            if ordered_includes:  # 如果前面有头文件，添加空行分隔
                ordered_includes.append('')
                ordered_includes.append('// C 标准库头文件')
            # 按字母顺序排序
            c_standard_includes.sort()
            ordered_includes.extend(c_standard_includes)
        
        if ordered_includes:
            print(f"   重新整理头文件顺序: {len([inc for inc in ordered_includes if inc.startswith('#include')])} 个")
            
            # 将整理好的include添加到代码开头
            ordered_includes_text = '\n'.join(ordered_includes) + '\n\n'
            c_code = ordered_includes_text + c_code_without_includes
        else:
            c_code = c_code_without_includes
        
        return c_code
        
    except Exception as e:
        print(f"   ⚠️  整理头文件时出错: {e}")
        return c_code

def reorder_all_includes_in_file(c_code, case_template=None):
    """
    对完整的C文件进行头文件重排序，确保postgres.h在第一行
    同时合并种子用例中的头文件
    
    Args:
        c_code (str): 完整的C代码
        case_template (str): JSON格式的种子用例模板（可选）
    
    Returns:
        str: 重新排序头文件的C代码
    """
    try:
        # 提取C代码中所有的include语句并移除它们
        include_pattern = r'#include\s*[<"][^>"]+[>"]\s*\n?'
        existing_include_matches = re.findall(include_pattern, c_code)
        
        # 从代码中移除所有现有的include语句
        c_code_without_includes = re.sub(include_pattern, '', c_code).strip()
        
        # 收集所有头文件
        all_includes = set()
        
        # 添加现有的include
        for match in existing_include_matches:
            include_match = re.search(r'#include\s*[<"]([^>"]+)[>"]', match)
            if include_match:
                include_file = include_match.group(1)
                all_includes.add(include_file)
        
        # 添加种子用例中的头文件（如果提供）
        if case_template:
            try:
                case_data = json.loads(case_template)
                direct_includes = case_data.get('direct_includes', [])
                for include_item in direct_includes:
                    include_file = include_item.strip('"<>')
                    all_includes.add(include_file)
                    
                if direct_includes:
                    print(f"   合并种子用例头文件: {len(direct_includes)} 个")
            except Exception as e:
                print(f"   ⚠️  处理种子用例头文件时出错: {e}")
        
        if not all_includes:
            return c_code
        
        # 按PostgreSQL头文件包含顺序分类
        postgres_h = None
        fmgr_h = None
        pg_internal_includes = []  # PostgreSQL内部头文件
        c_standard_includes = []   # C标准库头文件
        
        for include_file in all_includes:
            # 根据文件名决定格式
            if include_file in ['limits.h', 'ctype.h', 'math.h', 'stdio.h', 'stdlib.h', 'string.h', 'unistd.h', 'errno.h'] or include_file.startswith('sys/'):
                formatted_include = f'#include <{include_file}>'
            else:
                formatted_include = f'#include "{include_file}"'
            
            # 按PostgreSQL头文件包含顺序分类
            if include_file == 'postgres.h':
                postgres_h = formatted_include
            elif include_file == 'fmgr.h':
                fmgr_h = formatted_include
            elif include_file in ['limits.h', 'ctype.h', 'math.h', 'stdio.h', 'stdlib.h', 'string.h', 'unistd.h', 'errno.h'] or include_file.startswith('sys/'):
                # C标准库头文件
                c_standard_includes.append(formatted_include)
            else:
                # PostgreSQL内部头文件
                pg_internal_includes.append(formatted_include)
        
        # 按PostgreSQL严格的头文件包含顺序组织
        ordered_includes = []
        
        # 1. postgres.h 必须第一
        if postgres_h:
            ordered_includes.append(postgres_h)
        
        # 2. fmgr.h 必须紧随其后
        if fmgr_h:
            ordered_includes.append(fmgr_h)
        
        # 3. 其他PostgreSQL内部头文件
        if pg_internal_includes:
            if ordered_includes:  # 如果前面有头文件，添加空行分隔
                ordered_includes.append('')
                ordered_includes.append('// 其他 PostgreSQL 内部头文件')
            # 按字母顺序排序，保持一致性
            pg_internal_includes.sort()
            ordered_includes.extend(pg_internal_includes)
        
        # 4. C标准库头文件放在最后
        if c_standard_includes:
            if ordered_includes:  # 如果前面有头文件，添加空行分隔
                ordered_includes.append('')
                ordered_includes.append('// C 标准库头文件')
            # 按字母顺序排序
            c_standard_includes.sort()
            ordered_includes.extend(c_standard_includes)
        
        if ordered_includes:
            print(f"   重新排序头文件: {len([inc for inc in ordered_includes if inc.startswith('#include')])} 个")
            
            # 将整理好的include添加到代码开头
            ordered_includes_text = '\n'.join(ordered_includes) + '\n\n'
            c_code = ordered_includes_text + c_code_without_includes
        else:
            c_code = c_code_without_includes
        
        return c_code
        
    except Exception as e:
        print(f"   ⚠️  最终头文件重排序时出错: {e}")
        return c_code

def read_limited_error_info(error_file_path, max_lines=100):
    """
    读取错误信息文件，限制行数以避免LLM API溢出
    优先返回前100行内容，因为通常最重要的错误信息在开头
    
    Args:
        error_file_path (str): 错误文件路径
        max_lines (int): 最大读取行数，默认100行
    
    Returns:
        str: 限制后的错误信息内容
    """
    try:
        with open(error_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if len(lines) <= max_lines:
            return ''.join(lines)
        
        # 如果超过限制，优先返回前100行（最重要的错误信息通常在开头）
        limited_content = ''.join(lines[:max_lines])
        limited_content += f"\n... [省略了 {len(lines) - max_lines} 行后续错误信息以避免API溢出] ...\n"
        
        print(f"   ⚠️  错误文件过长({len(lines)}行)，已限制为前{max_lines}行")
        
        return limited_content
        
    except Exception as e:
        print(f"   ⚠️  读取错误文件时出错: {e}")
        return ""

def save_current_round_files(suite_dir, prompt_content, response_content, func_name, is_optimization_mode):
    """
    智能保存当前轮次的文件：
    - 基础prompt文件：仅在初始生成时保存（用于后续优化轮次读取）
    - 当前轮次文件：覆盖写入（用于查看当前完整prompt）
    - 历史记录文件：追加写入（用于调试分析）
    
    Args:
        suite_dir (str): 测试套件目录
        prompt_content (str): prompt内容
        response_content (str): 响应内容
        func_name (str): 函数名
        is_optimization_mode (bool): 是否为优化模式
    """
    mode_text = "优化模式" if is_optimization_mode else "初始生成"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. 基础prompt文件（仅在初始生成时保存，会覆盖旧文件以确保纯净）
    base_prompt_file = os.path.join(suite_dir, 'prompt_base.txt')
    if not is_optimization_mode:
        # 在非优化模式下，总是保存/更新基础prompt（确保是纯净的初始prompt）
        write_file(base_prompt_file, prompt_content)
        print(f"   ✓ 基础prompt已保存")
    else:
        print(f"   ℹ️  优化模式：使用现有基础prompt")
    
    # 2. 当前轮次文件（覆盖写入，用于查看当前完整prompt）
    current_prompt_file = os.path.join(suite_dir, 'prompt.txt')
    current_response_file = os.path.join(suite_dir, 'response.txt')
    
    # 保存当前轮次的prompt和response（纯内容，无格式）
    write_file(current_prompt_file, prompt_content)
    write_file(current_response_file, response_content)
    
    # 2. 历史记录文件（追加写入，用于调试分析）
    history_prompt_file = os.path.join(suite_dir, 'prompt_history.txt')
    history_response_file = os.path.join(suite_dir, 'response_history.txt')
    
    # 追加保存到历史文件（带格式和时间戳）
    file_exists = os.path.exists(history_prompt_file)
    
    with open(history_prompt_file, 'a', encoding='utf-8') as f:
        if file_exists:
            f.write(f"\n\n{'='*60}\n")
        f.write(f"时间: {timestamp}\n")
        f.write(f"函数: {func_name}\n")
        f.write(f"模式: {mode_text}\n")
        f.write(f"{'='*60}\n\n")
        f.write(prompt_content)
        f.write(f"\n{'='*60}\n")
    
    file_exists = os.path.exists(history_response_file)
    
    with open(history_response_file, 'a', encoding='utf-8') as f:
        if file_exists:
            f.write(f"\n\n{'='*60}\n")
        f.write(f"时间: {timestamp}\n")
        f.write(f"模式: {mode_text}\n")
        f.write(f"{'='*60}\n\n")
        f.write(response_content)
        f.write(f"\n{'='*60}\n")

def simplify(input_path, output_path, pg_src_path, compiler_args=None):
    """简化 C 源文件，为 LLM 创建一个最小化的上下文。"""
    print("  - 正在移除函数声明...")
    remove_function_declarations(input_path, output_path, pg_src_path, compiler_args)
    print("  - 正在移除全局变量赋值...")
    remove_global_variable_assignments(output_path, output_path, pg_src_path, compiler_args)
    print("  - 正在移除未使用的顶层定义...")
    simplify_file(output_path, pg_src_path, compiler_args)


def get_all_functions_in_file(c_file_path, pg_src_path):
    """
    获取C文件中所有函数的列表
    
    Args:
        c_file_path: C文件路径
        pg_src_path: PostgreSQL源码路径
    
    Returns:
        list: 函数名列表
    """
    index = clang.cindex.Index.create()
    compiler_args = get_pg_compiler_args(c_file_path, pg_src_path)
    
    try:
        tu = index.parse(c_file_path, args=compiler_args)
    except Exception as e:
        print(f"❌ 解析文件失败: {e}")
        return []
    
    functions = []
    for node in tu.cursor.get_children():
        if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.is_definition():
            if node.location.file and node.location.file.name == c_file_path:
                functions.append(node.spelling)
    
    return functions


def process_single_function(function_path, target_function, uncover_path, pg_src_path, pg_config_path):
    """
    处理单个函数的测试用例生成
    
    Args:
        function_path: C文件路径
        target_function: 目标函数名
        uncover_path: 未覆盖分支文件路径
        pg_src_path: PostgreSQL源码路径
        pg_config_path: pg_config路径
    
    Returns:
        bool: 是否成功
    """
    dir_path = os.path.dirname(function_path)
    
    print(f"\n{'='*60}")
    print(f"🎯 处理函数: {target_function}")
    print(f"{'='*60}")

    # --- 1. 静态分析：生成种子用例 ---
    try:
        print("\n步骤 1: [静态分析] 从源文件自动生成种子用例...")
        case_content, compiler_args = generate_seed_case(function_path, pg_src_path, target_function)
        print("✅ 种子用例生成成功。")

        # ✅ 输出生成的种子用例内容
        print("\n--- 🧩 生成的种子用例内容 ---")
        print(case_content)
        print("--- 🧩 结束 ---\n")

    except Exception as e:
        import traceback
        print(f"❌ 在种子用例生成过程中发生错误: {e}")
        traceback.print_exc()
        return False

    # --- 2. 静态分析：简化代码上下文 ---
    # print("\n步骤 2: [静态分析] 简化 C 代码以创建最小上下文...")
    # temp_simplified_path = function_path + ".simplified"
    # shutil.copy(function_path, temp_simplified_path)  # ✅ 修复复制逻辑
    
    # #检查复制后的文件
    # print(f"🔍 [main] 复制的 .simplified 文件大小: {os.path.getsize(temp_simplified_path)} 字节")
    
    # simplify(temp_simplified_path, temp_simplified_path, pg_src_path, compiler_args)  # 传递编译参数
    
    # # 检查简化后的文件
    # print(f"🔍 [main] 简化后的 .simplified 文件大小: {os.path.getsize(temp_simplified_path)} 字节")
    
    # # 读取简化后的代码内容用于分析
    # simplified_context = get_file(temp_simplified_path)
    # function_context = get_file(function_path)  # 读取未经简化的原始代码
    
    # # 输出简化结果的统计信息
    # original_lines = len(function_context.splitlines())
    # simplified_lines = len(simplified_context.splitlines())
    # print(f"📊 [main] 代码简化统计:")
    # print(f"    原始代码行数: {original_lines}")
    # print(f"    简化后行数: {simplified_lines}")
    # print(f"    减少行数: {original_lines - simplified_lines}")
    # print(f"    压缩率: {((original_lines - simplified_lines) / original_lines * 100):.1f}%")
    
    # # 输出简化后的代码内容（前50行和后20行）
    # simplified_lines_list = simplified_context.splitlines()
    # print(f"\n--- 📝 简化后的代码内容（前50行）---")
    # for i, line in enumerate(simplified_lines_list[:50], 1):
    #     print(f"{i:3d}| {line}")
    
    # if len(simplified_lines_list) > 70:
    #     print(f"\n... [省略 {len(simplified_lines_list) - 70} 行] ...")
    #     print(f"\n--- 📝 简化后的代码内容（后20行）---")
    #     for i, line in enumerate(simplified_lines_list[-20:], len(simplified_lines_list) - 19):
    #         print(f"{i:3d}| {line}")
    # elif len(simplified_lines_list) > 50:
    #     print(f"\n--- 📝 简化后的代码内容（剩余行）---")
    #     for i, line in enumerate(simplified_lines_list[50:], 51):
    #         print(f"{i:3d}| {line}")
    
    # 在第139行，不要立即删除 .simplified 文件
    # os.remove(temp_simplified_path)  # 注释掉这行
    # print(f"�� [main] 保留简化文件用于调试: {temp_simplified_path}")
    # print("\n✅ C 代码上下文准备完成。")
    print("\n步骤 2: [静态分析] 简化 C 代码以创建最小上下文...")
    print("\n✅ 暂时不准备 C 代码上下文")
    
    # 由于跳过了简化步骤，直接读取原始文件作为上下文
    function_context = get_file(function_path)


    # print(function_context)

    # --- 3. LLM 交互：构建 Prompt 并调用模型 ---
    case, default_PTR, has_stub = case_generator(case_content)
    
    # 调试：检查case中是否包含inputs/outputs/stubins
    case_data_debug = json.loads(case)
    print(f"🔍 调试信息：case中的关键字段")
    print(f"   - inputs: {len(case_data_debug.get('inputs', []))} 个")
    print(f"   - outputs: {len(case_data_debug.get('outputs', []))} 个")
    print(f"   - stubins: {len(case_data_debug.get('stubins', []))} 个")
    if case_data_debug.get('inputs'):
        print(f"   - inputs 示例: {case_data_debug['inputs'][0] if case_data_debug['inputs'] else 'None'}")

    # 🔧 修改：优先使用目标函数名，如果没有指定则从seed case中获取实际函数名
    if target_function:
        fun_name = target_function
        print(f"📍 使用指定的目标函数名: {fun_name}")
    else:
        # 从seed_case_generator返回的结果中获取实际的函数名
        case_data = json.loads(case_content)
        actual_func_name = case_data.get('func', '')
        if actual_func_name:
            fun_name = actual_func_name
            print(f"📍 从种子用例中获取实际函数名: {fun_name}")
        else:
            # 回退到从文件名提取
            fun_name = os.path.splitext(os.path.basename(function_path))[0]
            ind = fun_name.find('_build')
            if ind != -1:
                fun_name = fun_name[:ind]
            print(f"📍 回退到从文件名提取函数名: {fun_name}")

    model = 'deepseek-chat'   # 或 'deepseek-reasoner'
    print(f"\n步骤 3: [LLM交互] 使用模型 '{model}' 为函数 '{fun_name}' 生成测试用例...")

    # 判断是否为优化模式：基于文件夹命名规则自动检测
    # 构建预期的测试套件路径
    
    file_base_name = os.path.splitext(os.path.basename(function_path))[0]
    outer_dir = os.path.join(dir_path, f"my_{file_base_name}")
    expected_suite_dir = os.path.join(outer_dir, f"test_{fun_name}_suite")
    
    # 检查是否存在之前的测试套件（包含必要文件）
    previous_suite_exists = (
        os.path.exists(expected_suite_dir) and
        os.path.exists(os.path.join(expected_suite_dir, 'prompt_base.txt')) and
        os.path.exists(os.path.join(expected_suite_dir, 'response.txt'))
    )
    
    # 智能自动关联：如果没传路径但存在旧的覆盖率文件，自动使用它
    if not uncover_path and previous_suite_exists:
        auto_json = os.path.join(expected_suite_dir, 'uncover_branches.json')
        if os.path.exists(auto_json):
            uncover_path = auto_json
            print(f"   💡 自动关联到现有的未覆盖信息: {uncover_path}")

    is_optimization_mode = bool(uncover_path) or previous_suite_exists
    
    if previous_suite_exists:
        print(f"   检测到之前的测试套件: {expected_suite_dir}")
    elif uncover_path:
        print(f"   提供了未覆盖分支文件，进入优化模式")
    
    if not is_optimization_mode:
        # 正常模式：第一次生成
        prompt = prompt_generator(function_context, case, has_stub)
        print(prompt)
        print(f"   📊 生成的prompt长度: {len(prompt)} 字符")
        print(f"   ℹ️  prompt已保存，不在终端显示以避免输出混乱")
        resp = access_model(prompt, model)
    else:
        # 优化模式：基于之前的结果进行优化
        print("   (优化模式: 基于之前的测试结果进行优化...)")
        
        # 处理未覆盖分支信息
        branch_info = ""
        if uncover_path and uncover_path != 'FORCE_OPTIMIZE' and os.path.exists(uncover_path):
            print(f"   正在读取详细未覆盖信息: {uncover_path}")
            uncover_content = get_file(uncover_path)
            try:
                uncover_info = json.loads(uncover_content)
                
                # 1. 处理汇总摘要
                branches = uncover_info.get('branches', [])
                for i, b in enumerate(branches, 1):
                    branch_info += f"{i}. branch: {b['branch']}: {b['condition']} condition uncovered.\n"
                
                # 2. 处理详细行信息
                uncovered_lines = uncover_info.get('uncovered_lines', [])
                if uncovered_lines:
                    branch_info += "\n**Detailed Uncovered Lines:**\n"
                    branch_info += '\n'.join([f"- {line}" for line in uncovered_lines]) + "\n"
                
                # 3. 处理详细分支信息
                uncovered_branches_detailed = uncover_info.get('uncovered_branches', [])
                if uncovered_branches_detailed:
                    branch_info += "\n**Detailed Uncovered Branches:**\n"
                    branch_info += '\n'.join([f"- {branch}" for branch in uncovered_branches_detailed]) + "\n"
                
                if not branch_info:
                    branch_info = "1. general_optimization: Improve test coverage.\n"
            except Exception as e:
                print(f"   ⚠️ 解析 JSON 失败: {e}")
                branch_info = "1. general_optimization: Improve test coverage.\n"
        else:
            print("   ℹ️ 未提供有效的未覆盖分支路径，使用通用优化信息")
            branch_info = "1. general_optimization: Improve test coverage and fix any compilation or runtime issues.\n"

        # 优化模式：使用检测到的测试套件目录
        if previous_suite_exists:
            previous_suite_dir = expected_suite_dir
            print(f"   从之前的测试套件读取文件: {previous_suite_dir}")
        else:
            # 如果没有检测到之前的测试套件，但提供了uncover_path，需要查找
            print(f"❌ 未找到之前的测试套件目录: {expected_suite_dir}")
            print("   请先运行第一轮生成，或检查测试套件是否被删除")
            return False
        
        # 从之前的测试套件目录读取文件
        base_prompt_path = os.path.join(previous_suite_dir, 'prompt_base.txt')
        previous_output_path = os.path.join(previous_suite_dir, 'response.txt')
        error_file_path = os.path.join(previous_suite_dir, 'test_errors.txt')
        
        # 读取基础prompt（初始生成时的prompt）和上一轮的LLM响应
        if not os.path.exists(base_prompt_path):
            print(f"❌ 未找到基础prompt文件: {base_prompt_path}")
            print("   这可能是因为测试套件是旧版本生成的")
            print("   请重新运行初始生成，或手动创建 prompt_base.txt 文件")
            return False
        if not os.path.exists(previous_output_path):
            print(f"❌ 未找到之前的响应文件: {previous_output_path}")
            return False
            
        base_prompt = get_file(base_prompt_path)
        previous_llm_response = get_file(previous_output_path)
        
        # 读取错误信息（如果存在），限制行数以避免API溢出
        error_info = None
        if os.path.exists(error_file_path):
            error_info = read_limited_error_info(error_file_path, max_lines=100)
            print(f"   ✓ 发现测试错误信息文件，已加载")
        
        # 构建完整的优化prompt
        # 1. 从基础prompt开始（这样每次优化都只包含初始prompt）
        prompt = base_prompt
        
        # 2. 添加优化说明和上一轮的代码、错误信息
        optimization_section = opti_generator(previous_llm_response, error_info)
        prompt += optimization_section
        
        # 3. 添加未覆盖分支信息
        prompt += branch_info
        
        print(f"   ✅ 优化prompt构建完成")
        print(f"   📊 最终prompt长度: {len(prompt)} 字符")
        print(prompt)
        
        # 保存调试用的完整prompt（可选）
        debug_prompt_file = os.path.join(previous_suite_dir, 'prompt_debug.txt')
        write_file(debug_prompt_file, prompt)
        print(f"   ℹ️  完整prompt已保存到文件，不在终端显示")
        
        resp = access_model(prompt, model)

    print("✅ 已收到 LLM 响应。")

    # --- 4. 结果处理 ---
    print("\n步骤 4: [结果处理] 处理LLM生成的C代码...")
    
    # 4.1 清理LLM响应，去掉markdown标记
    print("   清理markdown代码块标记...")
    cleaned_response = clean_llm_response(resp)
    
    # 4.2 暂时跳过头文件处理，将在最终阶段统一处理
    print("   LLM代码清理完成，将在最终阶段统一处理头文件...")
    llm_generated_c_code = cleaned_response
    
    print(f"✅ 已处理完成，最终C代码长度: {len(llm_generated_c_code)} 字符。")

    # --- 5. 代码生成：生成 pg_regress 测试套件 ---
    print("\n步骤 5: [代码生成] 为 pg_regress 生成完整的测试套件...")

    # 🔧 修改部分：创建两层目录结构
    # 外层目录：my_{文件名}
    file_base_name = os.path.splitext(os.path.basename(function_path))[0]
    outer_dir = os.path.join(dir_path, f"my_{file_base_name}")
    os.makedirs(outer_dir, exist_ok=True)
    
    # 内层目录：test_{完整函数名}_suite
    output_suite_dir = os.path.join(outer_dir, f"test_{fun_name}_suite")

    try:
        generate_pg_regress_suite(llm_generated_c_code, fun_name, function_context, output_suite_dir, pg_config_path)
        print(f"✅ 测试套件已生成至: {output_suite_dir}")
        
        # 🔧 新增：对生成的C文件进行最终的头文件重排序和种子用例头文件合并
        print("   对生成的C文件进行头文件重排序...")
        test_c_file = os.path.join(output_suite_dir, f"test_{fun_name}.c")
        
        if os.path.exists(test_c_file):
            with open(test_c_file, 'r', encoding='utf-8') as f:
                original_c_code = f.read()
            
            # 重新排序头文件并合并种子用例头文件
            reordered_c_code = reorder_all_includes_in_file(original_c_code, case)
            
            # 写回文件
            with open(test_c_file, 'w', encoding='utf-8') as f:
                f.write(reordered_c_code)
            
            print(f"   ✅ 头文件重排序完成: {test_c_file}")
        else:
            print(f"   ❌ 测试C文件不存在: {test_c_file}")
        
        # 现在设置正确的文件路径（在测试套件目录内）
        input_path = os.path.join(output_suite_dir, 'prompt.txt')
        output_path = os.path.join(output_suite_dir, 'response.txt')
        
    except Exception as e:
        print(f"❌ 生成 pg_regress 测试套件时发生错误: {e}")
        return False

    # --- 6. 保存对话历史和测试套件路径 ---
    # 智能保存文件：当前轮次（覆盖）+ 历史记录（追加）
    print("   保存prompt和响应历史...")
    save_current_round_files(output_suite_dir, prompt, cleaned_response, fun_name, is_optimization_mode)
    
    # 注意：不再需要保存test_suite_path.txt，通过文件夹命名规则自动检测
    
    # 如果是优化模式，也保存uncover_branches.json到测试套件目录
    if uncover_path and uncover_path != 'FORCE_OPTIMIZE':
        suite_uncover_file = os.path.join(output_suite_dir, 'uncover_branches.json')
        uncover_content = get_file(uncover_path)
        write_file(suite_uncover_file, uncover_content)
    elif is_optimization_mode:
        # 如果是强制优化模式，创建一个通用的uncover_branches.json
        suite_uncover_file = os.path.join(output_suite_dir, 'uncover_branches.json')
        general_uncover = {
            "branches": [
                {
                    "branch": "general_optimization",
                    "condition": "Improve test coverage and fix any compilation or runtime issues"
                }
            ]
        }
        write_file(suite_uncover_file, json.dumps(general_uncover, indent=2))
    
    print(f"\n--- 🚀 流程执行完毕 ---")
    print(f"测试套件已生成到: {output_suite_dir}")
    print(f"可以使用以下命令运行测试套件:")
    print(f"chmod +x {output_suite_dir}")
    print(f"bash ./STRUT/run_test_suite.sh {output_suite_dir}")
    
    return True  # 成功返回 True


def main():
    """程序的主入口点，编排整个测试用例生成流程。"""
    # --- 0. 环境配置与参数解析 ---
    function_path, uncover_path, target_function = get_args()
    
    # 定义 PostgreSQL 相关路径
    pg_config_path = '/usr/local/pgsql/bin/pg_config'
    pg_src_path = os.getenv('PG_SRC_PATH', '/usr/src/postgresql')
    
    print("--- 环境配置 ---")
    print(f"待测文件: {function_path}")
    if target_function:
        print(f"目标函数: {target_function}")
    else:
        print("⚠️  未指定函数名！")
        print("   请使用 -f 参数指定函数名")
        print("   例如: python3 main.py file.c -f function_name")
        print("")
        print("   如果想批量处理所有函数，请使用:")
        print("   bash STRUT/auto_test_all_functions.sh file.c")
        return
    
    print(f"使用的 pg_config 路径: {pg_config_path}")
    print(f"使用的 PostgreSQL 源码路径: {pg_src_path}")
    print("-" * 20)
    
    # 处理指定的函数
    process_single_function(function_path, target_function, uncover_path, pg_src_path, pg_config_path)


if __name__ == "__main__":
    main()
