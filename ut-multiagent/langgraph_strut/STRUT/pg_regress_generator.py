# pg_regress_generator.py
import os
import re

"""
修改说明：
- 原来的逻辑：LLM生成JSON格式的测试用例 → 脚本解析JSON → 组装成C测试文件
- 新的逻辑：LLM直接生成可运行的C代码 → 脚本直接使用C代码生成测试套件

主要变化：
1. generate_pg_regress_suite() 现在接收 llm_generated_c_code 而不是 case_list
2. 不再需要 _generate_c_source() 函数来组装C代码
3. 直接将LLM生成的C代码写入测试文件
4. SQL、Makefile、Control文件的生成逻辑保持不变
"""


def _format_value_for_c(value, var_type):
    """将 Python 值格式化为 C 代码中的字面量。"""
    if isinstance(value, str):
        # 对字符串进行转义，以安全地插入C代码
        value = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        # 检查是否是 'NULL' 字符串，若是，则不加引号
        if value == "NULL":
            return "NULL"
        return f'"{value}"'
    if isinstance(value, bool): return "true" if value else "false"
    if 'float' in var_type.lower() or 'double' in var_type.lower() or isinstance(value, float): return f"{float(value)}"
    if isinstance(value, int): return str(value)
    return str(value)

def _get_c_print_format(value, var_type):
    """根据类型获取C语言的printf格式化符号。"""
    var_type_lower = var_type.lower()
    if 'char *' in var_type_lower or 'char*' in var_type_lower or isinstance(value, str): return "%s"
    if 'float' in var_type_lower or 'double' in var_type_lower or isinstance(value, float): return "%f"
    if 'int' in var_type_lower or 'long' in var_type_lower: return "%ld"
    # 对于指针和其他未知类型，使用 %p 打印地址
    return "%p" 

def _generate_c_source_deprecated(case_list, func_name, context_code):
    """为每个测试用例生成独立的C测试函数。"""
    
    # <--- 修改开始：收集所有唯一的头文件、类型定义、宏定义和结构体 ---
    all_includes = set()
    all_type_defs = {}
    all_macros = {}
    all_structs = {}

    for case in case_list:
        # 添加每个用例的头文件到集合中以去重
        for include in case.get('direct_includes', []):
            all_includes.add(include)
        # 使用 update 合并类型定义字典，同名类型会被覆盖（通常是相同的）
        all_type_defs.update(case.get('type_definitions', {}))
        
        # 收集宏定义
        for macro in case.get('macros', []):
            if isinstance(macro, dict) and 'name' in macro:
                all_macros[macro['name']] = macro
                
        # 收集结构体定义
        for struct in case.get('structs', []):
            if isinstance(struct, dict) and 'name' in struct:
                all_structs[struct['name']] = struct

    # 将集合转换为排序后的列表，以保证每次生成的文件内容一致
    # 格式化为 #include ... 字符串
    include_statements = "\n".join([f'#include {inc}' for inc in sorted(list(all_includes))])

    # 创建宏定义代码块
    macros_block = ""
    if all_macros:
        macros_block += "/* --- Injected Macro Definitions --- */\n"
        for macro_name, macro_info in all_macros.items():
            comment = macro_info.get('comment', '')
            if comment:
                macros_block += f"/* {comment} */\n"
            macros_block += f"#define {macro_name} {macro_info.get('value', '')}\n"
        macros_block += "/* --- End of Macro Definitions --- */\n\n"

    # 创建结构体定义代码块
    structs_block = ""
    if all_structs:
        structs_block += "/* --- Injected Structure Definitions --- */\n"
        for struct_name, struct_info in all_structs.items():
            comment = struct_info.get('comment', '')
            if comment:
                structs_block += f"/* {comment} */\n"
            kind = struct_info.get('kind', 'struct')
            body = struct_info.get('body', '')
            structs_block += f"{kind} {struct_name} {{\n{body}\n}};\n\n"
        structs_block += "/* --- End of Structure Definitions --- */\n\n"

    # 创建类型定义代码块
    type_defs_block = ""
    if all_type_defs:
        type_defs_block += "/* --- Injected Type Definitions --- */\n"
        for type_name, type_info in all_type_defs.items():
            # 添加注释，指明该类型定义来自哪个文件
            type_defs_block += f"// Type '{type_name}' originally from: {type_info.get('path', 'unknown path')}\n"
            type_defs_block += f"{type_info.get('definition', f'/* Error: No definition found for {type_name} */')}\n\n"
        type_defs_block += "/* --- End of Type Definitions --- */\n\n"
    # <--- 修改结束 ---

    # 生成主测试函数
    test_wrappers = f"""Datum {func_name}(PG_FUNCTION_ARGS);
Datum test_{func_name}(PG_FUNCTION_ARGS);

PG_FUNCTION_INFO_V1({func_name});
PG_FUNCTION_INFO_V1(test_{func_name});

/* 测试 {func_name} 的函数 */
Datum
test_{func_name}(PG_FUNCTION_ARGS)
{{
    elog(INFO, "Running test_{func_name}() to test {func_name}");

"""
    
    # 为每个测试用例生成测试代码
    for i, case in enumerate(case_list):
        desc = case.get('desc', f'Test case {i}')
        test_wrappers += f"    /* {desc} */\n"
        
        # 生成测试用例的具体测试代码
        inputs = case.get('inputs', [])
        outputs = case.get('outputs', [])
        
        if inputs and outputs:
            # 构建输入参数
            input_values = []
            for inp in inputs:
                value = _format_value_for_c(inp.get('value'), inp.get('type', ''))
                input_values.append(value)
            
            # 构建函数调用
            if input_values:
                func_call = f"{func_name}({', '.join(input_values)})"
            else:
                func_call = f"{func_name}()"
            
            # 生成测试代码
            expected_output = outputs[0].get('value') if outputs else 'void'
            test_wrappers += f"    elog(INFO, \"Case {i+1}: {' → '.join(str(v) for v in input_values)} → %d\", {func_call});\n\n"
        else:
            test_wrappers += f"    elog(INFO, \"Case {i+1}: Basic test\");\n\n"
    
    # 添加边界测试和错误处理
    test_wrappers += f"""    /* 错误测试用例 */
    PG_TRY();
    {{
        /* 这里可以添加预期会出错的测试用例 */
        elog(INFO, "Testing error conditions...");
    }}
    PG_CATCH();
    {{
        elog(INFO, "Caught expected error in test.");
    }}
    PG_END_TRY();

    PG_RETURN_VOID();
}}
"""

    # <--- 修改开始：在最终的C代码中注入所有必要的定义 ---
    return f"""
#include "postgres.h"
#include "fmgr.h"
#include "utils/palloc.h" // palloc for memory allocation

// --- Injected Header Files ---
{include_statements}

#ifdef PG_MODULE_MAGIC
PG_MODULE_MAGIC;
#endif

{macros_block}
{structs_block}
{type_defs_block}

/* --- 被测代码上下文 (Code Under Test Context) --- */
{context_code}
/* --- 上下文结束 --- */

/* --- 测试用例包装函数 (Test Case Wrappers) --- */
{test_wrappers}
"""
    # <--- 修改结束 ---

def _generate_sql_script(func_name, test_base_name):
    """生成驱动所有C测试函数的SQL脚本。"""
    sql_script = f"""-- Test script for {func_name}
-- This script creates and runs test functions for the {func_name} function

-- Create the main test function
CREATE OR REPLACE FUNCTION test_{func_name}() RETURNS void
AS '$libdir/{test_base_name}', 'test_{func_name}'
LANGUAGE C STRICT;

-- Run the test
SELECT test_{func_name}();
"""
    return sql_script

def _generate_expected_output(func_name, test_base_name):
    """生成预期的.out文件。"""
    expected_output = f"""-- Test script for {func_name}
-- This script creates and runs test functions for the {func_name} function

-- Create the main test function
CREATE OR REPLACE FUNCTION test_{func_name}() RETURNS void
AS '$libdir/{test_base_name}', 'test_{func_name}'
LANGUAGE C STRICT;
-- Run the test
SELECT test_{func_name}();
 test_{func_name} 
----------
 
(1 row)

"""
    return expected_output

def _generate_makefile(test_base_name):
    """生成符合 pg_regress 标准的 PGXS Makefile，基于example/makefile-new.txt模板。"""
    func_name = test_base_name.replace('test_', '')
    return f"""###############################################################################
# PostgreSQL Extension Build with Coverage Support (self-healing, IPC-clean)
###############################################################################

SHELL := /bin/bash

MODULES  = {test_base_name}
OBJS     = {test_base_name}.o

EXTENSION = {test_base_name}
DATA      = {test_base_name}--1.0.sql
CONTROL   = {test_base_name}.control

REGRESS = {test_base_name}

# --- PGXS ---
USE_PGXS  = 1
PG_CONFIG ?= pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)

# --- Coverage compile/link flags ---
override PG_CPPFLAGS += -O0 -g --coverage
override CFLAGS      += -Wall -Werror=vla -Werror=pointer-arith \\
                        -Werror=missing-prototypes -Werror=missing-declarations \\
                        --coverage
override PG_LDFLAGS  += --coverage

# --- Paths ---
sharedir   ?= /usr/local/pgsql/share
libdir     ?= /usr/local/pgsql/lib
pgbindir   ?= /usr/local/pgsql/bin
pgdatadir  ?= /usr/local/pgsql/data

pg_ctl := $(pgbindir)/pg_ctl
psql   := $(pgbindir)/psql

# --- Determine run command (root → runuser; postgres → direct) ---
ifeq ($(shell id -u),0)
	run_pg = runuser -u postgres --
else
	run_pg =
endif

###############################################################################
# Internal helpers
###############################################################################
define KILL_OLD_POSTGRES
pids=$$(ps -eo pid,cmd | awk '/[p]ostgres .* -D $(pgdatadir)( |$$)/ {{print $$1}}'); \\
if [ -n "$$pids" ]; then \\
  echo "[WARN] Killing leftover postgres PIDs: $$pids"; \\
  kill -TERM $$pids 2>/dev/null || true; \\
  sleep 2; \\
  pids2=$$(ps -eo pid,cmd | awk '/[p]ostgres .* -D $(pgdatadir)( |$$)/ {{print $$1}}'); \\
  [ -z "$$pids2" ] || {{ echo "[WARN] Forcing kill on: $$pids2"; kill -KILL $$pids2 2>/dev/null || true; }}; \\
fi
endef

define CLEAN_POSTGRES_IPC
if command -v ipcs >/dev/null 2>&1 && command -v ipcrm >/dev/null 2>&1; then \\
  echo "[WARN] Cleaning leftover System V IPC for user 'postgres'..."; \\
  shms=$$(ipcs -m | awk '$$$$3=="postgres"{{print $$$$2}}'); \\
  [ -z "$$shms" ] || {{ echo "[INFO] Removing SHM IDs: $$shms"; for id in $$shms; do ipcrm -m $$id 2>/dev/null || true; done; }}; \\
  sems=$$(ipcs -s | awk '$$$$3=="postgres"{{print $$$$2}}'); \\
  [ -z "$$sems" ] || {{ echo "[INFO] Removing SEM IDs: $$sems"; for id in $$sems; do ipcrm -s $$id 2>/dev/null || true; done; }}; \\
else \\
  echo "[INFO] ipcs/ipcrm not found; skipping IPC cleanup"; \\
fi
endef

###############################################################################
# ensure_pg_running: full self-healing (PID, processes, IPC, wait)
###############################################################################
.PHONY: ensure_pg_running
ensure_pg_running:
	@echo "[INFO] Checking PostgreSQL status..."; \\
	startup_log="$(pgdatadir)/log/postgresql.log"; \\
	if ! $(run_pg) $(pg_ctl) status -D $(pgdatadir) >/dev/null 2>&1; then \\
		echo "[WARN] PostgreSQL not running; healing environment..."; \\
		if [ -f "$(pgdatadir)/postmaster.pid" ]; then \\
			echo "[INFO] postmaster.pid exists; verifying..."; \\
			pid=$$(head -1 $(pgdatadir)/postmaster.pid); \\
			if [ -n "$$pid" ] && ps -p $$pid >/dev/null 2>&1; then \\
				echo "[WARN] A postgres process ($$pid) still exists; attempting to stop..."; \\
				$(call KILL_OLD_POSTGRES); \\
			else \\
				echo "[WARN] Stale postmaster.pid detected; removing..."; \\
				rm -f $(pgdatadir)/postmaster.pid || true; \\
			fi; \\
		fi; \\
		$(call KILL_OLD_POSTGRES); \\
		$(call CLEAN_POSTGRES_IPC); \\
		chown -R postgres:postgres $(pgdatadir) >/dev/null 2>&1 || true; \\
		echo "[INFO] Starting PostgreSQL..."; \\
		echo "[DEBUG] Ensuring log directory exists..."; \\
		mkdir -p "$$(dirname $$startup_log)" 2>/dev/null || true; \\
		chown -R postgres:postgres "$$(dirname $$startup_log)" 2>/dev/null || true; \\
		echo "[DEBUG] Log file: $$startup_log"; \\
		$(run_pg) $(pg_ctl) start -D $(pgdatadir) -l $$startup_log || true; \\
		for i in $$(seq 1 40); do \\
			sleep 1; \\
			if $(run_pg) $(psql) -U postgres -d postgres -c "SELECT 1;" >/dev/null 2>&1; then \\
				echo "[INFO] PostgreSQL is ready."; \\
				break; \\
			fi; \\
			if [ $$i -eq 10 ]; then \\
				echo "[WARN] Still not ready at 10s; showing recent logs:"; \\
				tail -n 40 $$startup_log 2>/dev/null || echo "[WARN] Log file not found: $$startup_log"; \\
			fi; \\
			if [ $$i -eq 40 ]; then \\
				echo "[ERROR] PostgreSQL did not become ready in time."; \\
				echo "[DEBUG] Full startup log:"; \\
				tail -n 80 $$startup_log 2>/dev/null || echo "[ERROR] Log file not found: $$startup_log"; \\
				echo "[DEBUG] Checking postgres processes:"; \\
				ps aux | grep "[p]ostgres" || true; \\
				exit 1; \\
			fi; \\
		done; \\
	else \\
		echo "[INFO] PostgreSQL is already running."; \\
		echo "[DEBUG] Verifying connection..."; \\
		if $(run_pg) $(psql) -U postgres -d postgres -c "SELECT 1;" >/dev/null 2>&1; then \\
			echo "[DEBUG] Connection test passed."; \\
		else \\
			echo "[WARN] PostgreSQL is running but not accepting connections!"; \\
			echo "[WARN] This may indicate a hung startup. Attempting recovery..."; \\
			$(MAKE) stop_pg; \\
			echo "[INFO] Restarting PostgreSQL..."; \\
			echo "[DEBUG] Ensuring log directory exists..."; \\
			mkdir -p "$$(dirname $$startup_log)" 2>/dev/null || true; \\
			chown -R postgres:postgres "$$(dirname $$startup_log)" 2>/dev/null || true; \\
			$(run_pg) $(pg_ctl) start -D $(pgdatadir) -l $$startup_log || true; \\
			for i in $$(seq 1 40); do \\
				sleep 1; \\
				if $(run_pg) $(psql) -U postgres -d postgres -c "SELECT 1;" >/dev/null 2>&1; then \\
					echo "[SUCCESS] PostgreSQL recovered and is ready."; \\
					break; \\
				fi; \\
				if [ $$i -eq 40 ]; then \\
					echo "[ERROR] PostgreSQL recovery failed."; \\
					tail -n 80 $$startup_log 2>/dev/null || true; \\
					exit 1; \\
				fi; \\
			done; \\
		fi; \\
	fi

###############################################################################
# stop_pg: robust stop with fallback to immediate mode + force kill
###############################################################################
.PHONY: stop_pg
stop_pg:
	@echo "[INFO] Stopping PostgreSQL..."; \\
	if $(run_pg) $(pg_ctl) status -D $(pgdatadir) >/dev/null 2>&1; then \\
		echo "[INFO] Attempting graceful shutdown (fast mode)..."; \\
		$(run_pg) $(pg_ctl) stop -D $(pgdatadir) -m fast -t 30 || true; \\
		sleep 2; \\
		if $(run_pg) $(pg_ctl) status -D $(pgdatadir) >/dev/null 2>&1; then \\
			echo "[WARN] Fast mode failed; trying immediate mode..."; \\
			$(run_pg) $(pg_ctl) stop -D $(pgdatadir) -m immediate -t 20 || true; \\
			sleep 2; \\
		fi; \\
		if $(run_pg) $(pg_ctl) status -D $(pgdatadir) >/dev/null 2>&1; then \\
			echo "[WARN] Immediate mode failed; force killing postgres processes..."; \\
			$(call KILL_OLD_POSTGRES); \\
			sleep 2; \\
		fi; \\
		if [ -f "$(pgdatadir)/postmaster.pid" ]; then \\
			echo "[INFO] Removing stale postmaster.pid..."; \\
			rm -f $(pgdatadir)/postmaster.pid || true; \\
		fi; \\
		$(call CLEAN_POSTGRES_IPC); \\
		if $(run_pg) $(pg_ctl) status -D $(pgdatadir) >/dev/null 2>&1; then \\
			echo "[ERROR] Failed to stop PostgreSQL after all attempts!"; \\
			exit 1; \\
		else \\
			echo "[SUCCESS] PostgreSQL stopped successfully."; \\
		fi; \\
	else \\
		echo "[INFO] PostgreSQL is already stopped."; \\
	fi

###############################################################################
# installcheck: ensure ready → run → stop (with robust readiness checks)
###############################################################################
installcheck: ensure_pg_running install
	@echo "[INFO] Running regression test..."; \\
	echo "[INFO] Waiting for PostgreSQL to be fully ready for connections..."; \\
	ready=0; \\
	for i in $$(seq 1 60); do \\
		if $(run_pg) $(pg_ctl) status -D $(pgdatadir) 2>&1 | grep -q "server is running"; then \\
			if $(run_pg) $(psql) -U postgres -d postgres -c "SELECT 1;" >/dev/null 2>&1; then \\
				echo "[SUCCESS] PostgreSQL is ready (attempt $$i/60)"; \\
				ready=1; \\
				break; \\
			fi; \\
		fi; \\
		if [ $$i -eq 1 ] || [ $$i -eq 10 ] || [ $$i -eq 30 ] || [ $$i -eq 50 ]; then \\
			echo "[INFO] Still waiting for PostgreSQL... (attempt $$i/60)"; \\
		fi; \\
		sleep 1; \\
	done; \\
	if [ $$ready -eq 0 ]; then \\
		echo "[ERROR] PostgreSQL did not become ready in 60 seconds!"; \\
		echo "[DEBUG] PostgreSQL status:"; \\
		$(run_pg) $(pg_ctl) status -D $(pgdatadir) || true; \\
		echo "[DEBUG] Recent PostgreSQL log:"; \\
		tail -n 50 $(CURDIR)/pg_autostart.log 2>/dev/null || true; \\
		exit 1; \\
	fi; \\
	echo "[INFO] Creating/resetting test database..."; \\
	$(run_pg) $(psql) -U postgres -d postgres -c "DROP DATABASE IF EXISTS contrib_regression;" || true; \\
	$(run_pg) $(psql) -U postgres -d postgres -c "CREATE DATABASE contrib_regression;"; \\
	echo "[INFO] Installing extension..."; \\
	$(run_pg) $(psql) -U postgres -d contrib_regression -c "DROP EXTENSION IF EXISTS {test_base_name} CASCADE;" || true; \\
	$(run_pg) $(psql) -U postgres -d contrib_regression -c "CREATE EXTENSION {test_base_name};"; \\
	echo "[INFO] Running test function..."; \\
	$(run_pg) $(psql) -U postgres -d contrib_regression -c "SELECT {test_base_name}();" || {{ \\
		echo "[ERROR] Test execution failed!"; \\
		$(MAKE) stop_pg; \\
		exit 1; \\
	}}; \\
	echo "[SUCCESS] Test completed successfully."; \\
	$(MAKE) stop_pg

###############################################################################
# ★ 新增：生成 .gcov 文件（关键）
###############################################################################
.PHONY: coverage_gcov
coverage_gcov:
	@echo "[INFO] Generating gcov files for {test_base_name}..."
	@test -f {test_base_name}.gcda || {{ echo "[ERROR] {test_base_name}.gcda not found"; exit 1; }}
	@test -f {test_base_name}.gcno || {{ echo "[ERROR] {test_base_name}.gcno not found"; exit 1; }}
	@gcov -o . {test_base_name}.c
	@echo "[INFO] Generated {test_base_name}.c.gcov"


###############################################################################
# Coverage report
###############################################################################
coverage_report:
	lcov --capture --directory $(CURDIR) --output-file coverage.info
	genhtml coverage.info --output-directory coverage_html
	lcov --summary coverage.info

###############################################################################
# Cleanup
###############################################################################
clean:
	rm -rf coverage_html coverage.info *.gcda *.gcno *.o *.so \\
	       results/ regression.diffs regression.out tmp_check/ log/ pg_autostart.log
"""

def _generate_control_file(test_base_name):
    """生成 .control 和 extension SQL 文件，基于example/模板。"""
    func_name = test_base_name.replace('test_', '')
    
    # control 文件 - 基于 example/text_int2in.control
    control_content = f"""# {test_base_name}.control
comment = 'Test extension for {func_name} function'
default_version = '1.0'
module_pathname = '$libdir/{test_base_name}'
relocatable = true
"""
    
    # extension SQL 文件 - 基于 example/test_int2in--1.0.sql
    sql_ext_content = f"""-- complain if script is sourced in psql, rather than via CREATE EXTENSION
\\echo Use "CREATE EXTENSION {test_base_name}" to load this file. \\quit

-- 绑定 C 函数 {test_base_name}（我们的测试入口）
CREATE FUNCTION {test_base_name}()
RETURNS void
AS '{test_base_name}', '{test_base_name}'
LANGUAGE C STRICT;

-- 调用测试函数，执行覆盖率测试
-- SELECT {test_base_name}();
"""
    
    # 返回一个字典，因为现在需要生成两个文件
    return {
        f"{test_base_name}.control": control_content,
        f"{test_base_name}--1.0.sql": sql_ext_content
    }

# <--- 修改：主函数 generate_pg_regress_suite 现在直接使用LLM生成的C代码 ---
def generate_pg_regress_suite(llm_generated_c_code, func_name, context_code, output_dir, pg_config_path):
    print(f"--- [pg_regress] Generating optimal test suite for '{func_name}' in '{output_dir}' ---")
    test_base_name = f"test_{func_name}"
    sql_dir = os.path.join(output_dir, 'sql')
    expected_dir = os.path.join(output_dir, 'expected')
    os.makedirs(sql_dir, exist_ok=True)
    os.makedirs(expected_dir, exist_ok=True)

    # 直接使用LLM生成的C代码，不再从case_list组装
    with open(os.path.join(output_dir, f'{test_base_name}.c'), 'w', encoding='utf-8') as f: 
        f.write(llm_generated_c_code)

    sql_script = _generate_sql_script(func_name, test_base_name)
    with open(os.path.join(sql_dir, f'{test_base_name}.sql'), 'w', encoding='utf-8') as f: f.write(sql_script)

    expected_output = _generate_expected_output(func_name, test_base_name)
    with open(os.path.join(expected_dir, f'{test_base_name}.out'), 'w', encoding='utf-8') as f: f.write(expected_output)

    makefile_content = _generate_makefile(test_base_name)
    with open(os.path.join(output_dir, 'Makefile'), 'w', encoding='utf-8') as f: f.write(makefile_content)

    # 生成 control 和 extension SQL 文件
    control_files = _generate_control_file(test_base_name)
    for filename, content in control_files.items():
        with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
            f.write(content)

    print(f"--- [pg_regress] Test suite successfully generated. ---")
    print("To run the test and generate coverage, navigate to the output directory and run:")
    print(f"  cd {output_dir}")
    print(f"  # 编译和运行测试:")
    print(f"  make clean && PG_CONFIG={pg_config_path} make && PG_CONFIG={pg_config_path} make installcheck")
    print(f"  # 生成覆盖率报告:")
    print(f"  make coverage_report")
    print(f"  # 或者直接运行测试函数:")
    print(f"  {pg_config_path.replace('/pg_config', '/psql')} -d contrib_regression -c \"SELECT test_{func_name}();\"")