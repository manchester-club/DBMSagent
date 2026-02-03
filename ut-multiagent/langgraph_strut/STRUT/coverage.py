#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict


def dprint(debug: bool, *args):
    if debug:
        print("[DEBUG]", *args)


# -----------------------------
# Locate function range in C file
# -----------------------------
def get_function_lines(c_file_path: str, function_name: str, debug: bool = False) -> Tuple[Optional[int], Optional[int]]:
    """
    Locate function definition start/end line numbers in C source.
    Heuristic:
      - match "function_name(" (word boundary)
      - skip declarations ending with ';'
      - within next 5 lines must find '{' to confirm definition
      - then count braces to find end

    NEW:
      - function name match is case-insensitive.
    """
    with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # NEW: case-insensitive function-name match
    pattern_funcname = re.compile(rf"\b{re.escape(function_name)}\s*\(", flags=re.IGNORECASE)

    function_start = None
    function_end = None

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not pattern_funcname.search(line):
            continue

        # skip prototype/declaration
        if line.endswith(";"):
            dprint(debug, f"Skip declaration at line {i+1}: {line}")
            continue

        # confirm definition by searching '{' soon
        j = i
        found_brace = False
        while j < len(lines) and j - i <= 5:
            if "{" in lines[j]:
                found_brace = True
                break
            j += 1
        if not found_brace:
            dprint(debug, f"Skip non-definition at line {i+1}: {line}")
            continue

        function_start = i + 1
        dprint(debug, f"Function {function_name} starts at {function_start}")

        brace_count = 0
        saw_left_brace = False
        for k in range(i, len(lines)):
            brace_count += lines[k].count("{")
            if lines[k].count("{") > 0:
                saw_left_brace = True
            brace_count -= lines[k].count("}")
            if saw_left_brace and brace_count == 0:
                function_end = k + 1
                dprint(debug, f"Function {function_name} ends at {function_end}")
                break
        break

    if function_start and function_end:
        return function_start, function_end
    return None, None


# -----------------------------
# Parse .gcov
# -----------------------------
GCOV_LINE_RE = re.compile(r"^\s*([^:]+):\s*([0-9]+):(.*)$")

# Support both:
#   branch 0 taken 0% (fallthrough)
#   branch 1 taken 12
#   branch 2 never executed
BRANCH_RE = re.compile(
    r"^\s*branch\s+(\d+)\s+"
    r"(?:taken\s+([0-9]+)(%)?|never\s+executed)"
    r"(?:\s+\(([^)]+)\))?\s*$"
)

# Support:
#   call 0 returned 40
#   call 1 never executed
CALL_RE = re.compile(
    r"^\s*call\s+(\d+)\s+"
    r"(?:returned\s+([0-9]+)|never\s+executed)\s*$"
)


def parse_gcov_line(raw: str) -> Optional[Tuple[str, int, str]]:
    """
    Parse a standard gcov source line:
      <count>:<line>:<source>
    """
    m = GCOV_LINE_RE.match(raw)
    if not m:
        return None
    count_str = m.group(1).strip()
    line_no = int(m.group(2))
    src = m.group(3).rstrip("\n")
    return count_str, line_no, src


@dataclass
class BranchEdge:
    # original line (the gcov-associated source line)
    line_no: int
    # normalized "decision" line (remapped to statement start)
    decision_line_no: int

    branch_id: int
    taken: Optional[int]         # None => never executed
    is_percent: bool             # taken is percent?
    note: Optional[str]          # e.g. fallthrough
    raw: str

    # if excluded, provide reason for reporting/debugging
    exclude_reason: Optional[str] = None


@dataclass
class CallEdge:
    line_no: int
    call_id: int
    returned: Optional[int]      # None => never executed
    raw: str


@dataclass
class CoverageResult:
    func_name: str
    func_start: int
    func_end: int

    # line coverage
    total_lines: int
    covered_lines: int
    uncovered_lines: List[int]

    # branch coverage (effective, after exclusion)
    total_branches: int
    covered_branches: int
    uncovered_branches: List[BranchEdge]

    # excluded branches
    excluded_branches: int
    excluded_branch_edges: List[BranchEdge]

    # call coverage (optional but useful)
    total_calls: int
    covered_calls: int
    uncovered_calls: List[CallEdge]

    # full source lines (1-based index)
    c_lines: List[str]


def is_executable_marker(marker: str) -> bool:
    """
    Decide if a gcov line marker should count as an executable line in line-coverage denominator.
    Typical non-exec markers: '-', '-:', '=====' etc.
    """
    m = marker.strip()
    if m in ("-", "-:", "=====", "=====:"):
        return False
    return True


def is_uncovered_marker(marker: str) -> bool:
    return marker.strip().startswith("#####")


def parse_exec_count(marker: str) -> Optional[int]:
    """
    Parse gcov execution marker into an integer count when possible.
    Examples:
      '#####:': 0
      '0': 0
      '12': 12
      '1*': 1   (gcov uses '*' to indicate partial blocks; for our purposes it still executed)
      '-': None (non-exec)
    """
    s = marker.strip()
    if s in ("-", "-:", "=====", "=====:"):
        return None
    if s.startswith("#####"):
        return 0
    # strip trailing '*' (e.g., '1*')
    s2 = s.rstrip("*")
    if s2.isdigit():
        return int(s2)
    # occasionally gcov produces weird markers; treat as unknown
    return None


# -----------------------------
# Pretty printing source snippets
# -----------------------------
def is_blank_or_comment(s: str) -> bool:
    t = s.strip()
    if not t:
        return True
    if t.startswith("//"):
        return True
    if t.startswith("/*") and t.endswith("*/"):
        return True
    if t.startswith("*"):
        return True
    return False


def extract_statement_snippet(c_lines: List[str], start_line_no: int, max_lines: int = 12) -> str:
    if start_line_no < 1 or start_line_no > len(c_lines):
        return "<out of range>"

    out: List[str] = []
    paren_depth = 0

    def update_paren_depth(line: str, depth: int) -> int:
        depth += line.count("(")
        depth -= line.count(")")
        return depth

    for idx in range(start_line_no - 1, min(len(c_lines), start_line_no - 1 + max_lines)):
        line = c_lines[idx]

        if not out:
            out.append(line.rstrip())
            paren_depth = update_paren_depth(line, paren_depth)
        else:
            t = line.strip()
            if t.startswith("#"):
                break
            if t in ("{", "}") or t.startswith("}"):
                break
            if is_blank_or_comment(line):
                continue
            out.append(line.rstrip())
            paren_depth = update_paren_depth(line, paren_depth)

        # Stop if statement likely ends
        if ";" in line and paren_depth <= 0:
            break

    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()

    if not out:
        return "<empty>"
    if len(out) == 1:
        return out[0].strip()
    return "\n".join(out)


# -----------------------------
# NEW: better unreachable branch detector (scan snippet, not just a single line)
# -----------------------------
def statement_contains_unconditional_error(c_lines: List[str], start_line_no: int) -> bool:
    """
    Heuristic: if a statement snippet contains ereport/elog ERROR-or-higher or pg_unreachable,
    branches on that statement are not meaningfully coverable under normal pg_regress/pgTAP flow.
    We scan multiple lines because macros frequently span lines.
    """
    snippet = extract_statement_snippet(c_lines, start_line_no, max_lines=20)
    s = " ".join(snippet.strip().split())

    patterns = [
        r"\bereport\s*\(\s*ERROR\b",
        r"\bereport\s*\(\s*FATAL\b",
        r"\bereport\s*\(\s*PANIC\b",
        r"\belog\s*\(\s*ERROR\b",
        r"\belog\s*\(\s*FATAL\b",
        r"\belog\s*\(\s*PANIC\b",
        r"\bpg_unreachable\s*\(",
        r"\bAssert\s*\(\s*false\s*\)",
    ]
    return any(re.search(p, s) for p in patterns)


# -----------------------------
# NEW: branch decision-line remapping (fix attribution for multi-line conditions)
# -----------------------------
CONTROL_START_RE = re.compile(r"\b(if|while|for|switch)\b")


def likely_continuation_line(line: str) -> bool:
    """
    Detect if a C line is likely a continuation of a previous condition/expression.
    """
    t = line.strip()
    if not t:
        return True
    if t.startswith("#"):
        return False
    # common continuation tokens in multi-line boolean conditions / parenthesized expressions
    cont_prefixes = ("||", "&&", ")", "(", ",", "?", ":", "+", "-", "*", "/", "%", "->", ".")
    if t.startswith(cont_prefixes):
        return True
    # lines that end with boolean operator are almost certainly continuations
    if t.endswith(("||", "&&")):
        return True
    # standalone closing paren line
    if t == ")":
        return True
    return False


def paren_balance(lines: List[str]) -> int:
    """
    Rough parentheses balance: (# '(') - (# ')') ignoring strings/comments.
    This is heuristic but sufficient for remapping decisions.
    """
    bal = 0
    for ln in lines:
        bal += ln.count("(")
        bal -= ln.count(")")
    return bal


def find_control_statement_start(c_lines: List[str], line_no: int, max_lookback: int = 30) -> int:
    """
    Try to find the start line of the control statement whose condition spans the given line.
    We look backwards for if/while/for/switch and validate that parentheses remain open
    through the target line.
    """
    if line_no < 1:
        return line_no
    start_idx = max(1, line_no - max_lookback)

    # precompute slice for balance checks as needed (small max_lookback, OK)
    for cand in range(line_no, start_idx - 1, -1):
        text = c_lines[cand - 1]
        if not CONTROL_START_RE.search(text):
            continue

        # must have '(' on the same line or shortly after, but we keep simple
        if "(" not in text:
            continue

        # validate that from cand..line_no we are inside the same parenthesized condition
        segment = c_lines[cand - 1: line_no]
        if paren_balance(segment) > 0:
            return cand

        # Another common case: condition ends on later line, but balance at line_no might be 0
        # (e.g., last line contains the closing ')'). Still, cand is a good decision anchor.
        # We accept it if there is no ';' before reaching line_no (suggesting not a new stmt).
        joined = "\n".join(segment)
        if ";" not in joined:
            return cand

    return line_no


def remap_branch_to_decision_line(c_lines: List[str], line_no: int) -> int:
    """
    Remap branch attribution line to a more stable 'decision' line.
    If the current line looks like a continuation of an if/while/for condition, anchor it.
    """
    if line_no < 1 or line_no > len(c_lines):
        return line_no
    curr = c_lines[line_no - 1]
    if likely_continuation_line(curr):
        return find_control_statement_start(c_lines, line_no)
    # Even if not obviously continuation, it might still be in a multi-line condition.
    # A conservative extra attempt: if line has only part of boolean expression.
    if ("||" in curr or "&&" in curr) and not CONTROL_START_RE.search(curr):
        return find_control_statement_start(c_lines, line_no)
    return line_no


def pct(n: int, d: int) -> float:
    return (n / d * 100.0) if d else 0.0


def format_branch_edge(b: BranchEdge) -> str:
    if b.taken is None:
        taken_str = "never executed"
    else:
        taken_str = f"taken {b.taken}{'%' if b.is_percent else ''}"
    note = f" ({b.note})" if b.note else ""
    dec = ""
    if b.decision_line_no != b.line_no:
        dec = f" [decision@{b.decision_line_no}]"
    if b.exclude_reason:
        dec += f" <excluded:{b.exclude_reason}>"
    return f"line {b.line_no}{dec}, branch {b.branch_id}: {taken_str}{note}"


def format_call_edge(c: CallEdge) -> str:
    returned_str = "never executed" if c.returned is None else f"returned {c.returned}"
    return f"line {c.line_no}, call {c.call_id}: {returned_str}"


# -----------------------------
# New: infer paths from suite directory rules
# -----------------------------
@dataclass
class InferredSuiteInfo:
    suite_dir: str
    func_name: str
    c_base: str
    src_c_path: str
    gcov_path: str


def infer_from_suite_dir(suite_dir: str, debug: bool = False) -> InferredSuiteInfo:
    """
    Given suite_dir like:
      src/backend/utils/adt/my_int/test_int2out_suite
    infer:
      func_name = int2out
      c_base    = int
      src_c_path = src/backend/utils/adt/int.c
      gcov_path  = <suite_dir>/int.c.gcov   (fallback to first *.gcov if not found)
    """
    suite_dir = os.path.normpath(suite_dir)
    if not os.path.isdir(suite_dir):
        raise RuntimeError(f"Suite directory does not exist or is not a directory: {suite_dir}")

    suite_name = os.path.basename(suite_dir)
    m = re.match(r"^test_(.+)_suite$", suite_name)
    if not m:
        raise RuntimeError(
            f"Suite directory name must match 'test_<func>_suite'. Got: {suite_name}"
        )
    func_name = m.group(1)

    my_dir = os.path.basename(os.path.dirname(suite_dir))
    mm = re.match(r"^my_(.+)$", my_dir)
    if not mm:
        raise RuntimeError(
            f"Suite parent directory must be named 'my_<cfilebase>'. Got: {my_dir}"
        )
    c_base = mm.group(1)

    # The original C file is sibling to my_<cbase> within the same parent dir
    adt_dir = os.path.dirname(os.path.dirname(suite_dir))  # .../adt
    src_c_path = os.path.join(adt_dir, f"{c_base}.c")
    if not os.path.isfile(src_c_path):
        raise RuntimeError(f"Cannot find inferred source C file: {src_c_path}")

    # Preferred gcov name: <c_base>.c.gcov
    prefer_gcov = os.path.join(suite_dir, f"{c_base}.c.gcov")
    gcov_path = prefer_gcov

    if not os.path.isfile(gcov_path):
        # Fallback: pick the first *.gcov in suite_dir
        gcovs = sorted(
            os.path.join(suite_dir, f)
            for f in os.listdir(suite_dir)
            if f.endswith(".gcov") and os.path.isfile(os.path.join(suite_dir, f))
        )
        if not gcovs:
            raise RuntimeError(
                f"Cannot find gcov file in suite directory. "
                f"Tried {prefer_gcov}, and no '*.gcov' files found under {suite_dir}"
            )
        gcov_path = gcovs[0]
        dprint(debug, f"Fallback gcov: {gcov_path}")

    dprint(debug, "Inferred:",
           f"suite_dir={suite_dir}",
           f"func={func_name}",
           f"c_base={c_base}",
           f"src={src_c_path}",
           f"gcov={gcov_path}")

    return InferredSuiteInfo(
        suite_dir=suite_dir,
        func_name=func_name,
        c_base=c_base,
        src_c_path=src_c_path,
        gcov_path=gcov_path,
    )


def list_suite_dirs(root_my_dir: str, debug: bool = False) -> List[str]:
    """
    Given root dir like:
      src/backend/utils/adt/my_int
    return all immediate children that match test_*_suite.
    """
    root_my_dir = os.path.normpath(root_my_dir)
    if not os.path.isdir(root_my_dir):
        raise RuntimeError(f"Root directory does not exist or is not a directory: {root_my_dir}")

    suites: List[str] = []
    for name in sorted(os.listdir(root_my_dir)):
        if not name.startswith("test_") or not name.endswith("_suite"):
            continue
        p = os.path.join(root_my_dir, name)
        if os.path.isdir(p):
            suites.append(p)

    dprint(debug, f"Found {len(suites)} suite(s) under {root_my_dir}")
    return suites


# -----------------------------
# Core analysis
# -----------------------------
def analyze_function_coverage_from_gcov(
    gcov_file: str,
    c_file_path: str,
    function_name: str,
    debug: bool = False
) -> CoverageResult:
    func_start, func_end = get_function_lines(c_file_path, function_name, debug=debug)
    if func_start is None or func_end is None:
        raise RuntimeError(f"Cannot locate function definition: {function_name} in {c_file_path}")

    with open(c_file_path, "r", encoding="utf-8", errors="ignore") as f:
        c_lines = [ln.rstrip("\n") for ln in f.readlines()]  # list index 0 == line 1

    total_lines = 0
    covered_lines = 0
    uncovered_lines: List[int] = []

    branch_edges: List[BranchEdge] = []
    call_edges: List[CallEdge] = []

    # store gcov execution counts for lines inside the function
    exec_count_by_line: Dict[int, int] = {}

    last_src_line_no: Optional[int] = None

    with open(gcov_file, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            pl = parse_gcov_line(raw)
            if pl is not None:
                marker, line_no, _ = pl
                last_src_line_no = line_no

                if not (func_start <= line_no <= func_end):
                    continue

                # exec count tracking (even if non-exec markers, parse_exec_count returns None)
                ec = parse_exec_count(marker)
                if ec is not None:
                    exec_count_by_line[line_no] = ec

                if not is_executable_marker(marker):
                    continue

                total_lines += 1
                if is_uncovered_marker(marker):
                    uncovered_lines.append(line_no)
                else:
                    covered_lines += 1
                continue

            # branch line
            bm = BRANCH_RE.match(raw)
            if bm:
                if last_src_line_no is None:
                    continue
                if not (func_start <= last_src_line_no <= func_end):
                    continue

                branch_id = int(bm.group(1))
                taken_num = bm.group(2)          # may be None (never executed case)
                percent_flag = bm.group(3)       # '%' or None
                note = bm.group(4)

                if taken_num is None:
                    taken = None
                    is_percent = False
                else:
                    taken = int(taken_num)
                    is_percent = (percent_flag == "%")

                decision_line_no = remap_branch_to_decision_line(c_lines, last_src_line_no)

                branch_edges.append(
                    BranchEdge(
                        line_no=last_src_line_no,
                        decision_line_no=decision_line_no,
                        branch_id=branch_id,
                        taken=taken,
                        is_percent=is_percent,
                        note=note,
                        raw=raw.rstrip("\n"),
                    )
                )
                continue

            # call line
            cm = CALL_RE.match(raw)
            if cm:
                if last_src_line_no is None:
                    continue
                if not (func_start <= last_src_line_no <= func_end):
                    continue

                call_id = int(cm.group(1))
                returned_str = cm.group(2)
                returned = int(returned_str) if returned_str is not None else None

                call_edges.append(
                    CallEdge(
                        line_no=last_src_line_no,
                        call_id=call_id,
                        returned=returned,
                        raw=raw.rstrip("\n"),
                    )
                )
                continue

    # -----------------------------
    # Branch filtering/exclusion
    # -----------------------------
    excluded_branch_edges: List[BranchEdge] = []
    effective_branch_edges: List[BranchEdge] = []

    # 1) exclude branches on statements that unconditionally raise ERROR-or-higher
    tmp: List[BranchEdge] = []
    for b in branch_edges:
        if statement_contains_unconditional_error(c_lines, b.decision_line_no):
            b.exclude_reason = "unconditional_error_stmt"
            excluded_branch_edges.append(b)
        else:
            tmp.append(b)

    # 2) NEW: exclude gcov attribution artifacts ("never executed") when decision executed and/or mixed with real edges
    # Group by decision line (this is the core fix for multi-line condition artifacts)
    by_decision: Dict[int, List[BranchEdge]] = {}
    for b in tmp:
        by_decision.setdefault(b.decision_line_no, []).append(b)

    for dec_line, edges in by_decision.items():
        dec_exec = exec_count_by_line.get(dec_line, None)

        any_real = any(e.taken is not None for e in edges)
        any_taken_pos = any((e.taken is not None and e.taken > 0) or (e.taken is not None and e.is_percent and e.taken > 0) for e in edges)
        all_never = all(e.taken is None for e in edges)

        # Case A: decision executed, but all edges are "never executed" -> instrumentation noise; exclude all
        if dec_exec is not None and dec_exec > 0 and all_never:
            for e in edges:
                e.exclude_reason = "gcov_artifact_all_never_on_executed_decision"
                excluded_branch_edges.append(e)
            continue

        # Case B: mixed real/never within same decision -> exclude only never-executed ones
        if any_real:
            for e in edges:
                if e.taken is None:
                    # if decision executed (or any other edge shows taken), this is almost certainly attribution noise
                    if (dec_exec is not None and dec_exec > 0) or any_taken_pos:
                        e.exclude_reason = "gcov_artifact_never_edge_in_mixed_decision"
                        excluded_branch_edges.append(e)
                    else:
                        # conservative: keep as effective if we can't assert decision ran
                        effective_branch_edges.append(e)
                else:
                    effective_branch_edges.append(e)
            continue

        # Case C: no real edges (all are numeric but could be zeros) -> keep as effective
        for e in edges:
            effective_branch_edges.append(e)

    # Now compute effective branch coverage
    total_branches = len(effective_branch_edges)
    covered_branches = 0
    uncovered_branches: List[BranchEdge] = []
    for b in effective_branch_edges:
        if b.taken is None or b.taken == 0:
            uncovered_branches.append(b)
        else:
            covered_branches += 1

    # Call coverage:
    total_calls = len(call_edges)
    covered_calls = sum(1 for c in call_edges if (c.returned is not None and c.returned > 0))
    uncovered_calls = [c for c in call_edges if (c.returned is None or c.returned == 0)]

    return CoverageResult(
        func_name=function_name,
        func_start=func_start,
        func_end=func_end,
        total_lines=total_lines,
        covered_lines=covered_lines,
        uncovered_lines=sorted(set(uncovered_lines)),
        total_branches=total_branches,
        covered_branches=covered_branches,
        uncovered_branches=uncovered_branches,
        excluded_branches=len(excluded_branch_edges),
        excluded_branch_edges=excluded_branch_edges,
        total_calls=total_calls,
        covered_calls=covered_calls,
        uncovered_calls=uncovered_calls,
        c_lines=c_lines,
    )


# -----------------------------
# Reporting
# -----------------------------
def print_single_suite_report(res: CoverageResult, inferred: "InferredSuiteInfo", debug: bool = False):
    print(f"\n=== Suite: {os.path.basename(inferred.suite_dir)} ===")
    print(f"  suite_dir: {inferred.suite_dir}")
    print(f"  func:      {res.func_name}")
    print(f"  src:       {inferred.src_c_path}")
    print(f"  gcov:      {inferred.gcov_path}")
    print(f"  range:     lines {res.func_start}-{res.func_end}")

    # Line coverage
    print("\n[Line coverage]")
    print(f"  total lines:    {res.total_lines}")
    print(f"  covered lines:  {res.covered_lines}")
    print(f"  uncovered lines:{len(res.uncovered_lines)}")
    print(f"  line coverage:  {pct(res.covered_lines, res.total_lines):.2f}%")

    # Branch coverage
    print("\n[Branch coverage]  (gcov 'branch' edges, after remap + exclusion)")
    print(f"  total branches:    {res.total_branches}")
    print(f"  covered branches:  {res.covered_branches}")
    print(f"  excluded branches: {res.excluded_branches}")
    if res.total_branches == 0:
        print("  branch coverage:   N/A (no effective branch edges in this function according to gcov)")
    else:
        print(f"  branch coverage:   {pct(res.covered_branches, res.total_branches):.2f}%")

    # Call coverage
    print("\n[Call coverage]  (gcov 'call' edges)")
    print(f"  total calls:   {res.total_calls}")
    print(f"  covered calls: {res.covered_calls}")
    if res.total_calls == 0:
        print("  call coverage: N/A (no call edges in this function according to gcov)")
    else:
        print(f"  call coverage: {pct(res.covered_calls, res.total_calls):.2f}%")

    # Uncovered lines
    print("\n[Uncovered lines]")
    if not res.uncovered_lines:
        print("  (none)")
    else:
        for lno in res.uncovered_lines:
            snippet = extract_statement_snippet(res.c_lines, lno)
            if "\n" in snippet:
                print(f"  line {lno}:")
                print("    " + "\n    ".join(snippet.splitlines()))
            else:
                print(f"  line {lno}: {snippet}")

    # Uncovered branches
    print("\n[Uncovered branches]  (effective)")
    if not res.uncovered_branches:
        print("  (none)")
    else:
        for b in res.uncovered_branches:
            print(f"  {format_branch_edge(b)}")
            snippet = extract_statement_snippet(res.c_lines, b.decision_line_no)
            if "\n" in snippet:
                print("    code (decision stmt):")
                print("      " + "\n      ".join(snippet.splitlines()))
            else:
                print(f"    code (decision stmt): {snippet}")
            if debug:
                print(f"    raw:  {b.raw}")

    # Excluded branches
    if debug and res.excluded_branch_edges:
        print("\n[Excluded branches]  (debug)")
        for b in res.excluded_branch_edges:
            print(f"  {format_branch_edge(b)}")
            snippet = extract_statement_snippet(res.c_lines, b.decision_line_no)
            if "\n" in snippet:
                print("    code (decision stmt):")
                print("      " + "\n      ".join(snippet.splitlines()))
            else:
                print(f"    code (decision stmt): {snippet}")
            print(f"    raw:  {b.raw}")

    # Uncovered calls
    print("\n[Uncovered calls]")
    if not res.uncovered_calls:
        print("  (none)")
    else:
        for c in res.uncovered_calls:
            print(f"  {format_call_edge(c)}")
            snippet = extract_statement_snippet(res.c_lines, c.line_no)
            if "\n" in snippet:
                print("    code:")
                print("      " + "\n      ".join(snippet.splitlines()))
            else:
                print(f"    code: {snippet}")
            if debug:
                print(f"    raw:  {c.raw}")


@dataclass
class SuiteAggregateRow:
    suite_dir: str
    func_name: str
    total_lines: int
    covered_lines: int
    uncovered_lines: int
    line_pct: float
    total_branches: int
    covered_branches: int
    branch_pct: Optional[float]  # None => N/A
    total_calls: int
    covered_calls: int
    call_pct: Optional[float]    # None => N/A


def compute_row(inferred: InferredSuiteInfo, debug: bool = False) -> Tuple[SuiteAggregateRow, CoverageResult]:
    res = analyze_function_coverage_from_gcov(
        gcov_file=inferred.gcov_path,
        c_file_path=inferred.src_c_path,
        function_name=inferred.func_name,
        debug=debug
    )
    line_pct = pct(res.covered_lines, res.total_lines) if res.total_lines else 0.0
    branch_pct = None if res.total_branches == 0 else pct(res.covered_branches, res.total_branches)
    call_pct = None if res.total_calls == 0 else pct(res.covered_calls, res.total_calls)
    row = SuiteAggregateRow(
        suite_dir=inferred.suite_dir,
        func_name=inferred.func_name,
        total_lines=res.total_lines,
        covered_lines=res.covered_lines,
        uncovered_lines=len(res.uncovered_lines),
        line_pct=line_pct,
        total_branches=res.total_branches,
        covered_branches=res.covered_branches,
        branch_pct=branch_pct,
        total_calls=res.total_calls,
        covered_calls=res.covered_calls,
        call_pct=call_pct,
    )
    return row, res


def print_root_summary(rows: List[SuiteAggregateRow], errors: List[str], root_dir: str):
    print(f"\n=== Root Summary: {root_dir} ===")
    print(f"  suites analyzed: {len(rows)}")
    if errors:
        print(f"  suites failed:   {len(errors)}")

    sum_total_lines = sum(r.total_lines for r in rows)
    sum_covered_lines = sum(r.covered_lines for r in rows)
    sum_uncovered_lines = sum(r.uncovered_lines for r in rows)

    overall_line_pct = pct(sum_covered_lines, sum_total_lines) if sum_total_lines else 0.0
    avg_line_pct = (sum(r.line_pct for r in rows) / len(rows)) if rows else 0.0

    # Branch overall: only count suites with branches present
    branch_rows = [r for r in rows if r.total_branches > 0]
    sum_total_branches = sum(r.total_branches for r in branch_rows)
    sum_covered_branches = sum(r.covered_branches for r in branch_rows)
    overall_branch_pct = pct(sum_covered_branches, sum_total_branches) if sum_total_branches else None
    avg_branch_pct = (sum(r.branch_pct for r in branch_rows if r.branch_pct is not None) / len(branch_rows)) if branch_rows else None

    # Call overall: only count suites with call edges present
    call_rows = [r for r in rows if r.total_calls > 0]
    sum_total_calls = sum(r.total_calls for r in call_rows)
    sum_covered_calls = sum(r.covered_calls for r in call_rows)
    overall_call_pct = pct(sum_covered_calls, sum_total_calls) if sum_total_calls else None
    avg_call_pct = (sum(r.call_pct for r in call_rows if r.call_pct is not None) / len(call_rows)) if call_rows else None

    print("\n[Line coverage aggregate]")
    print(f"  total lines:      {sum_total_lines}")
    print(f"  covered lines:    {sum_covered_lines}")
    print(f"  uncovered lines:  {sum_uncovered_lines}")
    print(f"  overall coverage: {overall_line_pct:.2f}%   (sum covered / sum total)")
    print(f"  average coverage: {avg_line_pct:.2f}%   (mean of per-suite line %)")

    print("\n[Branch coverage aggregate]  (only suites with effective branch edges)")
    if overall_branch_pct is None:
        print("  overall coverage: N/A (no effective branch edges across suites)")
        print("  average coverage: N/A")
    else:
        print(f"  total branches:   {sum_total_branches}")
        print(f"  covered branches: {sum_covered_branches}")
        print(f"  overall coverage: {overall_branch_pct:.2f}%")
        print(f"  average coverage: {avg_branch_pct:.2f}%")

    print("\n[Call coverage aggregate]  (only suites with call edges)")
    if overall_call_pct is None:
        print("  overall coverage: N/A (no call edges across suites)")
        print("  average coverage: N/A")
    else:
        print(f"  total calls:      {sum_total_calls}")
        print(f"  covered calls:    {sum_covered_calls}")
        print(f"  overall coverage: {overall_call_pct:.2f}%")
        print(f"  average coverage: {avg_call_pct:.2f}%")

    # Per-suite table
    print("\n[Per-suite]")
    header = (
        "  {suite:<36} {func:<22} "
        "{tl:>6} {ul:>6} {lp:>8}  "
        "{tb:>6} {bp:>8}  "
        "{tc:>6} {cp:>8}"
    )
    print(header.format(
        suite="suite",
        func="func",
        tl="TLine",
        ul="ULine",
        lp="Line%",
        tb="TBr",
        bp="Br%",
        tc="TCall",
        cp="Call%"
    ))
    print("  " + "-" * 110)
    for r in rows:
        brp = "N/A" if r.branch_pct is None else f"{r.branch_pct:.2f}%"
        cap = "N/A" if r.call_pct is None else f"{r.call_pct:.2f}%"
        print(
            "  {suite:<36} {func:<22} "
            "{tl:>6} {ul:>6} {lp:>7.2f}%  "
            "{tb:>6} {bp:>8}  "
            "{tc:>6} {cp:>8}".format(
                suite=os.path.basename(r.suite_dir),
                func=r.func_name,
                tl=r.total_lines,
                ul=r.uncovered_lines,
                lp=r.line_pct,
                tb=r.total_branches,
                bp=brp,
                tc=r.total_calls,
                cp=cap
            )
        )

    if errors:
        print("\n[Errors]")
        for e in errors:
            print(f"  - {e}")


# -----------------------------
# CLI entrypoints
# -----------------------------
def cmd_suite(suite_dir: str, debug: bool = False):
    inferred = infer_from_suite_dir(suite_dir, debug=debug)
    _, res = compute_row(inferred, debug=debug)
    print_single_suite_report(res, inferred, debug=debug)


def cmd_root(root_my_dir: str, debug: bool = False):
    suite_dirs = list_suite_dirs(root_my_dir, debug=debug)
    rows: List[SuiteAggregateRow] = []
    errors: List[str] = []

    for sd in suite_dirs:
        try:
            inferred = infer_from_suite_dir(sd, debug=debug)
            row, _ = compute_row(inferred, debug=debug)
            rows.append(row)
        except Exception as ex:
            errors.append(f"{sd}: {ex}")

    print_root_summary(rows, errors, root_my_dir)

    # If everything failed, make it obvious via exit code
    if suite_dirs and not rows:
        raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Coverage analyzer for PostgreSQL function test suites.\n\n"
            "Directory naming rules assumed:\n"
            "  - Suite dir:  .../my_<cbase>/test_<func>_suite\n"
            "  - Source C:   .../<cbase>.c (sibling of my_<cbase>)\n"
            "  - Gcov file:  <suite_dir>/<cbase>.c.gcov (fallback: first *.gcov)\n\n"
            "This version remaps branch attribution to decision lines and excludes\n"
            "gcov 'never executed' artifact edges inside executed decisions.\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug prints.")

    sub = parser.add_subparsers(dest="command", required=True)

    p_suite = sub.add_parser(
        "suite",
        help="Analyze a single suite directory (compute coverage for that function)."
    )
    p_suite.add_argument("suite_dir", help="Path to suite dir, e.g. src/backend/utils/adt/my_int/test_int2out_suite")

    p_root = sub.add_parser(
        "root",
        help="Analyze a my_<cbase> directory containing multiple suites (aggregate coverage)."
    )
    p_root.add_argument("root_dir", help="Path to root dir, e.g. src/backend/utils/adt/my_int")

    args = parser.parse_args()

    if args.command == "suite":
        cmd_suite(args.suite_dir, debug=args.debug)
    elif args.command == "root":
        cmd_root(args.root_dir, debug=args.debug)
    else:
        raise SystemExit(2)


if __name__ == "__main__":
    main()