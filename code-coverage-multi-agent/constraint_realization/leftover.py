"""Enumerate leftover gcov lines under catalog/adt (or any gcov roots)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

_GC = re.compile(r"^([^:]*):\s*(\d+):(.*)$")


@dataclass
class GcovLine:
    path: Path
    line: int
    count: str  # ##### / ===== / number / -
    source: str
    guard_hits: int = 0  # if this is a then-line, hits on the owning if


def parse_gcov(path: Path) -> List[GcovLine]:
    rows: List[GcovLine] = []
    if not path.is_file():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _GC.match(raw)
        if not m:
            continue
        ln = int(m.group(2))
        if ln == 0:
            continue
        rows.append(GcovLine(path, ln, m.group(1).strip(), m.group(3)))
    return rows


def _hit(tok: str) -> int:
    if tok in {"#####", "=====", "-", ""}:
        return 0
    try:
        return int(tok.replace("*", ""))
    except ValueError:
        return 0


def then_uncovered(rows: List[GcovLine], if_line: int) -> List[GcovLine]:
    depth = 0
    started = False
    out: List[GcovLine] = []
    for row in rows:
        if row.line < if_line:
            continue
        for ch in row.source:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
        if row.line == if_line:
            continue
        if started and depth <= 0:
            break
        if started and row.count in {"#####", "====="}:
            out.append(row)
    return out


def guard_hit_then_miss(rows: List[GcovLine]) -> List[GcovLine]:
    """if-lines that executed, with at least one ##### in the then-block."""
    by_ln = {r.line: r for r in rows}
    found: List[GcovLine] = []
    for row in rows:
        st = row.source.strip()
        if not st.startswith("if"):
            continue
        hits = _hit(row.count)
        if hits <= 0:
            continue
        miss = then_uncovered(rows, row.line)
        if miss:
            row.guard_hits = hits
            found.append(row)
    return found


def all_uncovered(rows: List[GcovLine]) -> List[GcovLine]:
    return [r for r in rows if r.count in {"#####", "====="}]


def iter_gcov(roots: Iterable[Path]) -> List[Path]:
    files: List[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.name.endswith(".gcov"):
            files.append(root)
            continue
        files.extend(sorted(root.rglob("*.c.gcov")))
    return files


def default_gcov_roots(pg_src: Path) -> List[Path]:
    return [
        pg_src / "src" / "backend" / "catalog",
        pg_src / "src" / "backend" / "utils" / "adt",
    ]


def scan_guard_gaps(pg_src: Path, roots: Optional[List[Path]] = None) -> List[GcovLine]:
    """Paper sampling frame: predicate reached, then still uncovered."""
    gaps: List[GcovLine] = []
    for gcov in iter_gcov(roots or default_gcov_roots(pg_src)):
        rows = parse_gcov(gcov)
        gaps.extend(guard_hit_then_miss(rows))
    return gaps
