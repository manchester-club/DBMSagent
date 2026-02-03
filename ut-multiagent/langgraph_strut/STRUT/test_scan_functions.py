#!/usr/bin/env python3
"""
测试函数扫描功能

用于调试 auto_test_all_functions.sh 中的函数扫描问题
"""

import sys
import os
import clang.cindex

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pg_clang_helper import get_pg_compiler_args

def scan_functions(c_file, pg_src_path="/usr/src/postgresql"):
    """扫描C文件中的所有函数"""
    
    print(f"扫描文件: {c_file}")
    print(f"PG源码路径: {pg_src_path}")
    print("-" * 60)
    
    # 设置 libclang 路径
    clang.cindex.Config.set_library_file(r'/usr/lib/llvm-14/lib/libclang.so')
    
    # 创建索引
    index = clang.cindex.Index.create()
    
    # 获取编译参数
    print("获取编译参数...")
    try:
        compiler_args = get_pg_compiler_args(c_file, pg_src_path)
        print(f"编译参数: {' '.join(compiler_args[:5])}... (共 {len(compiler_args)} 个)")
    except Exception as e:
        print(f"❌ 获取编译参数失败: {e}")
        return []
    
    # 解析文件
    print("解析文件...")
    try:
        tu = index.parse(c_file, args=compiler_args)
    except Exception as e:
        print(f"❌ 解析文件失败: {e}")
        return []
    
    # 检查解析错误
    if tu.diagnostics:
        print(f"\n⚠️  发现 {len(tu.diagnostics)} 个编译诊断信息:")
        for diag in tu.diagnostics[:5]:  # 只显示前5个
            print(f"   - {diag.spelling}")
        if len(tu.diagnostics) > 5:
            print(f"   ... 还有 {len(tu.diagnostics) - 5} 个")
    
    # 扫描函数
    print("\n扫描函数定义...")
    functions = []
    all_nodes_count = 0
    function_decl_count = 0
    
    for node in tu.cursor.get_children():
        all_nodes_count += 1
        
        if node.kind == clang.cindex.CursorKind.FUNCTION_DECL:
            function_decl_count += 1
            
            # 检查是否是定义（不只是声明）
            if node.is_definition():
                # 检查是否在当前文件中
                if node.location.file:
                    node_file = node.location.file.name
                    if node_file == c_file:
                        functions.append(node.spelling)
                        print(f"   ✓ 找到函数: {node.spelling} (行 {node.location.line})")
                    else:
                        print(f"   - 跳过（不在目标文件）: {node.spelling} (在 {os.path.basename(node_file)})")
                else:
                    print(f"   - 跳过（无位置信息）: {node.spelling}")
            else:
                print(f"   - 跳过（仅声明）: {node.spelling}")
    
    print("-" * 60)
    print(f"统计:")
    print(f"  顶层节点总数: {all_nodes_count}")
    print(f"  函数声明总数: {function_decl_count}")
    print(f"  函数定义总数: {len(functions)}")
    print("-" * 60)
    
    return functions


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python3 test_scan_functions.py <C文件路径> [PG源码路径]")
        print("例如: python3 test_scan_functions.py /usr/src/postgresql/src/backend/utils/adt/int.c")
        sys.exit(1)
    
    c_file = sys.argv[1]
    pg_src_path = sys.argv[2] if len(sys.argv) > 2 else "/usr/src/postgresql"
    
    if not os.path.exists(c_file):
        print(f"❌ 文件不存在: {c_file}")
        sys.exit(1)
    
    print("="*60)
    print("函数扫描测试工具")
    print("="*60 + "\n")
    
    functions = scan_functions(c_file, pg_src_path)
    
    if functions:
        print(f"\n✅ 成功！发现 {len(functions)} 个函数:")
        for i, func in enumerate(functions, 1):
            print(f"   {i}. {func}")
    else:
        print("\n❌ 未找到任何函数定义")
        print("\n可能的原因:")
        print("  1. 文件中只有函数声明，没有定义")
        print("  2. Clang 解析失败（检查编译参数）")
        print("  3. 函数定义在其他文件中")
        sys.exit(1)


if __name__ == "__main__":
    main()

