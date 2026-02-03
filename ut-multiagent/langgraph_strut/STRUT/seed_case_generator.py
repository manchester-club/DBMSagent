import clang.cindex
import json
import os
import re
from pg_clang_helper import get_pg_compiler_args

clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')

# ======================================================
# ----------------- PG_GETARG_* 类型映射 -----------------
# ======================================================
PG_ARG_TYPE_MAP = {
    "INT16": "int16", "INT2": "int16", "INT32": "int32", "INT4": "int32",
    "INT64": "int64", "INT8": "int64", "UINT16": "uint16", "UINT32": "uint32",
    "UINT64": "uint64", "POINTER": "void *", "CSTRING": "char *", "BOOL": "bool",
    "FLOAT4": "float4", "FLOAT8": "float8", "NUMERIC": "Numeric", "CASH": "Cash", "MONEY": "Cash",
    "TEXT_P": "text *", "VARCHAR_P": "VarChar *", "BPCHAR_P": "BpChar *", "NAME_P": "Name *", "BYTEA_P": "bytea *",
    "DATEADT": "DateADT", "TIMEADT": "TimeADT", "TIMETZADT": "TimeTzADT",
    "TIMESTAMP": "Timestamp", "TIMESTAMPTZ": "TimestampTz", "INTERVAL_P": "Interval *",
    "OID": "Oid", "REGPROC": "RegProcedure", "REGPROCEDURE": "RegProcedure",
    "REGOPERATOR": "RegOperator", "REGCLASS": "RegClass", "REGTYPE": "RegType",
    "REGROLE": "RegRole", "REGNAMESPACE": "RegNamespace", "REGCONFIG": "RegConfig", "REGDICTIONARY": "RegDictionary",
    "INET_P": "inet *", "CIDR_P": "cidr *", "MACADDR_P": "macaddr *", "MACADDR8_P": "macaddr8 *",
    "PATH_P": "Path *", "BOX_P": "Box *", "CIRCLE_P": "Circle *", "LSEG_P": "Lseg *",
    "POLYGON_P": "Polygon *", "POINT_P": "Point *",
    "RECORD": "HeapTupleHeader", "RECORD_P": "HeapTupleHeader", "ANYELEMENT": "Datum",
    "ANYARRAY": "Datum", "ANYNONARRAY": "Datum", "ANYENUM": "Datum", "ANYRANGE": "Datum",
    "ANYMULTIRANGE": "Datum", "ANYCOMPATIBLE": "Datum", "ANYCOMPATIBLEARRAY": "Datum",
    "ANYCOMPATIBLENONARRAY": "Datum", "ANYCOMPATIBLERANGE": "Datum", "ANYCOMPATIBLEMULTIRANGE": "Datum",
    "TRIGGER": "TriggerData *", "EVENT_TRIGGER": "EventTriggerData *", "FDW_ROUTINE": "FdwRoutine *",
    "INDEX_AM_ROUTINE": "IndexAmRoutine *", "TABLE_AM_ROUTINE": "TableAmRoutine *",
    "TSRANGECOLLATION": "Oid", "INTERNAL": "void *",
    "JSON": "text *", "JSONB": "jsonb *", "JSONB_P": "jsonb *",
    "XID": "TransactionId", "XID8": "FullTransactionId", "CID": "CommandId",
    "TID": "ItemPointerData *", "LSN": "XLogRecPtr",
}

MACRO_FUNC_PREFIX_BLACKLIST = (
    "PG_GETARG_", "PG_RETURN_", "PG_DETOAST_", "PG_FREE_IF_COPY", "PG_FUNCTION_INFO_V1",
    "PG_MODULE_MAGIC", "PG_ARGISNULL", "PG_RETURN_NULL", "PG_ENSURE_ERROR_CLEANUP",
    "PG_END_TRY", "PG_TRY", "PG_CATCH", "DatumGet", "GetDatum", "Int16Get", "Int32Get",
    "Int64Get", "BoolGet", "Float4Get", "Float8Get", "PointerGet", "ObjectIdGet",
    "CStringGet", "NameGet", "TextDatumGet", "DirectFunctionCall", "InvokeFunctionCall",
    "elog", "ereport", "palloc", "pfree", "repalloc", "memcpy", "memcmp", "strcpy",
    "strncpy", "snprintf", "fprintf", "printf", "strcat", "strlen", "strcmp", "Assert",
)

# ======================================================
# ----------------- 辅助函数 -----------------
# ======================================================
def log(msg): print(f"⚙️ {msg}")

def clean_text(s): return s.strip().replace("\\", "") if s else s

def safe_get(obj, attr, default=None):
    try: return getattr(obj, attr)
    except Exception: return default

def is_system_header(path):
    return path and any(path.startswith(p) for p in ("/usr/include", "/usr/lib", "/lib/"))

def is_macroish_function_name(name):
    return any(name.startswith(p) for p in MACRO_FUNC_PREFIX_BLACKLIST)

def get_default_value(type_kind, spelling):
    ts = spelling.lower()
    if "int" in ts: return 0
    if "float" in ts or "double" in ts: return 0.0
    if "char" in ts and "*" in spelling: return ""
    if type_kind == clang.cindex.TypeKind.POINTER: return "NOT_NULL"
    if type_kind == clang.cindex.TypeKind.BOOL: return False
    return None

# ======================================================
# ----------- 通用注释提取函数 --------------------------
# ======================================================
def extract_comment_above(c_file_path, symbol_name, func_decl_line_hint=None):
    """
    向上回溯查找 symbol_name 定义上方最近的块注释或行注释。
    改进点：
    - 允许注释与定义之间有至多 3 行空行
    - 支持多行块注释
    - 自动处理 1-based 行号
    """
    try:
        with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        # ---- 确定函数定义起始行号（从0开始）----
        if func_decl_line_hint:
            start_line = func_decl_line_hint - 1
        else:
            start_line = None
            for idx, line in enumerate(lines):
                if re.search(rf'\b{re.escape(symbol_name)}\b', line):
                    start_line = idx
                    break

        if start_line is None or start_line <= 0:
            return ""

        comment_lines = []
        i = start_line - 1
        in_block = False
        empty_lines = 0

        while i >= 0:
            line = lines[i].rstrip()

            # 跳过合理数量的空行
            if line.strip() == "":
                empty_lines += 1
                if empty_lines > 3:
                    break
                i -= 1
                continue

            # 进入块注释尾部
            if not in_block and "*/" in line:
                in_block = True
                comment_lines.append(line)
            elif in_block:
                comment_lines.append(line)
                if "/*" in line:
                    break

            # 单行注释
            elif re.match(r'\s*//', line):
                comment_lines.append(line)

            # 如果碰到非注释的内容则停止
            elif not in_block:
                break

            i -= 1

        if not comment_lines:
            return ""

        # ---- 清理注释内容 ----
        comment_lines.reverse()
        comment = "\n".join(comment_lines)
        comment = re.sub(r"/\*+|\*+/", "", comment)
        comment = re.sub(r"//+", "", comment)
        comment = re.sub(r"[\r\n\t]+", " ", comment)
        comment = re.sub(r" {2,}", " ", comment)
        return comment.strip()

    except Exception as e:
        print(f"❌ extract_comment_above error: {e}")
        return ""

# ======================================================
# ----------- typedef / doc 提取 ------------------------
# ======================================================
def extract_typedef_comment(filepath, typename):
    return extract_comment_above(filepath, typename)

def extract_doc_comment(filepath, funcname):
    return extract_comment_above(filepath, funcname)

def extract_direct_includes(filepath):
    incs, pat = [], re.compile(r'#\s*include\s*([<"])([^>"]+)([>"])')
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pat.match(line.strip())
            if m:
                incs.append(f"{m.group(1)}{m.group(2)}{m.group(3)}")
    return incs

# ======================================================
# ----------- typedef 提取函数 --------------------------
# ======================================================
def get_typedef_block(filepath, typename, depth=0, max_depth=3, visited=None):
    if visited is None:
        visited = set()
    if depth > max_depth or typename in visited:
        return None
    visited.add(typename)
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        content_clean = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
        typedef_blocks = re.findall(r"typedef\s+[^;]+;", content_clean, flags=re.DOTALL)
        for block in typedef_blocks:
            if re.search(rf"\b{re.escape(typename)}\b\s*;", block):
                return clean_text(re.sub(r"\s+", " ", block))
        return None
    except Exception:
        return None

# ======================================================
# ----------- 提取宏定义（带注释） ----------------------
# ======================================================
def extract_macros(c_file_path):
    """
    提取 #define 宏定义及其前方注释。
    - 自动去掉版权信息 / 过长注释
    - 支持多行宏值拼接
    - 保留简洁有效注释
    """
    macros = []
    try:
        with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 🔹 支持宏定义跨多行（带反斜线）
        # 先合并多行
        content = re.sub(r'\\\n', ' ', content)

        # 🔹 匹配形如：
        # /* comment */ #define MACRO(x) something
        pattern = re.compile(
            r'(?:(?P<comment>/\*[\s\S]*?\*/|//[^\n]*))?\s*'
            r'#define\s+(?P<name>[A-Za-z_]\w*(?:\([^\)]*\))?)\s+(?P<value>[^\n]+)',
            flags=re.MULTILINE
        )

        def clean_comment(raw_comment):
            """去除多余符号和空白"""
            if not raw_comment:
                return ""
            c = re.sub(r"/\*+|\*+/", "", raw_comment)
            c = re.sub(r"//+", "", c)
            c = re.sub(r"[\r\n\t]+", " ", c)
            c = re.sub(r" {2,}", " ", c)
            return c.strip()

        def is_header_comment(c):
            """识别文件头版权注释或无意义大块"""
            if not c:
                return False
            lower_c = c.lower()
            bad_kw = [
                "copyright", "postgresql", "global development group",
                "regents", "university", "src/", "portions"
            ]
            return any(k in lower_c for k in bad_kw)

        seen_names = set()
        for m in pattern.finditer(content):
            name = m.group("name").strip()
            value = m.group("value").strip()
            comment = clean_comment(m.group("comment"))

            # 🔸 跳过明显是文件头注释
            if is_header_comment(comment):
                comment = ""

            # 🔸 截断过长注释
            if len(comment) > 200:
                comment = comment[:200] + "..."

            # 🔸 去重
            if name in seen_names:
                continue
            seen_names.add(name)

            macros.append({
                "name": name,
                "value": value,
                "comment": comment
            })

        return macros

    except Exception as e:
        print(f"❌ extract_macros error: {e}")
        return []

# ======================================================
# ----------- 提取 struct / enum 定义（带注释） ----------
# ======================================================

def extract_structs(c_file_path):
    """
    提取 struct / enum 定义及其上方注释。
    自动过滤掉文件头版权段。
    """
    structs = []
    try:
        with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        typedef_pattern = re.compile(
            r'(?:(?P<comment>/\*[\s\S]*?\*/)\s*)?typedef\s+(?P<kind>struct|enum)\s+(\w+)?\s*\{(?P<body>[\s\S]*?)\}\s*(?P<name>\w+)\s*;',
            flags=re.MULTILINE
        )
        direct_pattern = re.compile(
            r'(?:(?P<comment>/\*[\s\S]*?\*/)\s*)?(?P<kind>struct|enum)\s+(?P<name>\w+)\s*\{(?P<body>[\s\S]*?)\}\s*;',
            flags=re.MULTILINE
        )

        def clean_comment(c):
            if not c:
                return ""
            c = re.sub(r"/\*|\*/", "", c)
            c = re.sub(r"[\r\n\t]+", " ", c)
            c = re.sub(r" {2,}", " ", c)
            return c.strip()

        def is_file_header_comment(c):
            keywords = [
                "copyright", "postgresql", "identification",
                "src/", "regents", "group", "portions", "university"
            ]
            lower_c = c.lower()
            return any(k in lower_c for k in keywords)

        def get_line_num(pos):
            return content[:pos].count("\n") + 1

        for m in typedef_pattern.finditer(content):
            kind = m.group("kind")
            name = m.group("name").strip()
            body = m.group("body").strip()
            comment = clean_comment(m.group("comment"))
            if comment and is_file_header_comment(comment):
                comment = ""
            if not comment:
                decl_line = get_line_num(m.start())
                comment = extract_comment_above(c_file_path, name, func_decl_line_hint=decl_line)
            structs.append({"name": name, "kind": kind, "body": body, "comment": comment})

        for m in direct_pattern.finditer(content):
            kind = m.group("kind")
            name = m.group("name").strip()
            body = m.group("body").strip()
            comment = clean_comment(m.group("comment"))
            if comment and is_file_header_comment(comment):
                comment = ""
            if not comment:
                decl_line = get_line_num(m.start())
                comment = extract_comment_above(c_file_path, name, func_decl_line_hint=decl_line)
            structs.append({"name": name, "kind": kind, "body": body, "comment": comment})

        return structs
    except Exception as e:
        print(f"❌ extract_structs error: {e}")
        return []

# ======================================================
# ----------- 提取文件内全局变量（带注释） ----------------
# ======================================================
def extract_file_globals(c_file_path):
    """
    精准提取真正的文件级全局变量（排除函数内部声明、控制语句、局部变量）
    """
    try:
        with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 1️⃣ 去掉函数体（包括 static inline 多行定义）
        no_funcs = re.sub(
            r'^[\t ]*(?:static\s+)?[A-Za-z_][\w\s\*]+\([^)]*\)\s*\{[\s\S]*?\}\s*',
            '', content, flags=re.MULTILINE
        )

        # 2️⃣ 去掉 preprocessor 和注释
        no_funcs = re.sub(r'#.*', '', no_funcs)
        no_funcs = re.sub(r'/\*.*?\*/', '', no_funcs, flags=re.DOTALL)
        no_funcs = re.sub(r'//.*', '', no_funcs)

        globals_ = []
        pattern = re.compile(
            r'^\s*([A-Za-z_][A-Za-z0-9_\s\*\[\]]+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);',
            re.MULTILINE
        )

        for m in pattern.finditer(no_funcs):
            decl_type = m.group(1).strip()
            name = m.group(2).strip()
            init = m.group(3).strip()

            # 🚫 排除明显非全局定义
            if any(word in decl_type for word in ["if", "else", "for", "while", "switch"]):
                continue
            if name in ("true", "false", "NULL"):
                continue
            if decl_type.startswith("else") or decl_type.startswith("if"):
                continue
            if decl_type.strip().startswith(("const", "static")) and "typedef" not in decl_type:
                # static 在 PG 中经常用于内部函数变量声明，可能不是全局
                continue

            # 🚫 排除小写局部命名（大多数 PG 全局变量首字母大写）
            if name[0].islower() and not decl_type.startswith("extern"):
                continue

            comment = extract_comment_above(
                c_file_path, name,
                func_decl_line_hint=content[:m.start()].count("\n")
            )
            globals_.append({
                "name": name,
                "type": decl_type,
                "init": init,
                "declaration": m.group(0).strip(),
                "comment": comment
            })
        return globals_
    except Exception as e:
        print(f"extract_file_globals error: {e}")
        return []
# ======================================================
# ----------------- 主函数 -----------------
# ======================================================
def generate_seed_case(c_file_path, pg_src_path, target_function=None):
    index = clang.cindex.Index.create()
    args = get_pg_compiler_args(c_file_path, pg_src_path)
    print("📁 C file:", os.path.abspath(c_file_path))
    
    # 检查文件是否存在
    if not os.path.exists(c_file_path):
        raise Exception(f"❌ C文件不存在: {c_file_path}")
    
    # 检查是否为目录
    if os.path.isdir(c_file_path):
        raise Exception(f"❌ 提供的路径是目录而不是C文件: {c_file_path}\n"
                       f"💡 请提供原始的.c文件路径，而不是测试套件目录。\n"
                       f"   例如: /usr/src/postgresql/src/backend/utils/adt/int.c")
    
    # 检查是否为.c文件
    if not c_file_path.endswith('.c'):
        raise Exception(f"❌ 提供的文件不是.c文件: {c_file_path}\n"
                       f"💡 请提供原始的C源文件（.c扩展名）。")
    
    # 打印编译参数用于调试
    print(f"🔧 编译参数:")
    for arg in args[:10]:  # 只打印前10个参数
        print(f"   - {arg}")
    if len(args) > 10:
        print(f"   ... (共 {len(args)} 个参数)")
    
    # 尝试解析，捕获详细错误
    try:
        tu = index.parse(c_file_path, args=args)
    except Exception as e:
        print(f"❌ Clang解析失败: {e}")
        print(f"💡 可能的原因:")
        print(f"   1. C文件包含语法错误")
        print(f"   2. 缺少必要的头文件")
        print(f"   3. PostgreSQL源码路径不正确: {pg_src_path}")
        print(f"   4. 编译参数配置有误")
        raise
    
    # 检查是否有诊断信息（编译错误/警告）
    if tu.diagnostics:
        print(f"⚠️  发现 {len(tu.diagnostics)} 个诊断信息:")
        for diag in tu.diagnostics[:5]:  # 只显示前5个
            print(f"   - [{diag.severity}] {diag.spelling}")
            if diag.location.file:
                print(f"     位置: {diag.location.file.name}:{diag.location.line}:{diag.location.column}")
        if len(tu.diagnostics) > 5:
            print(f"   ... (还有 {len(tu.diagnostics) - 5} 个)")
    
    log(f"✅ Parsed TU: {c_file_path}")

    focal = None
    available_functions = []

    for node in tu.cursor.get_children():
        if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.is_definition():
            if node.location.file and node.location.file.name == c_file_path:
                available_functions.append(node.spelling)
                if target_function:
                    if node.spelling == target_function:
                        focal = node
                        break
                else:
                    if focal is None:
                        focal = node

    if not focal:
        print(f"📋 文件中的函数列表: {', '.join(available_functions)}")
        raise Exception(f"❌ Function '{target_function}' not found in {c_file_path}")

    print(f"🎯 目标函数: {focal.spelling}")
    func_start, func_end = focal.extent.start.offset, focal.extent.end.offset

    macros = extract_macros(c_file_path)
    structs = extract_structs(c_file_path)
    file_globals = extract_file_globals(c_file_path)

    inputs, seen_inputs = [], set()
    # 函数：递归提取类型的完整定义（body）
    def get_type_body(typ_name, tu_cursor, depth=0, max_depth=3, visited=None):
        """
        递归提取类型的完整定义，特别处理PostgreSQL的不透明类型
        
        Args:
            typ_name: 类型名称
            tu_cursor: 翻译单元游标
            depth: 当前递归深度
            max_depth: 最大递归深度
            visited: 已访问的类型集合（防止循环引用）
        
        Returns:
            str: 类型的完整定义文本
        """
        if visited is None:
            visited = set()
        
        # 防止无限递归和重复解析
        if depth > max_depth or typ_name in visited:
            return None
        
        # 跳过基本类型
        if not typ_name or typ_name in ['int', 'char', 'void', 'long', 'short', 'float', 'double', 
                                          'unsigned', 'signed', 'uint8', 'uint16', 'uint32', 'uint64',
                                          'int8', 'int16', 'int32', 'int64', 'size_t', 'uintptr_t']:
            return None
        
        visited.add(typ_name)
        result_definitions = []
        
        # 尝试在当前翻译单元中查找类型定义
        # 首先收集所有匹配的节点，优先选择完整定义（有body的）
        matching_nodes = []
        for node in tu_cursor.walk_preorder():
            if node.kind in [clang.cindex.CursorKind.STRUCT_DECL, 
                            clang.cindex.CursorKind.TYPEDEF_DECL,
                            clang.cindex.CursorKind.ENUM_DECL]:
                if node.spelling == typ_name or node.type.spelling == typ_name:
                    # 对于结构体，优先选择有定义体的（不是前向声明）
                    if node.kind == clang.cindex.CursorKind.STRUCT_DECL:
                        # 检查是否是完整定义（有成员）
                        has_members = any(child.kind == clang.cindex.CursorKind.FIELD_DECL 
                                        for child in node.get_children())
                        matching_nodes.append((node, has_members))
                    else:
                        matching_nodes.append((node, True))
        
        # 按优先级排序：有成员的结构体 > 没有成员的
        matching_nodes.sort(key=lambda x: x[1], reverse=True)
        
        for node, has_definition in matching_nodes:
            try:
                extent = node.extent
                if extent.start.file and extent.end.file:
                    with open(extent.start.file.name, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        start_off = extent.start.offset
                        end_off = extent.end.offset
                        
                        # 提取类型定义
                        type_def = content[start_off:end_off].strip()
                        
                        # 对于结构体，确保提取到完整的定义（包括结尾的分号或大括号）
                        if node.kind == clang.cindex.CursorKind.STRUCT_DECL:
                            # 如果定义不以 } 或 ; 结尾，尝试扩展到下一个分号
                            if not type_def.endswith('}') and not type_def.endswith(';'):
                                semicolon_pos = content.find(';', end_off)
                                if semicolon_pos != -1 and semicolon_pos - end_off < 10:
                                    type_def = content[start_off:semicolon_pos + 1].strip()
                        
                        # 跳过空定义或前向声明
                        if len(type_def) < 20 and not has_definition:
                            continue
                        
                        result_definitions.append(type_def)
                        
                        # 检查是否是指针typedef（不透明类型）
                        # 例如: typedef struct FunctionCallInfoBaseData *FunctionCallInfo
                        if node.kind == clang.cindex.CursorKind.TYPEDEF_DECL:
                            # 获取底层类型
                            underlying_type = node.underlying_typedef_type
                            if underlying_type.kind == clang.cindex.TypeKind.POINTER:
                                # 这是一个指针typedef，获取指向的类型
                                pointee_type = underlying_type.get_pointee()
                                pointee_decl = pointee_type.get_declaration()
                                if pointee_decl.spelling:
                                    # 递归解析底层结构体
                                    underlying_def = get_type_body(
                                        pointee_decl.spelling, 
                                        tu_cursor, 
                                        depth + 1, 
                                        max_depth, 
                                        visited
                                    )
                                    if underlying_def:
                                        result_definitions.append(f"\n// Underlying definition for {pointee_decl.spelling}:\n{underlying_def}")
                        
                        # 如果找到了有效的定义，返回结果
                        if result_definitions:
                            return '\n'.join(result_definitions)
            except Exception as e:
                log(f"Warning: Failed to extract type body for {typ_name}: {e}")
                pass
        
        return '\n'.join(result_definitions) if result_definitions else None
    
    def add_input(expr, typ, val):
        key = (expr, typ)
        if key not in seen_inputs:
            seen_inputs.add(key)
            # 提取类型的body（递归解析不透明类型）
            body = get_type_body(typ, tu.cursor)
            if body:
                log(f"✅ Extracted type body for {typ}: {len(body)} characters")
            inputs.append({"expr": expr, "type": typ, "value": val, "body": body})

    for arg in focal.get_arguments():
        val = get_default_value(arg.type.kind, arg.type.spelling)
        if "FunctionCallInfo" in arg.type.spelling:
            val = "NOT_NULL"
        add_input(arg.spelling, arg.type.spelling, val)

    with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
        full_text = f.read()
        func_text = full_text[func_start:func_end]

    for m in re.findall(r'(PG_GETARG_[A-Z0-9_]+)\s*\(\s*(\d+)\s*\)', func_text):
        macro, idx = m
        key = macro.split("_")[-1]
        add_input(f"arg_{idx}", PG_ARG_TYPE_MAP.get(key, "Datum"), None)

    outputs = []
    if focal.result_type.kind != clang.cindex.TypeKind.VOID:
        # 提取返回值类型的body
        ret_type_body = get_type_body(focal.result_type.spelling, tu.cursor)
        outputs.append({"expr": "returnValue", "type": focal.result_type.spelling, "value": None, "body": ret_type_body})

    stubins, typedefs = [], {}
    def add_typedef(name, decl, path):
        if name not in typedefs and decl:
            typedefs[name] = {
                "definition": decl,
                "path": path,
                "comment": extract_typedef_comment(path, name)
            }

    # -------- 提取函数调用 --------
    for node in focal.walk_preorder():
        if node.kind == clang.cindex.CursorKind.CALL_EXPR and node.referenced:
            ref = node.referenced
            name = ref.spelling or node.spelling
            if is_macroish_function_name(name):
                continue
            loc_file = safe_get(ref.location, "file")
            loc_path = loc_file.name if loc_file else None
            if loc_path and loc_path != c_file_path and not is_system_header(loc_path):
                stub_comment = extract_doc_comment(loc_path, name)
                
                # 提取函数签名作为body
                func_body = None
                try:
                    extent = ref.extent
                    if extent.start.file and extent.end.file:
                        with open(extent.start.file.name, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # 只提取函数声明/定义的第一行（函数签名）
                            start_line_off = extent.start.offset
                            # 查找到第一个 { 或 ; 为止
                            end_idx = content.find('{', start_line_off)
                            if end_idx == -1:
                                end_idx = content.find(';', start_line_off)
                            if end_idx != -1:
                                func_body = content[start_line_off:end_idx].strip()
                except:
                    pass
                
                stubins.append({
                    "expr": name,
                    "type": "function",
                    "path": loc_path,
                    "comment": clean_text(stub_comment) if stub_comment else "",
                    "body": func_body
                })
                decl_line = get_typedef_block(loc_path, name, max_depth=2)
                if decl_line:
                    add_typedef(name, decl_line, loc_path)

    # -------- 去重 stubins --------
    unique_stubins = []
    seen_stub = set()
    for s in stubins:
        if s["expr"] not in seen_stub:
            seen_stub.add(s["expr"])
            unique_stubins.append(s)
    stubins = unique_stubins

    includes = extract_direct_includes(c_file_path)
    desc = clean_text(
        extract_comment_above(
            c_file_path,
            focal.spelling,
            func_decl_line_hint=focal.location.line - 1  # ⚠️ 修正行号基准
        ) or "Generated seed case"
    )

    result = {
        "func": focal.spelling,
        "file": c_file_path,
        "cases": [{"desc": desc, "inputs": inputs, "outputs": outputs, "stubins": stubins}],
        "macros": macros,
        "structs": structs,
        "file_globals": file_globals,
        "direct_includes": includes,
        "type_definitions": typedefs,
        "func_code": func_text.strip(),
        "userVar": [],
        "defaultPTR": [],
        "ios": []
    }

    log(f"✅ Done: {focal.spelling}")
    return json.dumps(result, indent=4, ensure_ascii=False), args