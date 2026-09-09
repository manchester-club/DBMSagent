"""Recover an actuation relation from a leftover read of V ∉ A.

Do not treat V as an SMT free variable. Walk: write-true → callers →
grammar / utility node → visibility (commit + WaitForLockers).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .c_source import enclosing_function, grep_lines, snippet
from .extract import Target


@dataclass
class WriteSite:
    path: Path
    line: int
    function: str
    polarity: str
    text: str


@dataclass
class ActuationRelation:
    field: str
    catalog: Optional[str]
    write_true: Optional[WriteSite]
    sql_template: Optional[str]
    concurrent_required: bool
    prevent_in_xact: bool
    wait_for_lockers: bool
    lock_object: str
    observer_sql: Optional[str]
    notes: List[str] = field(default_factory=list)
    evidence: Dict[str, str] = field(default_factory=dict)

    @property
    def recoverable(self) -> bool:
        return bool(self.sql_template and self.write_true)


def _is_read_only(line: str, field: str) -> bool:
    st = line.strip()
    if st.startswith("if") and f"->{field}" in st:
        rhs = st.split(field, 1)[-1]
        if "=" not in rhs[:8]:
            return True
    if re.search(rf"->{field}\s*==", line):
        return True
    return False


def find_write_sites(pg_src: Path, target: Target) -> List[WriteSite]:
    field = target.field
    if not field:
        return []
    sites: List[WriteSite] = []
    for path, ln, text in grep_lines(pg_src, rf"->{re.escape(field)}\s*="):
        if _is_read_only(text, field):
            continue
        rhs = text.split("=", 1)[-1]
        if re.search(r"\btrue\b", rhs):
            pol = "true"
        elif re.search(r"\bfalse\b", rhs):
            pol = "false"
        else:
            pol = "unknown"
        fn = enclosing_function(path, ln)
        sites.append(WriteSite(path, ln, fn.name if fn else "", pol, text.strip()))
    if target.catalog:
        anum = f"Anum_{target.catalog}_{field}"
        for path, ln, text in grep_lines(pg_src, re.escape(anum)):
            ctx = snippet(path, max(1, ln - 3), ln + 3)
            pol = None
            if "BoolGetDatum(true)" in ctx:
                pol = "true"
            elif "BoolGetDatum(false)" in ctx:
                pol = "false"
            if pol:
                fn = enclosing_function(path, ln)
                sites.append(WriteSite(path, ln, fn.name if fn else "", pol, text.strip()))
    seen = set()
    uniq: List[WriteSite] = []
    for s in sites:
        k = (str(s.path), s.line)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)
    return uniq


def _callers_of(pg_src: Path, func: str, prefer: Optional[Path] = None) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    for path, ln, _text in grep_lines(pg_src, rf"\b{re.escape(func)}\s*\("):
        fn = enclosing_function(path, ln)
        if fn and fn.name == func:
            continue
        out.append((path, ln, fn.name if fn else ""))
    if prefer:
        out.sort(key=lambda h: (0 if h[0] == prefer else 1, h[1]))
    return out


def _enum_sql_comment(pg_src: Path, enum_name: str) -> Optional[str]:
    header = pg_src / "src" / "include" / "nodes" / "parsenodes.h"
    if not header.is_file():
        return None
    for line in header.read_text(encoding="utf-8", errors="replace").splitlines():
        if enum_name + "," in line or f"{enum_name} " in line:
            m = re.search(r"/\*\s*(.*?)\s*\*/", line)
            if m:
                return m.group(1).strip()
    return None


def _gram_production(pg_src: Path, enum_name: str) -> Tuple[Optional[str], Optional[str]]:
    gram = pg_src / "src" / "backend" / "parser" / "gram.y"
    if not gram.is_file():
        return None, None
    lines = gram.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        if f"subtype = {enum_name}" not in line:
            continue
        comment = None
        for j in range(i, max(0, i - 30), -1):
            m = re.search(r"/\*\s*((?:ALTER|CREATE|DROP|REINDEX|REFRESH)[^*]+)\s*\*/", lines[j])
            if m:
                comment = " ".join(m.group(1).split())
                break
        prod = None
        for j in range(i, max(0, i - 20), -1):
            if lines[j].lstrip().startswith("|"):
                prod = lines[j].strip()
                break
        return comment, prod
    return None, None


def _prevent_in_xact(pg_src: Path, enum_name: str) -> Tuple[bool, Optional[str]]:
    util = pg_src / "src" / "backend" / "tcop" / "utility.c"
    if not util.is_file() or enum_name not in util.read_text(encoding="utf-8", errors="replace"):
        # still search
        pass
    if not util.is_file():
        return False, None
    text = util.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        rf"{re.escape(enum_name)}[\s\S]{{0,500}}PreventInTransactionBlock\([^,]+,\s*\"([^\"]+)\"",
        text,
    )
    if m:
        return True, m.group(1)
    return False, None


def _alter_enum_from_caller(caller_src: str, callee: str) -> Optional[str]:
    if not callee:
        return None
    last = None
    for m in re.finditer(r"case\s+(AT_[A-Za-z0-9_]+)\s*:", caller_src):
        window = caller_src[m.end() : m.end() + 900]
        if re.search(rf"\b{re.escape(callee)}\s*\(", window):
            last = m.group(1)
    return last


def _utility_enum_from_caller(caller_src: str, callee: str) -> Optional[str]:
    last = None
    for m in re.finditer(r"case\s+(T_[A-Za-z0-9_]+)\s*:", caller_src):
        window = caller_src[m.end() : m.end() + 1200]
        if re.search(rf"\b{re.escape(callee)}\s*\(", window):
            last = m.group(1)
    return last


def _force_optional_tokens(comment: Optional[str], prod: Optional[str], concurrent: bool) -> Optional[str]:
    raw = comment or ""
    if not raw and prod:
        return None
    tmpl = raw.replace("<name>", "{parent}").replace("<partition_name>", "{child}")
    tmpl = tmpl.replace("<index_name>", "{index}").replace("<relation>", "{parent}")
    if concurrent:
        tmpl = tmpl.replace("[CONCURRENTLY]", "CONCURRENTLY")
        tmpl = tmpl.replace("[", "").replace("]", "")
        if "CONCURRENTLY" not in tmpl.upper() and prod and "opt_concurrently" in prod:
            tmpl = (tmpl or "ALTER TABLE {parent}").rstrip() + " CONCURRENTLY"
    else:
        tmpl = re.sub(r"\[CONCURRENTLY\]", "", tmpl)
    tmpl = " ".join(tmpl.split())
    return tmpl or None


def _observer_sql(target: Target) -> Optional[str]:
    """User SQL that re-enters the leftover read on the same identity object."""
    fn = target.function or ""
    if any(
        k in fn
        for k in (
            "inheritance_children",
            "PartitionDesc",
            "relcache",
            "find_all_inheritors",
        )
    ):
        return "SELECT * FROM {parent}"
    if target.catalog:
        return "SELECT * FROM {parent}"
    return None


def recover(pg_src: Path, target: Target) -> ActuationRelation:
    notes: List[str] = []
    evidence: Dict[str, str] = {}
    writes = find_write_sites(pg_src, target)
    true_writes = [w for w in writes if w.polarity == "true"]
    notes.append(f"write sites for {target.field}: {len(writes)} ({len(true_writes)} set-true)")

    write_true = true_writes[0] if true_writes else None
    sql_template = None
    concurrent = False
    prevent = False
    wait = False
    lock_object = "unknown"
    enum_name = None

    if write_true:
        evidence["write_true"] = f"{write_true.path}:{write_true.line} {write_true.function}"
        callers = _callers_of(pg_src, write_true.function, prefer=write_true.path)
        notes.append(
            "callers of set-true: "
            + ", ".join(f"{n}@{p.name}:{ln}" for p, ln, n in callers[:8] if n)
        )
        hop: List[Tuple[Path, int, str]] = list(callers)
        seen = {write_true.function}
        for path, ln, cname in callers:
            if cname and cname not in seen:
                seen.add(cname)
                hop.extend(_callers_of(pg_src, cname, prefer=path)[:12])
        chain = [write_true.function] + [n for _, _, n in hop if n]
        for path, ln, cname in hop:
            whole = enclosing_function(path, ln)
            whole_src = snippet(path, whole.start, whole.end) if whole else snippet(path, ln - 40, ln + 40)
            if "WaitForLockers" in whole_src and "CommitTransactionCommand" in whole_src:
                wait = True
                evidence["wait"] = f"{path.name}:{cname}"
            if re.search(r"if\s*\(\s*!?concurrent\s*\)", whole_src) and write_true.function in whole_src:
                concurrent = True
            if "SET_LOCKTAG_RELATION" in whole_src and "parentrelid" in whole_src:
                lock_object = "parent"
            for callee in chain:
                enum_name = _alter_enum_from_caller(whole_src, callee) or enum_name
                if not enum_name:
                    ut = _utility_enum_from_caller(whole_src, callee)
                    if ut:
                        evidence["utility_node"] = ut
            if not enum_name:
                ctx = snippet(path, max(1, ln - 30), ln)
                m = re.search(r"case\s+(AT_[A-Za-z0-9_]+)", ctx)
                if m:
                    enum_name = m.group(1)

        if enum_name:
            evidence["enum"] = enum_name
            gram_comment, prod = _gram_production(pg_src, enum_name)
            evidence["gram"] = gram_comment or prod or ""
            sql_template = _force_optional_tokens(gram_comment, prod, concurrent)
            if not sql_template:
                sql_template = _enum_sql_comment(pg_src, enum_name)
            prevent, cmdstr = _prevent_in_xact(pg_src, enum_name)
            if cmdstr:
                evidence["prevent_in_xact"] = cmdstr
            if concurrent and sql_template and "CONCURRENTLY" not in sql_template.upper():
                sql_template += " CONCURRENTLY"

    observer = _observer_sql(target)
    if observer:
        notes.append(f"observer from leftover function {target.function}: {observer}")
    if not sql_template:
        notes.append("no grammar/utility mapping for the set-true write")

    return ActuationRelation(
        field=target.field,
        catalog=target.catalog,
        write_true=write_true,
        sql_template=sql_template,
        concurrent_required=concurrent,
        prevent_in_xact=prevent,
        wait_for_lockers=wait,
        lock_object=lock_object if wait else lock_object,
        observer_sql=observer,
        notes=notes,
        evidence=evidence,
    )
