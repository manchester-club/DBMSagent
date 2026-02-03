import os
import sys
import clang.cindex
from clang import cindex
from clang.cindex import CursorKind, TokenKind, TranslationUnit
from extract_function_info import extract_function_info
from util import write_content
from pg_clang_helper import get_pg_compiler_args

# 指定 libclang 路径
clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')


# =====================================================
# 工具函数：增强 include 路径 + 多轮解析重试（容错）
# =====================================================

def _augment_include_paths(args, pg_src_path):
    """增强 include 路径和编译宏"""
    extra_includes = [
        f"-I{pg_src_path}/src/include",
        f"-I{pg_src_path}/src/interfaces/libpq",
        f"-I{pg_src_path}/src/backend",
        "-I/usr/lib/llvm-14/lib/clang/14.0.0/include",
        "-I/usr/local/include",
        "-I/usr/include/x86_64-linux-gnu",
        "-I/usr/include",
    ]
    for inc in extra_includes:
        if inc not in args:
            args.append(inc)
    if not any(a.startswith("-std=") for a in args):
        args.append("-std=c11")
    args += ["-D_GNU_SOURCE", "-D__STDC_CONSTANT_MACROS", "-D__STDC_LIMIT_MACROS"]
    return args


def _try_parse_with_fallbacks(index, file_path, args, pg_src_path):
    """多轮 Clang 解析，失败时返回 None"""
    # 获取绝对路径
    abs_file_path = os.path.abspath(file_path)
    
    # 检查文件是否存在
    if not os.path.exists(abs_file_path):
        print(f"⚠️ [_try_parse_with_fallbacks] 文件不存在: {abs_file_path}")
        return None
    
    # 不使用 unsaved_files，直接解析磁盘上的文件
    unsaved = None

    base_args = list(args)
    variants = [base_args]

    # variant 2: include 当前目录
    curdir = os.path.dirname(os.path.abspath(file_path))
    var2 = list(base_args)
    var2.append(f"-I{curdir}")
    variants.append(var2)

    # variant 3: include postgres.h
    var3 = list(var2)
    postgres_h = os.path.join(pg_src_path, "src/include/postgres.h")
    if os.path.exists(postgres_h):
        var3.append(f"-include{postgres_h}")
    variants.append(var3)

    for i, av in enumerate(variants, 1):
        try:
            tu = index.parse(
                abs_file_path,  # 使用绝对路径
                args=av,
                unsaved_files=unsaved,  # None，不使用 unsaved_files
                options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
            )
            return tu
        except clang.cindex.TranslationUnitLoadError as e:
            print(f"⚠️  [delete_useless_info] 尝试 #{i} 失败: {e}")
        except Exception as e:
            print(f"⚠️  [delete_useless_info] 尝试 #{i} 异常: {e}")
    
    print(f"❌ [_try_parse_with_fallbacks] 所有解析尝试都失败了")
    return None


# =====================================================
# 主功能：收集与移除未使用定义
# =====================================================

def collect_top_level_definitions(file_path, pg_src_path, compiler_args=None):
    """
    收集顶层定义（struct, var, typedef, enum, union 等）
    """
    index = cindex.Index.create()
    if compiler_args is None:
        # 如果处理的是 .simplified 文件，使用原始 PostgreSQL 源码路径获取编译参数
        if file_path.endswith('.simplified'):
            original_path = file_path.replace('.simplified', '')
            if os.path.exists(original_path):
                print(f"🔍 [collect_top_level_definitions] 使用原始文件路径获取编译参数: {original_path}")
                compiler_args = get_pg_compiler_args(original_path, pg_src_path)
            else:
                print(f"🔍 [collect_top_level_definitions] 原始文件不存在，使用 .simplified 文件路径: {file_path}")
                compiler_args = get_pg_compiler_args(file_path, pg_src_path)
        else:
            compiler_args = get_pg_compiler_args(file_path, pg_src_path)
    else:
        print(f"🔍 [collect_top_level_definitions] 使用传递的编译参数，参数数量: {len(compiler_args)}")
    
    compiler_args = _augment_include_paths(compiler_args, pg_src_path)


    tu = _try_parse_with_fallbacks(index, file_path, compiler_args, pg_src_path)
    if tu is None:
        print(f"❕ [collect_top_level_definitions] 无法解析 {file_path}，返回空结果。")
        return []

    definitions = []
    
    # 获取目标文件的绝对路径用于比较
    abs_file_path = os.path.abspath(file_path)
    
    for cursor in tu.cursor.walk_preorder():
        if cursor.location.file:
            # 尝试匹配相对路径或绝对路径
            if cursor.location.file.name == file_path or cursor.location.file.name == abs_file_path:
                if cursor.kind == CursorKind.MACRO_DEFINITION:
                    definitions.append({
                    'name': cursor.spelling,
                    'range': (
                        (cursor.extent.start.line, cursor.extent.start.column),
                        (cursor.extent.end.line, cursor.extent.end.column)
                    ),
                    'kind': 'macro'
                })
            elif cursor.kind in [
                CursorKind.STRUCT_DECL, CursorKind.VAR_DECL,
                CursorKind.TYPEDEF_DECL, CursorKind.ENUM_DECL,
                CursorKind.UNION_DECL
            ] and cursor.semantic_parent.kind == CursorKind.TRANSLATION_UNIT:
                prefix = ''
                if cursor.kind == CursorKind.STRUCT_DECL: prefix = 'struct '
                elif cursor.kind == CursorKind.UNION_DECL: prefix = 'union '
                elif cursor.kind == CursorKind.ENUM_DECL: prefix = 'enum '
                definitions.append({
                    'name': prefix + cursor.spelling,
                    'range': (
                        (cursor.extent.start.line, cursor.extent.start.column),
                        (cursor.extent.end.line, cursor.extent.end.column)
                    ),
                    'kind': cursor.kind
                })
    
    return definitions


def simplify_file(file_path, pg_src_path, compiler_args=None):
    """
    移除未使用的顶层定义。
    """
    print(f"🔍 [simplify_file] 开始处理文件: {file_path}")
    
    variable_types, global_variables = extract_function_info(file_path,pg_src_path, compiler_args)
    print(f"🔍 [simplify_file] extract_function_info 结果: 变量类型 {len(variable_types)} 个, 全局变量 {len(global_variables)} 个")
    
    definitions = collect_top_level_definitions(file_path, pg_src_path, compiler_args)
    print(f"🔍 [simplify_file] collect_top_level_definitions 结果: {len(definitions)} 个定义")

    if not definitions:
        print(f"❕ [simplify_file] 无法获取 {file_path} 的顶层定义，跳过。")
        return

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        source_code = f.readlines()

    used_names = set()
    used_names.update(variable_types)
    used_names.update(global_variables)

    unused_definitions = [
        d for d in definitions if d['name'] not in used_names
    ]

    if unused_definitions:
        print(f"🧹 [simplify_file] 移除 {len(unused_definitions)} 个未使用定义。")
    else:
        print(f"✅ [simplify_file] 无需移除定义。")

    new_source_code = remove_unused_definitions(source_code, unused_definitions)
    write_content(file_path, ''.join(new_source_code))


def remove_unused_definitions(source_lines, unused_definitions):
    """
    删除未使用的顶层定义（按起始位置反序处理）
    """
    sorted_defs = sorted(
        unused_definitions,
        key=lambda d: (d['range'][0][0], d['range'][0][1]),
        reverse=True
    )

    for definition in sorted_defs:
        start_line, start_col = definition['range'][0]
        end_line, end_col = definition['range'][1]
        end_col += 1
        start_line_idx = start_line - 1
        end_line_idx = end_line - 1

        if start_line_idx == end_line_idx:
            line = source_lines[start_line_idx]
            new_line = line[:start_col - 1] + line[end_col:]
            source_lines[start_line_idx] = new_line
        else:
            start_part = source_lines[start_line_idx][:start_col - 1]
            end_part = source_lines[end_line_idx][end_col:]
            for i in range(start_line_idx + 1, end_line_idx):
                source_lines[i] = ''
            source_lines[start_line_idx] = start_part + '\n'
            source_lines[end_line_idx] = end_part
            if start_line_idx + 1 == end_line_idx:
                source_lines[start_line_idx] = start_part + end_part
    return source_lines