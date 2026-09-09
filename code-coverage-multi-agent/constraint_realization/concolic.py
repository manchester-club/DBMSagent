"""Leftover-branch concolic over alphabet A (PC_A input realization).

This is not whole-program angr/KLEE, and it is not catalog SMT.

At a leftover `if` the guard already executed (gcov hit) and the then-block
did not. Classic concolic: keep the concrete prefix, negate that last
decision, solve only for variables in the current SQL alphabet A.

Variables not in A stay concrete:
  - catalog / relcache (V) → wrong solver; use recover_family
  - pointer ABI / GUC (B) → inspect live callers; do not treat as free SMT vars

A SAT model on the extracted slice is `sat_on_slice`. That is the datetime.c
trap: unconstrained `tzp == NULL` is SAT, but every live `time_in`/`timetz_in`
passes `&tz`, so the conjunct is UNREALIZABLE UNDER A,E,B. Slice HIT is not
PostgreSQL coverage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .c_source import enclosing_function, grep_lines, snippet
from .extract import Target
from .instantiate import Plan, plan_from_input_sql

_CTRL_TYPES = {
    "char",
    "int",
    "const",
    "unsigned",
    "void",
    "struct",
    "bool",
    "Oid",
    "Datum",
    "static",
    "inline",
    "extern",
    "long",
    "short",
    "size_t",
    "float",
    "double",
    "HeapTuple",
    "List",
    "bytea",
    "text",
}

_STRINGISH = ("str", "input", "buf", "scan", "jsonpath", "timestr", "numstr", "fmt")


@dataclass
class Atom:
    kind: str  # eq_char | ne_char | prefix | ptr_null | ptr_nonnull | catalog
    var: str
    index: Optional[int] = None
    value: Optional[str] = None
    in_alphabet: bool = False


@dataclass
class InputRealization:
    status: str  # SAT | UNREALIZABLE | UNKNOWN | WRONG_SOLVER
    sat_on_slice: bool
    realizable_under_callers: bool
    model: Optional[str]
    sql: Optional[str]
    alphabet_vars: List[str]
    concretized: Dict[str, str]
    notes: List[str] = field(default_factory=list)
    evidence: Dict[str, str] = field(default_factory=dict)
    atoms: List[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.status == "UNREALIZABLE":
            return "UNREALIZABLE UNDER A,E,B"
        if self.status == "SAT" and self.sql:
            return "INPUT_REALIZED"
        if self.status == "WRONG_SOLVER":
            return "UNKNOWN"
        return "UNKNOWN"

    def public(self) -> Dict:
        return {
            "status": self.status,
            "verdict": self.verdict,
            "sat_on_slice": self.sat_on_slice,
            "realizable_under_callers": self.realizable_under_callers,
            "model": self.model,
            "sql": self.sql,
            "alphabet_vars": self.alphabet_vars,
            "concretized": self.concretized,
            "notes": self.notes,
            "evidence": self.evidence,
            "atoms": self.atoms,
        }


def _match_parens(s: str, open_at: int) -> Optional[int]:
    depth = 0
    for i in range(open_at, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


def leftover_condition(source: str) -> Optional[str]:
    s = source.strip()
    if not s.startswith("if"):
        return None
    i = s.find("(")
    if i < 0:
        return None
    j = _match_parens(s, i)
    if j is None:
        return None
    return s[i + 1 : j].strip()


def _split_and(cond: str) -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    i = 0
    while i < len(cond):
        ch = cond[i]
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif depth == 0 and cond.startswith("&&", i):
            parts.append("".join(buf).strip())
            buf = []
            i += 2
            continue
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p[1:-1].strip() if p.startswith("(") and p.endswith(")") and _match_parens(p, 0) == len(p) - 1 else p for p in parts]


def _fn_params(pg_src: Path, target: Target) -> List[Tuple[str, str]]:
    """Return (name, raw_decl) for the enclosing function."""
    fn = enclosing_function(target.abs_path, target.line)
    if not fn:
        return []
    head = snippet(target.abs_path, fn.start, min(fn.start + 8, fn.end))
    open_at = head.find("(")
    if open_at < 0:
        return []
    close = _match_parens(head, open_at)
    if close is None:
        return []
    inner = head[open_at + 1 : close]
    out: List[Tuple[str, str]] = []
    for part in inner.split(","):
        raw = " ".join(part.split())
        if not raw or raw == "void":
            continue
        ids = [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw) if t not in _CTRL_TYPES]
        if ids:
            out.append((ids[-1], raw))
    return out


def _string_params(params: List[Tuple[str, str]]) -> List[str]:
    names = []
    for name, decl in params:
        d = decl.lower()
        if "*" in decl and ("char" in d or "text" in d or "bytea" in d):
            names.append(name)
            continue
        if any(tok in name.lower() for tok in _STRINGISH):
            names.append(name)
    return names


def _in_alphabet(var: str, string_params: List[str]) -> bool:
    if var in string_params:
        return True
    return any(tok in var.lower() for tok in _STRINGISH)


def _parse_atom(term: str, string_params: List[str]) -> Optional[Atom]:
    t = " ".join(term.split())
    m = re.search(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(\d+)\s*\]\s*==\s*'((?:\\.|[^'\\]))'",
        t,
    )
    if m:
        return Atom("eq_char", m.group(1), int(m.group(2)), m.group(3), _in_alphabet(m.group(1), string_params))
    m = re.search(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(\d+)\s*\]\s*!=\s*'((?:\\.|[^'\\]))'",
        t,
    )
    if m:
        return Atom("ne_char", m.group(1), int(m.group(2)), m.group(3), _in_alphabet(m.group(1), string_params))
    m = re.search(r"\*\s*([A-Za-z_][A-Za-z0-9_]*)\s*==\s*'((?:\\.|[^'\\]))'", t)
    if m:
        return Atom("eq_char", m.group(1), 0, m.group(2), _in_alphabet(m.group(1), string_params))
    m = re.search(
        r"(?:pg_)?(?:strncasecmp|strncmp|strncasecmp)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*\"([^\"]+)\"\s*,\s*(\d+)\s*\)\s*==\s*0",
        t,
        re.I,
    )
    if m:
        return Atom("prefix", m.group(1), int(m.group(3)), m.group(2), _in_alphabet(m.group(1), string_params))
    m = re.search(
        r"(?:pg_)?(?:strcasecmp|strcmp)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*\"([^\"]+)\"\s*\)\s*==\s*0",
        t,
        re.I,
    )
    if m:
        return Atom("prefix", m.group(1), len(m.group(2)), m.group(2), _in_alphabet(m.group(1), string_params))
    m = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*==\s*NULL\b", t)
    if m:
        return Atom("ptr_null", m.group(1), in_alphabet=False)
    m = re.search(r"\bNULL\s*==\s*([A-Za-z_][A-Za-z0-9_]*)\b", t)
    if m:
        return Atom("ptr_null", m.group(1), in_alphabet=False)
    m = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*!=\s*NULL\b", t)
    if m:
        return Atom("ptr_nonnull", m.group(1), in_alphabet=False)
    if "->" in t or "Form_pg_" in t:
        vm = re.search(r"->([A-Za-z_][A-Za-z0-9_]*)", t)
        return Atom("catalog", vm.group(1) if vm else "field", in_alphabet=False)
    return None


def _split_c_args(inner: str) -> List[str]:
    args: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in inner:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        args.append("".join(buf).strip())
    return [a for a in args if a]


def _call_arg_for_param(pg_src: Path, func: str, param_index: int) -> List[str]:
    args_at_calls: List[str] = []
    for path, ln, text in grep_lines(pg_src, rf"\b{re.escape(func)}\s*\("):
        enc = enclosing_function(path, ln)
        if enc and enc.name == func:
            continue
        window = snippet(path, ln, ln + 8)
        m = re.search(rf"\b{re.escape(func)}\s*\(", window)
        if not m:
            continue
        abs_open = m.end() - 1
        close = _match_parens(window, abs_open)
        if close is None:
            continue
        parts = _split_c_args(window[abs_open + 1 : close])
        if param_index < len(parts):
            args_at_calls.append(parts[param_index].strip())
    return args_at_calls


def _never_null(args: List[str]) -> Optional[bool]:
    """True → every live caller passes an address; False → some NULL; None unknown."""
    if not args:
        return None
    flags = []
    for a in args:
        if a.startswith("&"):
            flags.append(True)
        elif a in {"NULL", "0", "nullptr"}:
            flags.append(False)
        else:
            flags.append(None)
    if flags and all(x is True for x in flags):
        return True
    if any(x is False for x in flags):
        return False
    return None


def _solve_string(atoms: List[Atom]) -> Tuple[Optional[str], str]:
    relevant = [a for a in atoms if a.kind in {"eq_char", "ne_char", "prefix"} and a.in_alphabet]
    if not relevant:
        return None, "enum"
    n = 8
    for a in relevant:
        if a.kind in {"eq_char", "ne_char"} and a.index is not None:
            n = max(n, a.index + 1)
        if a.kind == "prefix" and a.value:
            n = max(n, len(a.value))
    try:
        import z3  # type: ignore

        s = z3.Solver()
        chars = [z3.BitVec(f"a{i}", 8) for i in range(n)]
        for c in chars:
            s.add(c >= 32, c <= 126)
            s.add(c != 39)  # no single-quote in the model
        for a in relevant:
            if a.kind == "eq_char" and a.index is not None and a.value:
                s.add(chars[a.index] == ord(a.value[0]))
            elif a.kind == "ne_char" and a.index is not None and a.value:
                s.add(chars[a.index] != ord(a.value[0]))
            elif a.kind == "prefix" and a.value:
                for i, ch in enumerate(a.value):
                    s.add(chars[i] == ord(ch))
        if s.check() != z3.sat:
            return None, "z3"
        model = s.model()
        out = "".join(chr(model.eval(c).as_long()) for c in chars)
        return out, "z3"
    except Exception:
        buf = ["0"] * n
        for a in relevant:
            if a.kind == "prefix" and a.value:
                for i, ch in enumerate(a.value):
                    buf[i] = ch
            elif a.kind == "eq_char" and a.index is not None and a.value:
                buf[a.index] = a.value[0]
        for a in relevant:
            if a.kind == "ne_char" and a.index is not None and a.value:
                if buf[a.index] == a.value[0]:
                    buf[a.index] = "1" if a.value[0] != "1" else "2"
        return "".join(buf), "enum"


def wrap_sql(target: Target, model: str) -> str:
    blob = f"{target.function} {target.rel_path}".lower()
    esc = (model or "").replace("'", "''")
    if "jsonpath" in blob:
        return f"SELECT '{esc}'::jsonpath"
    if "timetz" in blob:
        return f"SELECT TIMETZ '{esc}'"
    if re.search(r"time", target.function, re.I) and "timestamp" not in blob:
        return f"SELECT TIME '{esc}'"
    if re.search(r"date", target.function, re.I):
        return f"SELECT DATE '{esc}'"
    if "timestamp" in blob:
        return f"SELECT TIMESTAMP '{esc}'"
    return f"SELECT '{esc}'"


def plan_from_realization(ir: InputRealization) -> Plan:
    if not ir.sql:
        raise RuntimeError("no SQL from input realization")
    return plan_from_input_sql(
        ir.sql,
        notes=[
            f"status={ir.status}",
            f"sat_on_slice={ir.sat_on_slice}",
            f"realizable_under_callers={ir.realizable_under_callers}",
            f"model={ir.model}",
        ],
    )


def realize(pg_src: Path, target: Target) -> InputRealization:
    notes: List[str] = []
    evidence: Dict[str, str] = {}
    params = _fn_params(pg_src, target)
    str_params = _string_params(params)
    cond = leftover_condition(target.source)
    evidence["condition"] = cond or target.source
    if not cond:
        return InputRealization(
            "UNKNOWN", False, False, None, None, str_params, {}, notes=["no if-condition to negate"], evidence=evidence
        )

    terms = _split_and(cond)
    atoms: List[Atom] = []
    for term in terms:
        atom = _parse_atom(term, str_params)
        if atom is None:
            notes.append(f"unparsed conjunct: {term}")
            continue
        atoms.append(atom)

    if any(a.kind == "catalog" for a in atoms):
        notes.append("conjunct reads catalog/relcache memory; not in A. Do not SMT-symbolize V.")
        return InputRealization(
            "WRONG_SOLVER",
            False,
            False,
            None,
            None,
            str_params,
            {},
            notes=notes,
            evidence=evidence,
            atoms=[a.kind for a in atoms],
        )

    param_names = [n for n, _ in params]
    concretized: Dict[str, str] = {}
    caller_blocks = False
    slice_sat = False

    ptr_atoms = [a for a in atoms if a.kind in {"ptr_null", "ptr_nonnull"}]
    for a in ptr_atoms:
        if a.var not in param_names:
            notes.append(f"{a.var} is not a parameter; cannot discharge via callers")
            continue
        idx = param_names.index(a.var)
        fn = enclosing_function(target.abs_path, target.line)
        callee = fn.name if fn else target.function
        call_args = _call_arg_for_param(pg_src, callee, idx)
        evidence[f"callers_{a.var}"] = ", ".join(call_args) or "(none)"
        never = _never_null(call_args)
        # Unconstrained pointer makes the slice SAT (the angr/KLEE trap).
        slice_sat = True
        notes.append(f"slice treats {a.var} as free → SAT for {a.kind}")
        if a.kind == "ptr_null" and never is True:
            caller_blocks = True
            concretized[a.var] = "always_nonnull_address"
            notes.append(
                f"every live caller of {callee} passes a non-NULL {a.var}; "
                "UNREALIZABLE UNDER A,E,B (slice HIT ≠ coverage)"
            )
        elif a.kind == "ptr_nonnull" and never is False:
            caller_blocks = True
            concretized[a.var] = "always_null"
            notes.append(f"every live caller passes NULL for {a.var}")
        elif never is None and not call_args:
            notes.append(f"no callers of {callee}; cannot prove B")
        elif a.kind == "ptr_null" and never is False:
            notes.append(f"some caller passes NULL for {a.var}; ABI allows the then-branch")
            concretized[a.var] = "null_possible"
        elif a.kind == "ptr_nonnull" and never is True:
            notes.append(f"callers already pass non-NULL {a.var}; then-branch is the concrete path")
            concretized[a.var] = "already_nonnull"

    alpha_atoms = [a for a in atoms if a.in_alphabet]
    model, solver = _solve_string(atoms)
    if alpha_atoms:
        if model is None:
            notes.append(f"{solver} could not solve alphabet conjuncts")
        else:
            slice_sat = True
            evidence["solver"] = solver
            evidence["model"] = model
            notes.append(f"negated leftover over A; {solver} model={model!r}")

    if caller_blocks:
        return InputRealization(
            "UNREALIZABLE",
            sat_on_slice=True,
            realizable_under_callers=False,
            model=None,
            sql=None,
            alphabet_vars=str_params,
            concretized=concretized,
            notes=notes,
            evidence=evidence,
            atoms=[f"{a.kind}:{a.var}" for a in atoms],
        )

    if not atoms:
        return InputRealization(
            "UNKNOWN", False, False, None, None, str_params, concretized, notes=notes, evidence=evidence
        )

    if alpha_atoms and model:
        sql = wrap_sql(target, model)
        return InputRealization(
            "SAT",
            sat_on_slice=True,
            realizable_under_callers=True,
            model=model,
            sql=sql,
            alphabet_vars=str_params,
            concretized=concretized,
            notes=notes,
            evidence=evidence,
            atoms=[f"{a.kind}:{a.var}" for a in atoms],
        )

    if ptr_atoms and not caller_blocks and slice_sat:
        # ABI allows NULL and we have no alphabet model — still not a SQL input.
        notes.append("pointer conjunct is in B, not A; no SQL token realizes it")
        return InputRealization(
            "UNKNOWN",
            sat_on_slice=True,
            realizable_under_callers=bool(concretized.get(ptr_atoms[0].var) == "null_possible"),
            model=None,
            sql=None,
            alphabet_vars=str_params,
            concretized=concretized,
            notes=notes,
            evidence=evidence,
            atoms=[f"{a.kind}:{a.var}" for a in atoms],
        )

    return InputRealization(
        "UNKNOWN",
        slice_sat,
        False,
        model,
        None,
        str_params,
        concretized,
        notes=notes or ["no alphabet preimage for leftover conjunct"],
        evidence=evidence,
        atoms=[f"{a.kind}:{a.var}" for a in atoms],
    )
