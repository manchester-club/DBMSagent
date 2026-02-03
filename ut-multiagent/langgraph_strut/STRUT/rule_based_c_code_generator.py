import json
import os
import re
import clang.cindex

from get_dependencies import remove_function_declarations, remove_global_variable_assignments
from delete_useless_info import simplify_file
from util import get_args, get_file, write_file
from generator import case_generator, prompt_generator, opti_generator
from model import access_model
from test_case import make_case_list
from seed_case_generator import generate_seed_case

clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')

# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++ LOGIC FROM rule_based_c_code_generator.py (这部分逻辑不变) +++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def _format_value(value, var_type):
    if isinstance(value, str):
        value = value.replace('"', '\\"').replace('\n', '\\n')
        return f'"{value}"'
    if isinstance(value, bool): return "true" if value else "false"
    if 'float' in var_type or 'double' in var_type: return f"{float(value)}f" if 'float' in var_type else str(float(value))
    if isinstance(value, int): return str(value)
    return str(value)

def _get_assertion_macro(output):
    value = output.get('value')
    var_type = output.get('type', '').lower()
    if 'float' in var_type or 'double' in var_type or isinstance(value, float): return "ASSERT_FLOAT_EQ"
    if 'char *' in var_type or 'char*' in var_type or isinstance(value, str): return "ASSERT_STRING_EQ"
    return "ASSERT_EQ"

def _generate_stubs(case_list):
    stubs_code = "/* --- 桩函数定义 (Stub Function Definitions) --- */\n"
    stub_map = {}
    for i, case in enumerate(case_list):
        for stub_info in case.get('stubins', []):
            signature = stub_info.get("called function")
            if not signature: continue
            if signature not in stub_map: stub_map[signature] = {}
            stub_map[signature][i] = stub_info.get("changed variable", [])
    for signature, case_values in stub_map.items():
        match = re.match(r'([\w\s\*]+)\s+([\w]+)\s*\((.*)\)', signature)
        if not match: continue
        return_type, func_name, params = match.groups()
        stubs_code += f"{return_type} {func_name}({params}) {{\n    // Return different mock values based on the currently running test case\n"
        first_case = True
        for case_index, changed_vars in case_values.items():
            stubs_code += f"    {'if' if first_case else 'else if'} (g_test_case_index == {case_index}) {{\n"
            first_case = False
            for var in changed_vars:
                if var['expr'] == 'returnValue':
                    stubs_code += f"        return {_format_value(var['value'], var.get('type', ''))};\n"
            stubs_code += f"    }}\n"
        if return_type.strip() != "void": stubs_code += "    return 0; // Default return value\n"
        stubs_code += "}\n\n"
    return stubs_code

def _generate_test_case_functions(case_list, focal_function_name):
    test_functions_code = "/* --- 测试用例函数 (Test Case Functions) --- */\n"
    for i, case in enumerate(case_list):
        test_functions_code += f"void {focal_function_name}_test_{i}() {{\n    /* 1. 数据准备 (Data Preparation) */\n"
        declarations = set()
        pointer_allocations = []
        for var in case['inputs']:
            base_var = var['expr'].split('->')[0].split('.')[0].split('[')[0]
            base_var_type = next((v.get('type') for v in case['inputs'] if v['expr'] == base_var), None)
            if base_var_type and base_var not in declarations:
                 declarations.add(base_var)
                 test_functions_code += f"    {base_var_type} {base_var};\n"
                 if '*' in base_var_type:
                     struct_type = base_var_type.replace('*','').strip()
                     pointer_allocations.append(f"    {base_var} = ({base_var_type})malloc(sizeof({struct_type}));")
        if pointer_allocations: test_functions_code += "\n    // Pointer Memory Allocation\n" + "\n".join(pointer_allocations) + "\n"
        test_functions_code += "\n    /* 2. 输入值赋值 (Input Value Assignment) */\n"
        for var in case['inputs']:
            test_functions_code += f"    {var['expr']} = {_format_value(var['value'], var.get('type', ''))};\n"
        test_functions_code += "\n    /* 3. 测试执行 (Test Execution) */\n"
        input_params = [v['expr'] for v in case['inputs'] if '->' not in v['expr'] and '.' not in v['expr']]
        test_functions_code += f"    {focal_function_name}({', '.join(input_params)});\n"
        test_functions_code += "\n    /* 4. 结果验证 (Result Validation) */\n"
        for var in case['outputs']:
            test_functions_code += f"    {_get_assertion_macro(var)}({var['expr']}, {_format_value(var['value'], var.get('type', ''))});\n"
        test_functions_code += "}\n\n"
    return test_functions_code

def _generate_main_runner(case_list, focal_function_name):
    runner_code = "/* --- 测试运行器 (Test Runner) --- */\nint main() {\n"
    for i in range(len(case_list)):
        runner_code += f'    printf("--- Running {focal_function_name}_test_{i} ---\\n");\n'
        runner_code += f"    g_test_case_index = {i};\n"
        runner_code += f"    {focal_function_name}_test_{i}();\n"
        runner_code += f'    printf("--- Test {focal_function_name}_test_{i} Passed ---\\n\\n");\n'
    runner_code += "    return 0;\n}\n"
    return runner_code

def generate_c_test_file(case_list, focal_function_name, context_code):
    headers = """
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <math.h>
/* --- Simple Assertion Framework --- */
#define ASSERT_EQ(actual, expected) \\
    if ((actual) != (expected)) { \\
        printf("Assertion failed: %s == %s, file %s, line %d. Actual: %d, Expected: %d\\n", #actual, #expected, __FILE__, __LINE__, (int)actual, (int)expected); \\
        exit(1); \\
    }
#define ASSERT_FLOAT_EQ(actual, expected) \\
    if (fabs((actual) - (expected)) > 1e-6) { \\
        printf("Assertion failed: %s == %s, file %s, line %d. Actual: %f, Expected: %f\\n", #actual, #expected, __FILE__, __LINE__, actual, expected); \\
        exit(1); \\
    }
#define ASSERT_STRING_EQ(actual, expected) \\
    if (strcmp((actual), (expected)) != 0) { \\
        printf("Assertion failed: %s == %s, file %s, line %d. Actual: \\"%s\\", Expected: \\"%s\\"\\n", #actual, #expected, __FILE__, __LINE__, actual, expected); \\
        exit(1); \\
    }
int g_test_case_index = 0;
"""
    stubs = _generate_stubs(case_list)
    test_functions = _generate_test_case_functions(case_list, focal_function_name)
    main_runner = _generate_main_runner(case_list, focal_function_name)
    return (headers + "\n/* --- 被测代码上下文 (Code Under Test Context) --- */\n" + context_code + "\n\n" + stubs + test_functions + main_runner)

# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++ 主流程逻辑 (main.py) 开始 +++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

conversation_history = []

def simplify(input_path, output_path, pg_src_path):
    """
    通过传递 pg_src_path 来简化 C 源文件。
    """
    remove_function_declarations(input_path, output_path, pg_src_path)
    remove_global_variable_assignments(output_path, output_path, pg_src_path)
    simplify_file(output_path, pg_src_path)

def main():
    function_path, _, uncover_path = get_args()
    dir_path = os.path.dirname(function_path)
    input_path = os.path.join(dir_path, 'input.txt')
    output_path = os.path.join(dir_path, 'output.txt')

    # 定义PG源码根目录
    pg_src_path = os.getenv('PG_SRC_PATH', '/postgres')
    print(f"Using PostgreSQL source path: {pg_src_path}")

    try:
        print("Step 1: Automatically generating seed case from source file...")
        case_content = generate_seed_case(function_path, pg_src_path)
        print("Seed case generated successfully.")
    except Exception as e:
        print(f"Error during seed case generation: {e}")
        return

    print("\nStep 2: Simplifying C code to create minimal context...")
    simplify(function_path, function_path, pg_src_path)
    function_context = get_file(function_path)
    print("C code simplified.")

    case, default_PTR, has_stub = case_generator(case_content)
    
    fun_name = os.path.splitext(os.path.basename(function_path))[0]
    ind = fun_name.find('_build')
    if ind != -1:
        fun_name = fun_name[:ind]

    #model = 'GPT-4o'
    model = 'Gemini'
    
    print(f"\nStep 3: Generating test cases for function '{fun_name}' using model '{model}'...")
    if not uncover_path:
        prompt = prompt_generator(function_context, case, has_stub)
        resp = access_model(prompt, model)
    else:
        print("   (Optimization Mode: Reading uncovered branches info...)")
        uncover_content = get_file(uncover_path)
        uncover_info = json.loads(uncover_content)
        con = ''.join([f"{i}. branch: {b['branch']}: {b['condition']} condition uncovered.\\n" for i, b in enumerate(uncover_info['branches'], 1)])
        question = get_file(input_path)
        answer = get_file(output_path)
        conversation_history.extend([f'User:{question}', f'AI:{answer}'])
        prompt = ''.join(conversation_history) + opti_generator() + con
        resp = access_model(prompt, model)
    
    print("LLM response received.")

    print("\nStep 4: Parsing LLM response into structured test cases...")
    case_list = make_case_list(resp, has_stub, default_PTR)
    print(f"Parsed {len(case_list)} test cases.")

    print("\nStep 5: Generating complete C test file from structured cases...")
    c_test_code = generate_c_test_file(case_list, fun_name, function_context)

    output_c_file_path = os.path.join(dir_path, f"{fun_name}_test.c")
    try:
        with open(output_c_file_path, "w", encoding="utf-8") as f:
            f.write(c_test_code)
        print("\n--- Generation Complete! ---")
        print(f"Successfully generated C test file at: {output_c_file_path}")
    except Exception as e:
        print(f"Error writing C test file: {e}")
        return

    if not uncover_path:
        write_file(input_path, prompt)
        write_file(output_path, resp)

if __name__ == "__main__":
    main()