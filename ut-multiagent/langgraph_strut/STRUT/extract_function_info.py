import os
import sys
import clang.cindex
from clang import cindex
from clang.cindex import CursorKind, TokenKind, TranslationUnit
from pg_clang_helper import get_pg_compiler_args

# 确保 libclang 正确加载
clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')


# ===============================
# 工具函数：增强 include 路径与宏
# ===============================
def _augment_include_paths(args, pg_src_path):
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
    # 标准与宏定义
    if not any(a.startswith("-std=") for a in args):
        args.append("-std=c11")
    args += ["-D_GNU_SOURCE", "-D__STDC_CONSTANT_MACROS", "-D__STDC_LIMIT_MACROS"]
    return args


# ===============================
# 工具函数：多轮解析尝试
# ===============================
def _try_parse_with_fallbacks(index, file_path, args, pg_src_path):
    """
    多轮解析尝试:
      1. 基础参数
      2. 加上当前目录 include
      3. 强制 include postgres.h
    """
    try:
        code = open(file_path, encoding="utf-8", errors="ignore").read()
    except Exception:
        code = ""
    unsaved = [(file_path, code)]
    base_args = list(args)
    variants = [base_args]

    # 变体 2：加上当前目录
    curdir = os.path.dirname(os.path.abspath(file_path))
    var2 = list(base_args)
    var2.append(f"-I{curdir}")
    variants.append(var2)

    # 变体 3：强制 include postgres.h
    var3 = list(var2)
    postgres_h = os.path.join(pg_src_path, "src/include/postgres.h")
    if os.path.exists(postgres_h):
        var3.append(f"-include{postgres_h}")
    variants.append(var3)

    for i, av in enumerate(variants, 1):
        try:
            tu = index.parse(
                file_path,
                args=av,
                unsaved_files=unsaved,
                options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
            )
            return tu
        except clang.cindex.TranslationUnitLoadError as e:
            print(f"⚠️  [extract_function_info] 尝试 #{i} 失败: {e}")
            print(f"    使用的参数: {' '.join(av)}")
        except Exception as e:
            print(f"⚠️  [extract_function_info] 尝试 #{i} 异常: {e}")
    return None


# ===============================
# 类型与变量分析逻辑
# ===============================
def is_function_pointer(var_type):
    return (
        var_type.kind == cindex.TypeKind.POINTER
        and var_type.get_pointee().kind == cindex.TypeKind.FUNCTIONPROTO
    )


def process_file(file_path, pg_src_path, compiler_args=None):
    index = cindex.Index.create()
    if compiler_args is None:
        compiler_args = get_pg_compiler_args(file_path, pg_src_path)
    compiler_args = _augment_include_paths(compiler_args, pg_src_path)

    tu = _try_parse_with_fallbacks(index, file_path, compiler_args, pg_src_path)
    if tu is None:
        print(f"❕ [process_file] 无法解析 {file_path}，返回空结果。")
        return set(), set()

    variable_types = set()
    global_variables = set()
    process_node(tu.cursor, variable_types, global_variables)
    return variable_types, global_variables


def process_node(node, variable_types, global_variables):
    if node.kind == cindex.CursorKind.FUNCTION_DECL:
        process_function_body(node, variable_types, global_variables)
    else:
        for child in node.get_children():
            process_node(child, variable_types, global_variables)


def process_function_body(node, variable_types, global_variables):
    for param in node.get_arguments():
        process_variable_declaration(param, variable_types)
    if node.result_type.kind != cindex.TypeKind.INVALID:
        process_type(node.result_type, variable_types)
    for child in node.get_children():
        if child.kind == cindex.CursorKind.DECL_STMT:
            for decl in child.get_children():
                if decl.kind == cindex.CursorKind.VAR_DECL:
                    process_variable_declaration(decl, variable_types)
        elif child.kind == cindex.CursorKind.COMPOUND_STMT:
            for inner_child in child.get_children():
                process_function_body(inner_child, variable_types, global_variables)
        elif child.kind == cindex.CursorKind.DECL_REF_EXPR:
            process_variable_reference(child, global_variables, variable_types)
        else:
            process_function_body(child, variable_types, global_variables)


def process_variable_declaration(var_decl, variable_types):
    var_type = var_decl.type
    process_type(var_type, variable_types)


def process_variable_reference(ref_expr, global_variables, variable_types):
    if not ref_expr.referenced:
        return
    process_variable_declaration(ref_expr.referenced, variable_types)
    var_decl = ref_expr.referenced
    if var_decl is not None and var_decl.kind == cindex.CursorKind.VAR_DECL:
        if is_global_variable(var_decl):
            global_variables.add(var_decl.spelling)


def is_global_variable(var_decl):
    return var_decl.semantic_parent.kind == cindex.CursorKind.TRANSLATION_UNIT


def get_basic_type(var_type):
    if var_type.kind == cindex.TypeKind.POINTER:
        return get_basic_type(var_type.get_pointee())
    elif var_type.kind in (
        cindex.TypeKind.CONSTANTARRAY,
        cindex.TypeKind.INCOMPLETEARRAY,
    ):
        return get_basic_type(var_type.get_array_element_type())
    elif var_type.kind == cindex.TypeKind.TYPEDEF:
        return get_basic_type(var_type.get_canonical())
    else:
        return var_type


def process_type(var_type, variable_types):
    base_type = get_basic_type(var_type)
    type_name = base_type.spelling
    variable_types.add(type_name)
    if not is_builtin_type(var_type):
        type_decl = var_type.get_declaration()
        if type_decl and type_decl.kind != cindex.CursorKind.NO_DECL_FOUND:
            if type_decl.kind == cindex.CursorKind.TYPEDEF_DECL:
                underlying_type = var_type.get_canonical()
                process_type(underlying_type, variable_types)
            elif type_decl.kind == cindex.CursorKind.STRUCT_DECL:
                for field in type_decl.get_children():
                    if field.kind == cindex.CursorKind.FIELD_DECL:
                        process_type(field.type, variable_types)


def is_builtin_type(var_type):
    kind = var_type.kind
    return kind in [
        cindex.TypeKind.VOID,
        cindex.TypeKind.BOOL,
        cindex.TypeKind.CHAR_U,
        cindex.TypeKind.UCHAR,
        cindex.TypeKind.CHAR16,
        cindex.TypeKind.CHAR32,
        cindex.TypeKind.USHORT,
        cindex.TypeKind.UINT,
        cindex.TypeKind.ULONG,
        cindex.TypeKind.ULONGLONG,
        cindex.TypeKind.UINT128,
        cindex.TypeKind.CHAR_S,
        cindex.TypeKind.SCHAR,
        cindex.TypeKind.WCHAR,
        cindex.TypeKind.SHORT,
        cindex.TypeKind.INT,
        cindex.TypeKind.LONG,
        cindex.TypeKind.LONGLONG,
        cindex.TypeKind.INT128,
        cindex.TypeKind.FLOAT,
        cindex.TypeKind.DOUBLE,
        cindex.TypeKind.LONGDOUBLE,
        cindex.TypeKind.NULLPTR,
    ]


def get_type_location(var_type):
    type_decl = var_type.get_declaration()
    if type_decl and type_decl.location.file:
        return f"{type_decl.location.file.name}:{type_decl.location.line}"
    else:
        return "unknown location"

def extract_function_info(file_path, pg_src_path, compiler_args=None):
    try:
        variable_types, global_variables = process_file(file_path, pg_src_path, compiler_args)
        print(f"🔍 [extract_function_info] 成功解析 {file_path}")
    except Exception as e:
        print(f"⚠️  [extract_function_info] 解析 {file_path} 失败: {e}")
        variable_types, global_variables = set(), set()
    return variable_types, global_variables