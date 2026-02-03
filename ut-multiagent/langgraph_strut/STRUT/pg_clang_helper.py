#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL 源码 Clang 编译参数辅助模块。
"""
import os
import re
import subprocess

def get_system_include_paths():
    """自动检测 Clang 系统 include 路径"""
    print("🔍 [pg_helper] Detecting system include paths...")
    try:
        command = ['clang', '-v', '-E', '-x', 'c', os.devnull]
        result = subprocess.run(command, capture_output=True, text=True)
        output = result.stderr
        paths, in_list = [], False
        for line in output.splitlines():
            if '#include <...> search starts here:' in line:
                in_list = True
                continue
            if 'End of search list.' in line:
                in_list = False
                continue
            if in_list:
                path = line.strip()
                if '(framework directory)' in path:
                    continue
                if os.path.isdir(path):
                    paths.append('-I' + path)
        print(f"✅ [pg_helper] Found {len(paths)} system include paths.")
        return paths
    except Exception as e:
        print(f"⚠️ [pg_helper] Failed to get system include paths: {e}")
        return []

def extract_macros_from_make(c_file_path):
    """尝试从 Makefile 中提取编译宏（如果失败则返回空列表）"""
    print(f"🔍 [pg_helper] Extracting macros for {os.path.basename(c_file_path)} ...")
    c_file_dir = os.path.dirname(c_file_path)
    if not os.path.isdir(c_file_dir):
        return []

    base_name = os.path.basename(c_file_path)
    object_name = os.path.splitext(base_name)[0] + '.o'
    try:
        result = subprocess.run(['make', '-n', object_name],
                                cwd=c_file_dir,
                                capture_output=True,
                                text=True,
                                check=True)
        macros = re.findall(r'-D\S+', result.stdout)
        print(f"✅ [pg_helper] Extracted {len(macros)} macros from make.")
        return macros
    except Exception:
        print(f"⚠️ [pg_helper] 'make -n' failed in {c_file_dir}, fallback to defaults.")
        return ['-DUSE_ASSERT_CHECKING', '-DFRONTEND=0']

# 添加编译参数缓存
_compiler_args_cache = {}

def get_pg_compiler_args(c_file_path, pg_src_path='/usr/src/postgresql'):
    """生成 PostgreSQL 源码 Clang 编译参数"""
    
    # 检查缓存
    cache_key = (c_file_path, pg_src_path)
    if cache_key in _compiler_args_cache:
        return _compiler_args_cache[cache_key]
    
    compiler_args = [
        '-x', 'c',                       # ✅ 明确语言类型
        '-std=gnu11',
        '-D_GNU_SOURCE',
        '-D__STDC_CONSTANT_MACROS',
        '-D__STDC_LIMIT_MACROS',
        '-I' + os.path.join(pg_src_path, 'src/include'),
        '-I' + os.path.join(pg_src_path, 'src/backend'),
        '-I' + os.path.join(pg_src_path, 'src/include/port/linux'),
        '-I/usr/local/pgsql/include/server',
        '-I/usr/local/pgsql/include',
        '-Wno-unused-parameter',
        '-Wno-unused-function',
        '-Wno-ignored-attributes',
        '-Wno-visibility',
        '-fparse-all-comments'
    ]

    system_includes = get_system_include_paths()
    compiler_args.extend(system_includes)

    dynamic_macros = extract_macros_from_make(c_file_path)
    compiler_args.extend(dynamic_macros)

    # 去重（保持顺序）
    seen = set()
    compiler_args = [x for x in compiler_args if not (x in seen or seen.add(x))]

    _compiler_args_cache[cache_key] = compiler_args
    return compiler_args