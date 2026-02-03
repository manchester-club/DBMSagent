import argparse
import re

def read_file(file_path):
    """
    从给定路径读取文件内容，默认使用 UTF-8 编码。
    如果 UTF-8 解码失败，会尝试使用 gbk 编码作为备用。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f: # 默认使用 utf-8
            return f.read()
    except UnicodeDecodeError:
        # 备用编码，以处理可能存在的旧 gbk 文件
        with open(file_path, 'r', encoding='gbk') as f:
            return f.read()
    except FileNotFoundError as e:
        print(f"Error: File not found at {file_path}")
        raise e

def write_content(output_path, modified_content):
    """将修改后的内容以 UTF-8 编码写入文件，跳过空行。"""
    # 此函数已使用 utf-8，无需修改
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in modified_content.splitlines():
            if line.strip():
                f.write(line + '\n')

def write_file(path, content):
    """将内容以 UTF-8 编码写入文件。"""
    # 修改：默认编码改为 utf-8
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def get_args():
    """
    解析命令行参数。
    支持多种使用方式：
    1. 初始生成：python main.py file.c
    2. 指定函数：python main.py file.c -f function_name
    3. 优化模式：python main.py file.c -f function_name uncover_branches.json
    4. 简单优化：python main.py file.c -f function_name (基于之前的测试结果)
    """
    parser = argparse.ArgumentParser(description="使用 STRUT 方法论为 C 函数生成单元测试。")
    parser.add_argument('fun_path', type=str, help="包含待测函数的 C 源文件路径。")
    parser.add_argument('uncover_path', type=str, nargs='?', default=None, 
                        help="（可选）包含未覆盖分支信息的 JSON 文件路径，用于优化。如果不提供，将基于之前的测试结果进行通用优化。")
    parser.add_argument('--function', '-f', type=str, default=None,
                        help="（可选）指定要生成测试的特定函数名。")
    parser.add_argument('--optimize', '-o', action='store_true',
                        help="（可选）强制进入优化模式，即使没有提供uncover_branches.json。")
    args = parser.parse_args()

    function_path = args.fun_path
    target_function = args.function
    uncover_path = args.uncover_path if args.uncover_path else ''
    
    # 如果使用了 --optimize 标志，但没有提供 uncover_path，设置一个标记
    if args.optimize and not uncover_path:
        uncover_path = 'FORCE_OPTIMIZE'
    
    return function_path, uncover_path, target_function

def get_file(path: str):
    """
    按 'utf-8' 编码读取文件。
    """
    # 修改：默认编码改为 utf-8
    with open(path, encoding='utf-8') as f:
        return f.read()

def determine_type(input_str):
    """根据输入字符串的格式判断其基本数据类型。"""
    # 此函数不涉及文件编码，无需修改
    if re.fullmatch(r'-?\d+', input_str):
        return "Integer"

    if re.fullmatch(r'-?0[xX][0-9a-fA-F]+|"(-?0[xX][0-9a-fA-F]+)"', input_str):
        return "Hexadecimal"

    if re.fullmatch(r'-?\d+\.\d+', input_str):
        return "Float"

    if re.fullmatch(r"'(\\?.)'", input_str):
        return "Character"

    if re.fullmatch(r'"[^"]*"', input_str):
        return "String"

    return "Unknown"