#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import argparse
import csv


def dprint(debug, *args):
    if debug:
        print("[DEBUG]", *args)


def get_function_lines(c_file_path, function_name, debug=False):
    with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    pattern_funcname = re.compile(rf"\b{re.escape(function_name)}\s*\(")

    function_start = None
    function_end = None

    for i, raw in enumerate(lines):
        line = raw.strip()

        if not pattern_funcname.search(line):
            continue

        if line.endswith(";"):
            dprint(debug, f"跳过声明: 行 {i+1}: {line}")
            continue

        j = i
        found_brace = False
        while j < len(lines) and j - i <= 5:
            if "{" in lines[j]:
                found_brace = True
                break
            j += 1

        if not found_brace:
            dprint(debug, f"跳过非定义: 行 {i+1}: {line}")
            continue

        function_start = i + 1
        dprint(debug, f"✅ 函数 {function_name} 定义起始于行 {function_start}")

        brace_count = 0
        saw_left_brace = False
        for k in range(i, len(lines)):
            brace_count += lines[k].count("{")
            if lines[k].count("{"):
                saw_left_brace = True
            brace_count -= lines[k].count("}")
            if saw_left_brace and brace_count == 0:
                function_end = k + 1
                dprint(debug, f"函数 {function_name} 结束于行 {function_end}")
                break

        break

    if function_start and function_end:
        return function_start, function_end

    dprint(debug, "⚠️ 未找到函数定义（可能只有声明或括号未闭合）")
    return None, None


def load_source_lines(c_file_path):
    with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.readlines()


def get_source_line(src_lines, lineno_1based):
    idx = lineno_1based - 1
    if 0 <= idx < len(src_lines):
        return src_lines[idx].rstrip("\n")
    return ""


def analyze_coverage(gcov_file, c_file_path, function_start, function_end, debug=False):
    """
    输出增强点：
      - Uncovered lines：输出 line + 源码内容
      - Uncovered branches：输出 line + branch 信息 + 该行源码内容（来自 c_file_path）
    """
    src_lines = load_source_lines(c_file_path)

    # 行覆盖
    total_lines = 0
    covered_lines = 0
    uncovered_line_nos = []

    # 分支覆盖
    total_branches = 0          # 仅 'branch N taken X' 计入有效分支
    covered_branches = 0
    excluded_branches = 0       # 'branch N never executed'
    uncovered_branches = []     # (lineno, idx, taken, raw, code)

    code_line_re = re.compile(r"^\s*(?P<marker>[^:]+):\s*(?P<lineno>\d+):(?P<src>.*)$")
    branch_taken_re = re.compile(r"^\s*branch\s+(?P<idx>\d+)\s+taken\s+(?P<taken>\d+)\b(?P<rest>.*)$")
    branch_never_re = re.compile(r"^\s*branch\s+(?P<idx>\d+)\s+never\s+executed\b(?P<rest>.*)$")

    current_c_line = None

    with open(gcov_file, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            m = code_line_re.match(raw)
            if m:
                marker_raw = m.group("marker").strip()
                try:
                    c_line = int(m.group("lineno"))
                except ValueError:
                    current_c_line = None
                    continue

                current_c_line = c_line

                if function_start <= c_line <= function_end:
                    marker = marker_raw.replace(" ", "")

                    if marker in ("-:", "-"):
                        pass
                    elif marker in ("#####", "#####:", "##### :".replace(" ", "")):
                        total_lines += 1
                        uncovered_line_nos.append(c_line)
                    else:
                        covered_lines += 1
                        total_lines += 1
                continue

            # 分支行：使用最近一次出现的源码行号 current_c_line 作为归属行号
            if current_c_line is None:
                continue
            if not (function_start <= current_c_line <= function_end):
                continue

            bt = branch_taken_re.match(raw)
            if bt:
                idx = int(bt.group("idx"))
                taken = int(bt.group("taken"))

                total_branches += 1
                if taken > 0:
                    covered_branches += 1
                else:
                    code = get_source_line(src_lines, current_c_line).strip()
                    uncovered_branches.append((current_c_line, idx, taken, raw.strip(), code))

                dprint(debug, f"[branch taken] line={current_c_line} idx={idx} taken={taken}")
                continue

            bn = branch_never_re.match(raw)
            if bn:
                excluded_branches += 1
                idx = int(bn.group("idx"))
                dprint(debug, f"[branch excluded] line={current_c_line} idx={idx} never executed")
                continue

    # 未覆盖行：附加源码内容
    uncovered_line_entries = []
    if uncovered_line_nos:
        for lno in uncovered_line_nos:
            uncovered_line_entries.append((lno, get_source_line(src_lines, lno).strip()))

    uncovered_branches.sort(key=lambda x: (x[0], x[1]))

    return {
        "line": {
            "total": total_lines,
            "covered": covered_lines,
            "uncovered": total_lines - covered_lines,
            "uncovered_entries": uncovered_line_entries,  # (lineno, code)
        },
        "branch": {
            "total": total_branches,
            "covered": covered_branches,
            "excluded": excluded_branches,
            "uncovered_entries": uncovered_branches,      # (lineno, idx, taken, raw, code)
        },
    }


def print_coverage_block(func_name, line_info, branch_info):
    total_lines = line_info["total"]
    covered_lines = line_info["covered"]
    uncovered_lines = line_info["uncovered"]
    uncovered_entries = line_info["uncovered_entries"]

    total_branches = branch_info["total"]
    covered_branches = branch_info["covered"]
    excluded_branches = branch_info["excluded"]
    uncovered_branch_entries = branch_info["uncovered_entries"]

    line_cov = (covered_lines / total_lines * 100.0) if total_lines > 0 else 0.0

    print(f"\n=== {func_name} ===")
    print("[Line coverage]")
    print(f"  total lines:    {total_lines}")
    print(f"  covered lines:  {covered_lines}")
    print(f"  uncovered lines:{uncovered_lines}")
    print(f"  line coverage:  {line_cov:.2f}%")

    print("\n[Branch coverage]")
    print(f"  total branches:    {total_branches}")
    print(f"  covered branches:  {covered_branches}")
    print(f"  excluded branches: {excluded_branches}")
    if total_branches > 0:
        branch_cov = covered_branches / total_branches * 100.0
        print(f"  branch coverage:   {branch_cov:.2f}%")
    else:
        print("  branch coverage:   N/A (no effective branch edges in this function according to gcov)")

    print("\n[Uncovered lines]")
    if uncovered_entries:
        # 输出 line + 具体源码
        for (lno, code) in uncovered_entries:
            print(f"  line {lno}: {code}")
    else:
        print("  (none)")

    print("\n[Uncovered branches]")
    if uncovered_branch_entries:
        # 输出 line + branch 信息 + 具体源码
        for (lno, idx, taken, raw, code) in uncovered_branch_entries:
            # raw 保留 gcov 原始信息（含 fallthrough），code 展示该行的实际语句
            print(f"  line {lno}: {code}")
            print(f"           -> branch {idx} taken {taken}  ({raw})")
    else:
        print("  (none)")


def infer_suite_func_name_from_suite_dir(suite_dir):
    base = os.path.basename(os.path.normpath(suite_dir))
    if not (base.startswith("test_") and base.endswith("_suite")):
        return None
    return base[len("test_"):-len("_suite")]


def process_one_test_dir(subdir, writer, debug=False):
    base = os.path.basename(os.path.normpath(subdir))
    if not base.startswith("test_") or not base.endswith("_suite"):
        return {"ok": False, "lines_total": 0, "lines_covered": 0,
                "branches_total": 0, "branches_covered": 0, "branches_excluded": 0}

    func_name = infer_suite_func_name_from_suite_dir(subdir)
    if func_name is None:
        return {"ok": False, "lines_total": 0, "lines_covered": 0,
                "branches_total": 0, "branches_covered": 0, "branches_excluded": 0}

    c_file = os.path.join(subdir, f"test_{func_name}.c")
    gcov_file = os.path.join(subdir, f"test_{func_name}.c.gcov")

    if not os.path.exists(c_file) or not os.path.exists(gcov_file):
        print(f"⚠️ 缺少文件：{base}（需要 {os.path.basename(c_file)} 与 {os.path.basename(gcov_file)}）")
        return {"ok": False, "lines_total": 0, "lines_covered": 0,
                "branches_total": 0, "branches_covered": 0, "branches_excluded": 0}

    target_func = f"my_{func_name}"
    dprint(debug, f"正在定位函数: {target_func}")

    func_start, func_end = get_function_lines(c_file, target_func, debug=debug)
    if func_start is None or func_end is None:
        print(f"⚠️ 未找到函数 {target_func}() 在 {c_file} 中的定义")
        return {"ok": False, "lines_total": 0, "lines_covered": 0,
                "branches_total": 0, "branches_covered": 0, "branches_excluded": 0}

    result = analyze_coverage(gcov_file, c_file, func_start, func_end, debug=debug)
    line_info = result["line"]
    branch_info = result["branch"]

    # 终端打印：Uncovered lines/branches 都带具体代码
    print_coverage_block(target_func, line_info, branch_info)

    total_lines = line_info["total"]
    covered_lines = line_info["covered"]
    line_rate = (covered_lines / total_lines * 100.0) if total_lines > 0 else 0.0

    total_branches = branch_info["total"]
    covered_branches = branch_info["covered"]
    excluded_branches = branch_info["excluded"]

    if total_branches > 0:
        branch_rate_str = f"{(covered_branches / total_branches * 100.0):.2f}"
    else:
        branch_rate_str = "N/A"

    uncovered_line_entries = line_info["uncovered_entries"]
    uncovered_lines_str = (
        " | ".join([f"line {lno}: {code}" for (lno, code) in uncovered_line_entries])
        if uncovered_line_entries else "（全部覆盖）"
    )

    uncovered_branch_entries = branch_info["uncovered_entries"]
    uncovered_branches_str = (
        " | ".join([f"line {lno}: {code} -> branch {idx} taken {taken}"
                    for (lno, idx, taken, _, code) in uncovered_branch_entries])
        if uncovered_branch_entries else "（无）"
    )

    writer.writerow({
        "函数名": target_func,
        "C文件": c_file,
        "覆盖行数": covered_lines,
        "总代码行数": total_lines,
        "覆盖率(%)": f"{line_rate:.2f}",
        "分支覆盖(covered/total)": f"{covered_branches}/{total_branches}",
        "分支排除数": f"{excluded_branches}",
        "分支覆盖率(%)": branch_rate_str,
        "未覆盖行内容": uncovered_lines_str,
        "未覆盖分支": uncovered_branches_str,
    })

    return {
        "ok": True,
        "lines_total": total_lines,
        "lines_covered": covered_lines,
        "branches_total": total_branches,
        "branches_covered": covered_branches,
        "branches_excluded": excluded_branches,
    }


def analyze_root(root_dir, debug=False):
    if not os.path.isdir(root_dir):
        print(f"❌ 目录不存在: {root_dir}")
        return

    csv_path = os.path.join(root_dir, "coverage_report.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "函数名", "C文件",
            "覆盖行数", "总代码行数", "覆盖率(%)",
            "分支覆盖(covered/total)", "分支排除数", "分支覆盖率(%)",
            "未覆盖行内容", "未覆盖分支",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        total_lines = covered_lines = 0
        total_branches = covered_branches = excluded_branches = 0

        for entry in sorted(os.listdir(root_dir)):
            subdir = os.path.join(root_dir, entry)
            if not os.path.isdir(subdir):
                continue
            base = os.path.basename(os.path.normpath(subdir))
            if not (base.startswith("test_") and base.endswith("_suite")):
                continue

            stat = process_one_test_dir(subdir, writer, debug=debug)
            if not stat["ok"]:
                continue

            total_lines += stat["lines_total"]
            covered_lines += stat["lines_covered"]
            total_branches += stat["branches_total"]
            covered_branches += stat["branches_covered"]
            excluded_branches += stat["branches_excluded"]

        print("\n========== SUMMARY ==========")
        if total_lines > 0:
            overall_line_rate = covered_lines / total_lines * 100.0
            print(f"✅ Overall line coverage: {covered_lines}/{total_lines} ({overall_line_rate:.2f}%)")
        else:
            print("⚠️ No line coverage data found.")

        if total_branches > 0:
            overall_branch_rate = covered_branches / total_branches * 100.0
            print(f"✅ Overall branch coverage (effective): {covered_branches}/{total_branches} ({overall_branch_rate:.2f}%)")
        else:
            print("⚠️ No effective branch edges found in any function (according to gcov).")

    print(f"\n📄 已生成 CSV 报告: {csv_path}")


def analyze_suite(suite_dir, json_out=None, debug=False):
    if not os.path.isdir(suite_dir):
        print(f"❌ 目录不存在: {suite_dir}")
        return

    base = os.path.basename(os.path.normpath(suite_dir))
    if not (base.startswith("test_") and base.endswith("_suite")):
        print(f"❌ 不是合法的 test_xxx_suite 目录: {suite_dir}")
        return

    csv_path = os.path.join(suite_dir, "coverage_report.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "函数名", "C文件",
            "覆盖行数", "总代码行数", "覆盖率(%)",
            "分支覆盖(covered/total)", "分支排除数", "分支覆盖率(%)",
            "未覆盖行内容", "未覆盖分支",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        stat = process_one_test_dir(suite_dir, writer, debug=debug)
        if not stat["ok"]:
            print("⚠️ 该 suite 未产生有效覆盖数据（缺少文件或函数定位失败）。")
            return

        print("\n========== SUITE SUMMARY ==========")
        if stat["lines_total"] > 0:
            r = stat["lines_covered"] / stat["lines_total"] * 100.0
            print(f"✅ Line coverage: {stat['lines_covered']}/{stat['lines_total']} ({r:.2f}%)")
        else:
            print("⚠️ No line coverage data found in this suite.")

        if stat["branches_total"] > 0:
            rb = stat["branches_covered"] / stat["branches_total"] * 100.0
            print(f"✅ Branch coverage (effective): {stat['branches_covered']}/{stat['branches_total']} ({rb:.2f}%)")
        else:
            print("⚠️ No effective branch edges found in this suite (according to gcov).")

        if json_out:
            import json
            # 获取 func_name 以重新运行分析获取详细数据
            func_name_extracted = infer_suite_func_name_from_suite_dir(suite_dir)
            c_file_path = os.path.join(suite_dir, f"test_{func_name_extracted}.c")
            gcov_file_path = os.path.join(suite_dir, f"test_{func_name_extracted}.c.gcov")
            target_func_name = f"my_{func_name_extracted}"
            f_start, f_end = get_function_lines(c_file_path, target_func_name, debug=debug)
            detailed_result = analyze_coverage(gcov_file_path, c_file_path, f_start, f_end, debug=debug)
            
            # 构造符合 main.py 要求的格式，同时保留详细信息
            uncovered_info = {
                "branches": [
                    {
                        "branch": "coverage_optimization",
                        "condition": f"Line coverage is {stat['lines_covered']}/{stat['lines_total']}, Branch coverage is {stat['branches_covered']}/{stat['branches_total']}. Need to cover remaining paths."
                    }
                ],
                "uncovered_lines": [f"line {lno}: {code}" for lno, code in detailed_result["line"]["uncovered_entries"]],
                "uncovered_branches": [f"line {lno}: {code} -> branch {idx} taken {taken}" 
                                      for lno, idx, taken, _, code in detailed_result["branch"]["uncovered_entries"]]
            }
            with open(json_out, 'w', encoding='utf-8') as f:
                json.dump(uncovered_info, f, indent=4, ensure_ascii=False)
            print(f"📊 已生成 JSON 报告: {json_out}")

    print(f"\n📄 已生成 CSV 报告: {csv_path}")


def main():
    # 重新创建一个简单的 ArgumentParser，不使用子命令模式，直接通过逻辑判断，以提高参数解析的兼容性
    parser = argparse.ArgumentParser(
        description="Coverage analyzer for test_xxx_suite directories."
    )
    parser.add_argument(
        "mode",
        choices=["root", "suite"],
        help="root: analyze all test_*_suite under a root dir; suite: analyze a single test_*_suite dir"
    )
    parser.add_argument(
        "path",
        type=str,
        help="directory path"
    )
    parser.add_argument("-j", "--json-out", type=str, help="将未覆盖信息导出为 JSON 文件")
    parser.add_argument("--debug", action="store_true", help="显示调试信息")
    
    args, unknown = parser.parse_known_args()
    if unknown:
        dprint(args.debug, f"忽略未知参数: {unknown}")

    if args.mode == "root":
        analyze_root(args.path, debug=args.debug)
    elif args.mode == "suite":
        analyze_suite(args.path, json_out=args.json_out, debug=args.debug)


if __name__ == "__main__":
    main()