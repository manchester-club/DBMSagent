#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量测试待测函数集合中的函数

用法:
    python3 batch_test_functions.py [--start-index N] [--end-index M] [--skip-zero]
    
参数:
    --start-index N: 从第 N 个函数开始测试（从0开始）
    --end-index M: 测试到第 M 个函数（不包含）
    --skip-zero: 跳过零覆盖率函数
"""

import sys
import re
import argparse
import builtins
from datetime import datetime
from pathlib import Path
from typing import Optional

# 添加 langgraph 目录到路径（必须在导入之前）
_langgraph_path = str(Path(__file__).parent / "langgraph")
if _langgraph_path not in sys.path:
    sys.path.insert(0, _langgraph_path)

# 导入 coverage_multi_agent（使用 type: ignore 避免 linter 警告）
from coverage_multi_agent import (
    run_test,  # type: ignore
    TeeLogger,  # type: ignore
    get_log_file_path,  # type: ignore
)


def extract_functions_from_markdown(md_file: str) -> list:
    """从 Markdown 文件中提取函数列表"""
    functions = []
    
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 从表格中提取函数信息
    table_pattern = r'\| `(\w+)` \| ([\d.]+)% \| (\d+) \| (\d+) \|'
    matches = re.findall(table_pattern, content)
    
    for match in matches:
        func_name, coverage, total_lines, uncovered_lines = match
        functions.append({
            'name': func_name,
            'coverage': float(coverage),
            'total_lines': int(total_lines),
            'uncovered_lines': int(uncovered_lines)
        })
    
    return functions


def generate_test_prompt(func_name: str) -> str:
    """为函数生成测试请求"""
    prompt = (
        f"请提高{func_name}函数的代码覆盖率："
        "1) 用 Collect_Coverage 收集覆盖率；"
        "2) 用 Search_Nearest_Seed 查找相关 SQL 种子；"
        "3) 用 Code Explorer 获取其源代码；"
        "4) 用 Traverse_Call_Graph 向上遍历调用关系；"
        "5) 用 Coverage Analyzer 生成 SQL 测试用例；"
        "6) 用 SQL Tester 执行 SQL 测试用例；"
        "7) 用 Collect_Coverage 验证覆盖率是否提升。"
        "8) 如果覆盖率没有提升，重复步骤 2-7。"
        "9) 如果覆盖率提升，结束。"
    )
    return prompt


def run_batch_test(
    functions: list,
    start_index: int = 0,
    end_index: Optional[int] = None,
    skip_zero: bool = False,
    output_dir: str = "batch_test_results"
):
    """批量测试函数"""
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # 生成摘要文件
    summary_file = output_path / f"batch_test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    # 过滤函数
    if skip_zero:
        functions = [f for f in functions if f['coverage'] > 0.0]
    
    # 确定测试范围
    if end_index is None:
        end_index = len(functions)
    
    functions_to_test = functions[start_index:end_index]
    
    print(f"\n{'='*80}")
    print(f"批量测试函数")
    print(f"{'='*80}")
    print(f"总函数数: {len(functions)}")
    print(f"测试范围: {start_index} - {end_index} (共 {len(functions_to_test)} 个函数)")
    print(f"跳过零覆盖率: {skip_zero}")
    print(f"{'='*80}\n")
    
    results = []
    
    for idx, func in enumerate(functions_to_test, start=start_index):
        func_name = func['name']
        initial_coverage = func['coverage']
        
        # 为每个函数创建独立的日志文件
        log_file_path = get_log_file_path(func_name, base_dir=str(Path(__file__).parent))
        logger = TeeLogger(log_file_path)
        
        # 保存原始 print 函数
        original_print = builtins.print
        
        # 重定向 print 到 logger
        def log_print(*args, **kwargs):
            """重定向 print 到 logger"""
            sep = kwargs.get('sep', ' ')
            end = kwargs.get('end', '\n')
            text = sep.join(str(arg) for arg in args) + end
            logger.write(text)
        
        # 替换 print
        builtins.print = log_print
        
        # 初始化 start_time，确保在异常处理中可用
        start_time = datetime.now()
        
        try:
            print("=" * 60)
            print("Coverage Multi-Agent (Supervisor + SQL Tester / Code Explorer / Coverage Analyzer)")
            print("=" * 60)
            print(f"日志文件: {log_file_path}")
            print()
            
            print(f"\n[Test] {func_name}\n")
            print(f"[User] {generate_test_prompt(func_name)}")
            print()
            
            print(f"\n[{idx+1}/{len(functions_to_test)}] 测试函数: {func_name}")
            print(f"  初始覆盖率: {initial_coverage:.2f}%")
            print(f"  未覆盖行数: {func['uncovered_lines']}/{func['total_lines']}")
            print(f"  开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 80)
            
            # 生成测试请求
            test_prompt = generate_test_prompt(func_name)
            
            # 运行测试
            thread_id = f"batch_test_{func_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            messages = run_test(
                test_prompt,
                thread_id=thread_id,
                recursion_limit=25
            )
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # 从消息中提取最终结果
            final_message = None
            for msg in reversed(messages):
                if hasattr(msg, 'content') and msg.content:
                    if '测试报告' in msg.content or '总结' in msg.content:
                        final_message = msg.content
                        break
            
            # 打印对话记录（与 coverage_multi_agent.py 的格式一致）
            print("\n" + "=" * 50)
            print("对话记录 (Messages)")
            print("=" * 50)
            for i, m in enumerate(messages):
                name = type(m).__name__
                content = (getattr(m, "content", None) or "")
                cap = 200
                if len(content) > cap:
                    content = content[:cap].rstrip() + "..."
                prefix = "[User]      " if name == "HumanMessage" else "[Assistant] "
                if name == "ToolMessage":
                    tname = (getattr(m, "name", None) or "?")[:24]
                    prefix = f"[Tool: {tname}] "
                print(f"  {prefix} {content}")
            print("\nDone.")
            
            result = {
                'index': idx,
                'function': func_name,
                'initial_coverage': initial_coverage,
                'status': 'success',
                'duration': duration,
                'final_message': final_message[:500] if final_message else None,  # 只保存前500字符
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                'log_file': log_file_path
            }
            
            print(f"  ✅ 测试完成 (耗时: {duration:.2f}秒)")
            
        except KeyboardInterrupt:
            print(f"  ⚠️  测试被用户中断")
            result = {
                'index': idx,
                'function': func_name,
                'initial_coverage': initial_coverage,
                'status': 'interrupted',
                'duration': None,
                'final_message': None,
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'log_file': log_file_path
            }
            # 恢复 print 并关闭日志
            builtins.print = original_print
            logger.close()
            break
            
        except Exception as e:
            print(f"  ❌ 测试失败: {e}")
            result = {
                'index': idx,
                'function': func_name,
                'initial_coverage': initial_coverage,
                'status': 'error',
                'duration': None,
                'final_message': str(e)[:500],
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'log_file': log_file_path
            }
        finally:
            # 恢复原始 print 并关闭日志
            builtins.print = original_print
            logger.close()
            # 使用原始 print 输出（此时日志已关闭）
            original_print(f"\n日志已保存到: {log_file_path}")
        
        results.append(result)
        
        # 保存中间结果
        with open(summary_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[{idx+1}] {func_name}\n")
            f.write(f"  状态: {result['status']}\n")
            f.write(f"  初始覆盖率: {initial_coverage:.2f}%\n")
            if result['duration']:
                f.write(f"  耗时: {result['duration']:.2f}秒\n")
            f.write(f"  开始时间: {result['start_time']}\n")
            f.write(f"  结束时间: {result['end_time']}\n")
            if 'log_file' in result:
                f.write(f"  日志文件: {result['log_file']}\n")
            if result['final_message']:
                f.write(f"  结果摘要: {result['final_message'][:200]}...\n")
            f.write("-" * 80 + "\n")
    
    # 生成最终摘要
    print(f"\n{'='*80}")
    print(f"批量测试完成")
    print(f"{'='*80}")
    print(f"总测试数: {len(results)}")
    print(f"成功: {sum(1 for r in results if r['status'] == 'success')}")
    print(f"失败: {sum(1 for r in results if r['status'] == 'error')}")
    print(f"中断: {sum(1 for r in results if r['status'] == 'interrupted')}")
    
    total_duration = sum(r['duration'] for r in results if r['duration'])
    if total_duration:
        print(f"总耗时: {total_duration:.2f}秒")
    
    print(f"\n详细结果已保存到: {summary_file}")
    print(f"{'='*80}\n")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='批量测试待测函数集合中的函数')
    parser.add_argument('--start-index', type=int, default=0, help='从第 N 个函数开始测试（从0开始）')
    parser.add_argument('--end-index', type=int, default=None, help='测试到第 M 个函数（不包含）')
    parser.add_argument('--skip-zero', action='store_true', help='跳过零覆盖率函数')
    parser.add_argument('--functions-file', type=str, default='待测函数集合.md', help='待测函数集合文件路径')
    parser.add_argument('--output-dir', type=str, default='batch_test_results', help='结果输出目录')
    
    args = parser.parse_args()
    
    # 读取函数列表
    functions_file = Path(__file__).parent / args.functions_file
    if not functions_file.exists():
        print(f"错误: 找不到文件 {functions_file}")
        sys.exit(1)
    
    functions = extract_functions_from_markdown(str(functions_file))
    
    if not functions:
        print("错误: 未能从文件中提取函数列表")
        sys.exit(1)
    
    print(f"从 {functions_file} 中读取到 {len(functions)} 个函数")
    
    # 运行批量测试
    results = run_batch_test(
        functions,
        start_index=args.start_index,
        end_index=args.end_index,
        skip_zero=args.skip_zero,
        output_dir=args.output_dir
    )


if __name__ == "__main__":
    main()
