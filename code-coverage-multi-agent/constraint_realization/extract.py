from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .c_source import enclosing_function
from .leftover import GcovLine, parse_gcov, then_uncovered

_FIELD = re.compile(r"(?:->|\.)([A-Za-z_][A-Za-z0-9_]*)")
_FORM = re.compile(r"\bForm_pg_([A-Za-z0-9_]+)")


@dataclass
class Target:
    rel_path: str
    abs_path: Path
    line: int
    source: str
    function: str
    field: str
    catalog: Optional[str]
    gcov_count: Optional[str]
    then_uncovered: List[int] = field(default_factory=list)
    guard_hits: int = 0


def _resolve(pg_src: Path, spec: str) -> tuple[Path, int, str]:
    spec = spec.strip()
    if ":" not in spec:
        raise ValueError("target must be FILE:LINE")
    path_s, ln_s = spec.rsplit(":", 1)
    line = int(ln_s)
    abs_path = Path(path_s)
    if not abs_path.is_file():
        for cand in (pg_src / path_s, pg_src / "src" / path_s):
            if cand.is_file():
                abs_path = cand
                break
    if not abs_path.is_file():
        raise FileNotFoundError(path_s)
    try:
        rel = str(abs_path.relative_to(pg_src))
    except ValueError:
        rel = str(abs_path)
    return abs_path, line, rel


def _field_and_catalog(source: str) -> tuple[str, Optional[str]]:
    fields = [f for f in _FIELD.findall(source) if f not in {"t_data", "t_self"}]
    field = fields[-1] if fields else ""
    form = _FORM.search(source)
    catalog = f"pg_{form.group(1)}" if form else None
    return field, catalog


def extract_from_gcov_line(pg_src: Path, row: GcovLine) -> Target:
    name = row.path.name
    src_c = row.path.parent / (name[:-5] if name.endswith(".gcov") else name)
    if not src_c.is_file():
        src_c = row.path.parent / name.replace(".gcov", "")
    fn = enclosing_function(src_c, row.line) if src_c.is_file() else None
    field, catalog = _field_and_catalog(row.source)
    try:
        rel = str(src_c.relative_to(pg_src))
    except ValueError:
        rel = str(src_c)
    gcov_rows = parse_gcov(row.path)
    then_miss = [r.line for r in then_uncovered(gcov_rows, row.line)]
    return Target(
        rel_path=rel,
        abs_path=src_c,
        line=row.line,
        source=row.source.strip(),
        function=fn.name if fn else "",
        field=field,
        catalog=catalog,
        gcov_count=row.count,
        then_uncovered=then_miss,
        guard_hits=row.guard_hits,
    )


def extract(pg_src: Path, spec: str) -> Target:
    abs_path, line, rel = _resolve(pg_src, spec)
    lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    source = lines[line - 1] if 0 < line <= len(lines) else ""
    fn = enclosing_function(abs_path, line)
    field, catalog = _field_and_catalog(source)
    gcov = Path(str(abs_path) + ".gcov")
    count = None
    then_miss: List[int] = []
    if gcov.is_file():
        rows = parse_gcov(gcov)
        for r in rows:
            if r.line == line:
                count = r.count
                source = r.source
                field, catalog = _field_and_catalog(source)
                then_miss = [x.line for x in then_uncovered(rows, line)]
                break
    return Target(
        rel_path=rel,
        abs_path=abs_path,
        line=line,
        source=source.strip(),
        function=fn.name if fn else "",
        field=field,
        catalog=catalog,
        gcov_count=count,
        then_uncovered=then_miss,
    )
