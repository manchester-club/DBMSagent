"""Split a leftover predicate: PC_A vs PC_V vs env / named SQL / unrealizable.

The cut is dataflow to alphabet A, not 'looks like an internal variable'.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .extract import Target

_ENV_FILES = {
    "objectaccess.c",
    "pg_upgrade_support.c",
}
_ENV_TOKS = (
    "XLogIsNeeded",
    "wal_level",
    "object_access_hook",
    "IsBinaryUpgrade",
    "pg_upgrade",
    "ApplyingWork",
    "amcheck",
    "MyWalSender",
    "DisableSubscription",
)
_NAMED_SQL_FILES = {
    "aclchk.c",
    "acl.c",
}
_INPUT_TOKS = (
    "timestr",
    "input_string",
    "strval",
    "format_str",
    "numstr",
    "jsonpath",
    "scanstr",
)
_PC_A_FILES = {
    "jsonpath_scan.c",
    "jsonpath_gram.c",
}


@dataclass
class Split:
    kind: str  # PC_A | PC_V | ENV | NAMED_SQL | UNREALIZABLE | SKIP
    reasons: List[str]


def split_constraint(target: Target) -> Split:
    reasons: List[str] = []
    src = target.source
    fname = target.abs_path.name
    blob = f"{fname} {target.function} {src}"

    if fname in _ENV_FILES or any(t in blob for t in _ENV_TOKS):
        reasons.append("conjunct depends on GUC / hook / worker / upgrade, not session SQL")
        return Split("ENV", reasons)

    if fname in _NAMED_SQL_FILES:
        reasons.append("SQL alphabet already has GRANT/REVOKE; leftover is unwritten named SQL")
        return Split("NAMED_SQL", reasons)

    if target.catalog and target.field:
        reasons.append(
            f"predicate reads {target.catalog}.{target.field}; "
            "no taint from the current SQL token buffer"
        )
        return Split("PC_V", reasons)

    if "Form_pg_" in src or "SearchSysCache" in src or "relcache" in src:
        reasons.append("catalog/relcache memory, not current input")
        return Split("PC_V", reasons)

    if fname in _PC_A_FILES or any(t in src for t in _INPUT_TOKS):
        reasons.append("operand taints to the current statement buffer / lexer")
        return Split("PC_A", reasons)

    # Pointer compared to NULL is usually a caller ABI (e.g. tzp always &tz).
    if "NULL" in src and target.field in {"tzp", "p", "isnull"}:
        reasons.append("NULL-pointer conjunct is a caller contract under current A")
        return Split("UNREALIZABLE", reasons)

    if src.strip().startswith("elog") or "cache lookup failed" in src:
        reasons.append("defensive elog, not an actuation target")
        return Split("SKIP", reasons)

    reasons.append("no taint back to A; treat as opaque PC_V candidate")
    return Split("PC_V", reasons)


def family_key(target: Target, split: Split) -> str:
    if split.kind == "PC_V" and target.catalog and target.field:
        return f"{target.catalog}.{target.field}"
    if split.kind == "PC_V" and target.field:
        return f"{target.function}.{target.field}"
    if split.kind == "PC_A":
        return f"pca:{target.rel_path}:{target.line}"
    return f"{split.kind}:{target.rel_path}:{target.line}"
