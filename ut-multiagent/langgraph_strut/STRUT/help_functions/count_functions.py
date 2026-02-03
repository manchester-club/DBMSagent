import re
import sys

def analyze_c_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 去掉多行注释和单行注释
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.S)
    content = re.sub(r'//.*', '', content)

    # 匹配函数定义（包括 static 或非 static）
    func_pattern = re.compile(
        r'\b(static\s+)?[A-Za-z_]\w*\s+\**[A-Za-z_]\w*\s*\([^;{}]*\)\s*\{',
        flags=re.M
    )

    # 匹配 pg 日志/异常类宏调用（elog, ereport, unlikely）
    macro_pattern = re.compile(r'\b(elog|ereport|unlikely)\s*\(')

    # 结果统计变量
    static_count = 0
    non_static_count = 0
    total_func_lines = 0

    matches = list(func_pattern.finditer(content))

    for m in matches:
        func_start = m.end()
        func_decl = m.group()

        if 'static' in func_decl:
            static_count += 1
        else:
            non_static_count += 1

        # 查找函数体的结束位置（匹配花括号）
        brace_level = 1
        i = func_start
        while i < len(content) and brace_level > 0:
            if content[i] == '{':
                brace_level += 1
            elif content[i] == '}':
                brace_level -= 1
            i += 1

        # 提取函数体并统计行数
        func_body = content[func_start:i]
        total_func_lines += func_body.count('\n')

    # 统计所有宏调用（elog/ereport/unlikely）出现的行
    macro_lines = [
        idx + 1
        for idx, line in enumerate(content.splitlines())
        if macro_pattern.search(line)
    ]

    print(f"文件：{file_path}")
    print(f"总函数数：{len(matches)}")
    print(f"  static 函数：{static_count}")
    print(f"  非 static 函数：{non_static_count}")
    print(f"函数体总行数：{total_func_lines}")
    print(f"日志/异常宏调用行数（elog + ereport + unlikely）：{len(macro_lines)}")
    print(f"对应行号：{macro_lines}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python analyze_pg_cfile.py <C文件路径>")
    else:
        analyze_c_file(sys.argv[1])