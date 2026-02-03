# -*- coding: utf-8 -*-
"""
本模块负责生成与大语言模型（LLM）交互的 Prompts，并处理相关的测试用例数据结构。
"""

import json

# 文件: generator.py

def case_generator(case_content):
    """
    从静态分析生成的种子案例JSON中提取并格式化第一个案例，作为LLM的示例。
    """
    case_content = json.loads(case_content)
    cases = case_content.get('cases', [])
    if not cases:
        raise ValueError("种子用例内容中缺少 'cases' 列表或列表为空。")

    case_0 = cases[0]
    case = {'desc': 'description text'}
    case['inputs'] = case_0.get('inputs', [])
    case['outputs'] = case_0.get('outputs', [])
    
    # 将顶层函数信息添加到用例模板中
    case['func'] = case_content.get('func', '')
    case['file'] = case_content.get('file', '')
    # 将函数注释从第一个case中提取到顶层，方便prompt_generator使用
    case['func_desc'] = case_0.get('desc', '')
    
    # 将所有新增的JSON字段添加到用例模板中
    case['direct_includes'] = case_content.get('direct_includes', [])
    case['type_definitions'] = case_content.get('type_definitions', {})
    case['macros'] = case_content.get('macros', [])
    case['structs'] = case_content.get('structs', [])
    case['file_globals'] = case_content.get('file_globals', [])
    case['func_code'] = case_content.get('func_code', '')
    # 包含完整的cases数组，但过滤掉stubins字段并调整结构
    filtered_cases = []
    for c in cases:
        filtered_case = {k: v for k, v in c.items() if k != 'stubins'}
        # 将_info放在case内部的最后
        filtered_case["_info"] = "Seed test case with inferred inputs/outputs"
        filtered_cases.append(filtered_case)
    case['cases'] = filtered_cases
    
    case_stubins = case_0.get('stubins', [])
    has_stub = bool(case_stubins)
    if has_stub:
        case['stubins'] = case_stubins  # 为prompt_generator提供stubins信息
        
    default_PTR = case_content.get('defaultPTR', [])
    
    return json.dumps(case, indent=4), default_PTR, has_stub


def prompt_generator(fun_context, case_template, has_stub: bool):
    """
    根据函数上下文和种子案例，生成引导LLM的高质量Prompt。
    使用结构化的依赖图和严格的命名规则。

    Args:
        fun_context (str): 被测函数的C代码及其上下文（现在主要用于兼容性，实际内容来自case_template）。
        case_template (str): JSON格式的单个测试用例模板，包含所有必要信息。
        has_stub (bool): 是否包含桩函数。

    Returns:
        str: 构造完成的、准备发送给LLM的完整Prompt。
    """
    
    # 基础Prompt模板
    base_prompt = (
        "PostgreSQL C Function Test Generation\n\n"
        "You are an expert PostgreSQL core developer and test engineer.\n"
        "Follow PostgreSQL backend coding conventions and testing framework behavior strictly.\n"
        "Your task is to generate a single, fully compilable PostgreSQL regression test C source file for a low-level backend C function (e.g., from src/backend/utils/adt/int.c).\n\n"
        "Output only valid C source code (no Markdown or meta explanations; inline C comments are allowed).\n\n"
        "---\n\n"
        "Input Context\n\n"
        "You will receive all necessary information as a single structured JSON dependency graph, containing:\n\n"
        "\t•\tThe target PostgreSQL function code and metadata (macros, structs, typedefs, includes, etc.).\n\n"
        "\t•\tAny external dependencies that require mocking/stubbing.\n\n"
        "\t•\tOptional seed test cases extracted from static analysis to guide realistic test design.\n\n"
        "The JSON is self-descriptive through inline _info comments.\n\n"
        "Use it directly to understand the function, its dependencies, and seed test cases.\n\n\n"
    )
    
    case_data = json.loads(case_template)
    
    # 从case_template中提取所有必要的上下文信息
    func_name = case_data.get('func', 'unknown_function')
    file_path = case_data.get('file', '')
    func_code = case_data.get('func_code', '')
    func_desc = case_data.get('func_desc', '')
    macros = case_data.get('macros', [])
    structs = case_data.get('structs', [])
    file_globals = case_data.get('file_globals', [])
    direct_includes = case_data.get('direct_includes', [])
    type_definitions = case_data.get('type_definitions', {})
    cases = case_data.get('cases', [])
    
    # 提取桩函数信息
    stubins = case_data.get('stubins', [])
    
    # 构建依赖图JSON - 按逻辑分组组织，包含内联注释
    dependency_graph = {
        "func": {
            "name": func_name,
            "file": file_path,
            "func_code": func_code,
            "desc": func_desc,

            "direct_includes": direct_includes,
            "macros": macros,
            "structs": structs,
            "type_definitions": type_definitions,
            "file_globals": file_globals,

            "cases": cases
        },
        "dependencies": []  # External functions called by target function - need to be stubbed/mocked
    }
    
    # 构建外部依赖函数列表
    if stubins and has_stub:
        for stub in stubins:
            dependency_graph["dependencies"].append({
                "_info": "External function that needs to be stubbed for testing",
                "func_name": stub.get('expr', ''),  # 外部函数名
                "stub": stub.get('body', ''),       # 桩函数实现
                "path": stub.get('path', ''),       # 函数声明路径
                "comment": stub.get('comment', '')  # 函数注释
            })
    
    # 构建Dependency Graph部分
    json_content = json.dumps(dependency_graph, indent=2)
    dependency_graph_str = f"""Example Dependency Graph

{json_content}



Test File Generation Requirements

\t1.\tGenerate a Valid PostgreSQL C Source File

\t•\tOutput only valid C source code (no Markdown or external explanations; inline C comments are allowed).

\t•\tInclude all headers in direct_includes plus required PostgreSQL headers (postgres.h, fmgr.h, utils/builtins.h, etc.).

\t•\tRegister SQL-callable functions with PG_FUNCTION_INFO_V1().

\t2.\tDesign Realistic and Diverse Test Cases

\t•\tUse function logic and seed cases as guidance.

\t•\tInclude normal, boundary, and error inputs.

\t•\tUse PostgreSQL-specific types (int16, int32, Oid, Datum, etc.).

\t•\tSimulate runtime errors (NULL input, overflow, invalid format).

\t3.\tImplement Stubs for Dependencies

\t•\tImplement static mock functions for all items listed under dependencies.

\t•\tEach stub should return realistic values and enable error path coverage.

\t4.\tIntegrate with pg_regress

\t•\tThe test must compile and run under PGXS using a Makefile like:

MODULES = test_int
REGRESS = test_int
USE_PGXS = 1
include $(PGXS)

\t•\tThe SQL entry point must be callable via:

SELECT test_[TARGET_FUNC]();


\t5.\tFollow PostgreSQL Coding Conventions



\t•\t4-space indentation, no tabs.

\t•\tUse elog(INFO, ...) for output.

\t•\tHandle exceptions with PG_TRY / PG_CATCH.

\t•\tSQL-callable functions must end with PG_RETURN_VOID().

⸻

Mandatory Naming Rule

\t•\tFunction Under Test (UUT):

Include the full body of the target function but rename it as my_[TARGET_FUNC]()

(e.g., int2in() → my_int2in()).

\t•\tTest Driver:

The test logic must be implemented in a separate function named test_[TARGET_FUNC]()

(e.g., test_int2in()).

\t•\tCoverage Requirement:

test_[TARGET_FUNC]() must directly call my_[TARGET_FUNC]() at least once.

If it does not, the output is non-compliant (coverage cannot be computed).
"""

    # 完整的示例
    complete_example = f"""
The example below is illustrative only. The model must regenerate equivalent code dynamically for the provided target function.
Illustrative Example (for reference only — do not copy verbatim)


1. Test C File:

#include "postgres.h"

#include "fmgr.h"
// Other PostgreSQL internal headers
#include "catalog/pg_type.h"
#include "common/int.h"
#include "funcapi.h"
#include "libpq/pqformat.h"
#include "nodes/nodeFuncs.h"
#include "nodes/supportnodes.h"
#include "optimizer/optimizer.h"
#include "utils/array.h"
#include "utils/builtins.h"
// C standard library headers
#include <ctype.h>
#include <limits.h>
#include <math.h>

/*
 * test_int2not.c
 *
 * A regression test for the PostgreSQL backend function int2not,
 * which is found in src/backend/utils/adt/int.c.
 *
 * This test file is designed to be compiled as a PostgreSQL extension
 * and run via the pg_regress framework.
 */

PG_MODULE_MAGIC;

Datum my_int2not(PG_FUNCTION_ARGS);  // Renamed function
Datum test_int2not(PG_FUNCTION_ARGS);  // Test driver function

PG_FUNCTION_INFO_V1(my_int2not);  // Renamed function
PG_FUNCTION_INFO_V1(test_int2not);  // Test driver function

Datum
my_int2not(PG_FUNCTION_ARGS)  // Renamed function
{{
    int16 arg1 = PG_GETARG_INT16(0);
    elog(INFO, "Running my_int2not with input: %d", arg1);
    PG_RETURN_INT16(~arg1);
}}

static void
run_single_test(const char *test_name, int16 input_val)
{{
    FunctionCallInfo fcinfo;
    Datum result_datum;
    int16 result_val;
    int16 expected_val;
    fcinfo = (FunctionCallInfo) palloc0(SizeForFunctionCallInfo(1));
    fcinfo->nargs = 1;
    fcinfo->args[0].value = Int16GetDatum(input_val);
    fcinfo->args[0].isnull = false;
    expected_val = ~input_val;
    result_datum = my_int2not(fcinfo);  // Call renamed function
    result_val = DatumGetInt16(result_datum);
    if (result_val == expected_val)
        elog(INFO, "✅ Test '%s': my_int2not(%d) -> %d. PASSED.", test_name, input_val, result_val);
    else
        elog(WARNING, "❌ Test '%s': my_int2not(%d) -> %d, expected %d. FAILED.", test_name, input_val, result_val, expected_val);
    pfree(fcinfo);
}}

Datum
test_int2not(PG_FUNCTION_ARGS)  // Test driver function
{{
    elog(INFO, "--- Running regression tests for my_int2not ---");
    run_single_test("Positive number", 5);
    run_single_test("Negative number", -42);
    run_single_test("Zero", 0);
    run_single_test("Minus one", -1);
    run_single_test("INT16_MAX", INT16_MAX);
    run_single_test("INT16_MIN", INT16_MIN);
    run_single_test("Positive number 2", 1024);
    run_single_test("Negative number 2", -1025);
    elog(INFO, "--- Regression tests for my_int2not complete ---");
    PG_RETURN_VOID();
}}

2. Test SQL File:

-- Complain if script is sourced directly in psql
\\echo Use "CREATE EXTENSION test_int2not" to load this file. \\quit

-- Bind C function test_int2not (our test entry point)
CREATE FUNCTION test_int2not()
RETURNS void
AS 'test_int2not', 'test_int2not'
LANGUAGE C STRICT;

-- Execute the test function to perform coverage testing
SELECT test_int2not();
"""

    # 组合完整的prompt
    full_prompt = base_prompt + dependency_graph_str + complete_example

    return full_prompt


def opti_generator(previous_code=None, error_info=None):
    """
    为覆盖率优化场景生成追加的Prompt。
    
    Args:
        previous_code (str): 上一轮LLM生成的测试代码
        error_info (str): 运行测试套件后的报错信息
    
    Returns:
        str: 优化场景的Prompt
    """
    base_prompt = (
        "\n\n=== OPTIMIZATION ROUND ===\n"
        "The previous test suite had some issues. I will provide:\n"
        "1. The previous test code you generated\n"
        "2. Any compilation/runtime errors encountered\n"
        "3. Uncovered branches that need to be addressed\n\n"
        "Please analyze the issues and generate an improved, complete test suite that:\n"
        "- Fixes any compilation or runtime errors\n"
        "- Covers the previously uncovered branches\n"
        "- Maintains all previously working test cases\n"
        "- Follows the same output format (complete C source file)\n\n"
    )
    
    if previous_code:
        base_prompt += f"**Previous Test Code:**\n```c\n{previous_code}\n```\n\n"
    
    if error_info:
        base_prompt += f"**Error Information:**\n```\n{error_info}\n```\n\n"
    
    base_prompt += "**Uncovered Path/Branch Information:**\n"
    
    return base_prompt


def aout_file_generator(case_list, func_name, defaultPTR):
    """
    根据case列表，对指针表达式进行后处理以生成特定格式（如aunit）的JSON。

    注意：此函数主要用于适配一个特定的、可能已废弃的测试框架格式，
    其核心逻辑是重写指针和数组访问的 'expr' 字段。

    Args:
        case_list (list): 从LLM解析出的测试用例列表。
        func_name (str): 被测函数名。
        defaultPTR (list): 静态分析识别出的指针类型参数列表。

    Returns:
        str: 经过后处理的、符合特定格式的JSON字符串。
    """
    processed_case = {'func': func_name, 'file': '', 'cases': []}

    for c in case_list:
        inputs = c.get('inputs', [])
        
        # 对输入表达式进行后处理
        for inp in inputs:
            expr = inp.get('expr', '')
            
            # 处理 '->' 指针访问
            if '->' in expr:
                parts = expr.split('->', 1)
                pointer_param = parts[0]
                
                base_var = pointer_param.split('[')[0]
                if any(item['expr'] == base_var for item in defaultPTR):
                    # 进行名称转换，例如 a[0] -> a_PTRTO[0]
                    new_pointer_param = pointer_param.replace('[', '_PTRTO[')
                    inp['expr'] = f"({new_pointer_param})->{parts[1]}"
            # 处理数组形式的指针
            elif '[' in expr:
                base_var = expr.split('[')[0]
                suffix = expr[expr.find('['):]
                if any(item['expr'] == base_var for item in defaultPTR):
                    inp['expr'] = f"{base_var}_PTRTO{suffix}"

        c['inputs'] = inputs
        processed_case['cases'].append(c)

    processed_case['userVar'] = []
    processed_case['defaultPTR'] = defaultPTR
    processed_case['ios'] = []

    return json.dumps(processed_case, indent=4)