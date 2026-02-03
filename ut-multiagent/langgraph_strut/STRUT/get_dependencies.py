import clang.cindex
from clang.cindex import Index, CursorKind
from util import read_file, write_content
from pg_clang_helper import get_pg_compiler_args

def remove_function_declarations(input_path, output_path, pg_src_path, compiler_args=None):
    index = clang.cindex.Index.create()
    if compiler_args is None:
        args = get_pg_compiler_args(input_path, pg_src_path) # 注入编译参数
    else:
        args = compiler_args
    code = read_file(input_path)
    unsaved_files = [(input_path, code)]
    tu = index.parse(input_path, args=args, unsaved_files=unsaved_files)

    remove_ranges = []

    function_count = 0
    declaration_count = 0
    definition_count = 0
    
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind == CursorKind.FUNCTION_DECL:
            function_count += 1
            if cursor.is_definition():
                definition_count += 1
                if function_count <= 5:  # 只显示前5个
                    print(f"🔍 [remove_function_declarations] 函数定义: {cursor.spelling} at {cursor.extent.start.offset}-{cursor.extent.end.offset}")
            else:
                declaration_count += 1
                if function_count <= 5:  # 只显示前5个
                    print(f"🔍 [remove_function_declarations] 函数声明: {cursor.spelling} at {cursor.extent.start.offset}-{cursor.extent.end.offset}")
                
                start_offset = cursor.extent.start.offset
                end_offset = cursor.extent.end.offset

                while end_offset < len(code) and code[end_offset] != ';':
                    end_offset += 1
                if end_offset < len(code):
                    end_offset += 1
                
                # 避免重复添加相同的范围
                range_tuple = (start_offset, end_offset)
                if range_tuple not in remove_ranges:
                    remove_ranges.append(range_tuple)
    
    print(f"🔍 [remove_function_declarations] 统计: 总函数 {function_count}, 定义 {definition_count}, 声明 {declaration_count}, 将移除 {len(remove_ranges)} 个范围")

    remove_ranges.sort(reverse=True)

    modified_code = code
    for start_offset, end_offset in remove_ranges:
        # 用单个换行符替换被移除的内容，保持行号结构
        # print(f"🔍 [remove_function_declarations] 移除范围: {start_offset}-{end_offset}")
        modified_code = modified_code[:start_offset] + '\n' + modified_code[end_offset:]
    write_content(output_path, modified_code)
    return modified_code

def remove_global_variable_assignments(input_path, output_path, pg_src_path, compiler_args=None):
    index = Index.create()
    if compiler_args is None:
        args = get_pg_compiler_args(input_path, pg_src_path) # 注入编译参数
    else:
        args = compiler_args
    code = read_file(input_path)
    unsaved_files = [(input_path, code)]
    translation_unit = index.parse(input_path, args=args, unsaved_files=unsaved_files)

    if not translation_unit:
        return ""

    lines_to_remove = []

    def visit_node(cursor, parent):
        if cursor.kind == CursorKind.VAR_DECL:
            if cursor.lexical_parent.kind == CursorKind.TRANSLATION_UNIT:
                tokens = list(cursor.get_tokens())
                equal_token = None
                for token in tokens:
                    if token.spelling == '=':
                        equal_token = token
                        break
                if equal_token:
                    start_loc = equal_token.extent.start
                    end_loc = tokens[-1].extent.start
                    lines_to_remove.append((start_loc.line, start_loc.column, end_loc.line, end_loc.column))

        for child in cursor.get_children():
            visit_node(child, cursor)

    root_cursor = translation_unit.cursor
    visit_node(root_cursor, None)

    code_lines = code.splitlines()

    # 恢复为您的原始逻辑：基于行列信息修改
    for start_line, start_col, end_line, end_col in sorted(lines_to_remove, reverse=True):
        if start_line == end_line:
            code_lines[start_line - 1] = (code_lines[start_line - 1][:start_col - 1] +
                                          code_lines[start_line - 1][end_col:])
        else:
            code_lines[start_line - 1] = code_lines[start_line - 1][:start_col - 1]
            for line in range(start_line, end_line - 1):
                code_lines[line] = ""
            code_lines[end_line - 1] = code_lines[end_line - 1][end_col + 1:]

    new_code = "\n".join(code_lines)
    write_content(output_path, new_code)
    return new_code