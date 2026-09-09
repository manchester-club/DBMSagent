"""Instantiate a session plan from a recovered relation.

LLM fills legal SQL from the relation. It does not read leftover C
and must not invent an operation that is not in sql_template.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .llm import LLMError, complete_chat, extract_json_object
from .recover import ActuationRelation

Completer = Callable[[str], str]


@dataclass
class Session:
    name: str
    role: str
    statements: List[str]


@dataclass
class Plan:
    setup: List[str]
    teardown: List[str]
    holder: Session
    writer: Session
    observer: Session
    catalog: str = ""
    catalog_field: str = ""
    hold_seconds: int = 12
    notes: List[str] = field(default_factory=list)
    via: str = "template"


def _setup_objects(template: str, parent: str, child: str, keep: str) -> List[str]:
    u = template.upper()
    if "PARTITION" in u:
        return [
            f"DROP TABLE IF EXISTS {parent} CASCADE",
            f"CREATE TABLE {parent} (a int) PARTITION BY LIST (a)",
            f"CREATE TABLE {keep} PARTITION OF {parent} FOR VALUES IN (1)",
            f"CREATE TABLE {child} PARTITION OF {parent} FOR VALUES IN (2)",
            f"INSERT INTO {parent} VALUES (1), (2)",
        ]
    if "INDEX" in u:
        return [
            f"DROP TABLE IF EXISTS {parent} CASCADE",
            f"CREATE TABLE {parent} (a int)",
            f"INSERT INTO {parent} VALUES (1)",
        ]
    return [
        f"DROP TABLE IF EXISTS {parent} CASCADE",
        f"CREATE TABLE {parent} (a int)",
        f"INSERT INTO {parent} VALUES (1)",
    ]


def instantiate_template(rel: ActuationRelation, prefix: str = "cr_auto") -> Plan:
    if not rel.sql_template:
        raise RuntimeError("no SQL template recovered; refusing to guess an operation")
    parent = f"{prefix}_p"
    child = f"{prefix}_c"
    keep = f"{prefix}_k"
    writer_sql = rel.sql_template.format(
        parent=parent, child=child, index=f"{prefix}_i", name=parent
    )
    observer_sql = (rel.observer_sql or "SELECT * FROM {parent}").format(
        parent=parent, child=child
    )
    setup = _setup_objects(rel.sql_template, parent, child, keep)
    hold = rel.wait_for_lockers
    holder_stmts = (
        ["BEGIN", f"SELECT * FROM {parent}", f"SELECT pg_sleep({12})", observer_sql, "COMMIT"]
        if hold
        else ["SELECT 1"]
    )
    return Plan(
        setup=setup,
        teardown=[f"DROP TABLE IF EXISTS {parent} CASCADE"],
        holder=Session("holder", "hold_lock_until_observe" if hold else "noop", holder_stmts),
        writer=Session("writer", "actuation_write", [writer_sql]),
        observer=Session("observer", "target_read", [observer_sql]),
        catalog=rel.catalog or "",
        catalog_field=rel.field or "",
        via="template",
        notes=[
            f"template={rel.sql_template}",
            f"wait_for_lockers={rel.wait_for_lockers}",
            f"prevent_in_xact={rel.prevent_in_xact}",
        ],
    )


_SYSTEM = """You are a SQL plan instantiator for PostgreSQL.
You receive an actuation relation recovered by program analysis.
You must NOT invent a different SQL operation than sql_template.
You must NOT read or guess from C source.
Fill in legal object names and session order only.

Return a single JSON object with keys:
  setup: string[]     DDL that makes sql_template executable
  holder: string[]    session that holds a conflicting lock if wait_for_lockers
  writer: string[]    the recovered operation (one top-level command if prevent_in_xact)
  observer: string[]  SQL that re-reads the leftover identity during the window
  teardown: string[]

Rules:
- writer MUST be sql_template with {parent}/{child}/{index}/{name} replaced by real identifiers.
- If wait_for_lockers is true, holder starts with BEGIN, locks the parent, sleeps, then observer SQL, then COMMIT.
- If prevent_in_xact is true, writer is NOT wrapped in BEGIN.
- If wait_for_lockers is false, holder is ["SELECT 1"].
- Prefer prefix in all identifiers.
- No markdown, JSON only.
"""


def _relation_prompt(rel: ActuationRelation, prefix: str, feedback: str = "") -> str:
    body = (
        f"prefix={prefix}\n"
        f"sql_template={rel.sql_template}\n"
        f"observer_sql={rel.observer_sql}\n"
        f"wait_for_lockers={rel.wait_for_lockers}\n"
        f"prevent_in_xact={rel.prevent_in_xact}\n"
        f"lock_object={rel.lock_object}\n"
        f"catalog={rel.catalog}\n"
        f"field={rel.field}\n"
        f"evidence={rel.evidence}\n"
    )
    if feedback:
        body += (
            f"previous_attempt_failed={feedback}\n"
            "Revise identifiers and session order only. Keep sql_template tokens.\n"
        )
    return body


def _as_str_list(val) -> List[str]:
    if val is None:
        return []
    if isinstance(val, str):
        return [val]
    return [str(x) for x in val]


def _validate(rel: ActuationRelation, data: dict) -> None:
    writer = " ".join(_as_str_list(data.get("writer"))).upper()
    tmpl = (rel.sql_template or "").upper()
    tokens = [t for t in ("DETACH", "ATTACH", "CONCURRENTLY", "ENABLE", "DISABLE", "INDEX", "GRANT") if t in tmpl]
    if tokens and not any(t in writer for t in tokens):
        raise LLMError(f"writer does not realize template tokens {tokens}: {writer!r}")
    if rel.wait_for_lockers:
        holder = " ".join(_as_str_list(data.get("holder"))).upper()
        if "BEGIN" not in holder:
            raise LLMError("wait_for_lockers requires holder BEGIN")
    if rel.prevent_in_xact:
        wjoin = " ".join(_as_str_list(data.get("writer"))).upper()
        if wjoin.strip().startswith("BEGIN"):
            raise LLMError("prevent_in_xact forbids wrapping writer in BEGIN")


def plan_from_llm_json(rel: ActuationRelation, data: dict) -> Plan:
    _validate(rel, data)
    hold = rel.wait_for_lockers
    return Plan(
        setup=_as_str_list(data.get("setup")),
        teardown=_as_str_list(data.get("teardown")),
        holder=Session(
            "holder",
            "hold_lock_until_observe" if hold else "noop",
            _as_str_list(data.get("holder")) or ["SELECT 1"],
        ),
        writer=Session("writer", "actuation_write", _as_str_list(data.get("writer"))),
        observer=Session("observer", "target_read", _as_str_list(data.get("observer"))),
        catalog=rel.catalog or "",
        catalog_field=rel.field or "",
        via="llm",
        notes=[
            f"template={rel.sql_template}",
            "instantiator=llm",
        ],
    )


def instantiate_llm(
    rel: ActuationRelation,
    prefix: str = "cr_auto",
    *,
    completer: Optional[Completer] = None,
    feedback: str = "",
) -> Plan:
    prompt = _relation_prompt(rel, prefix, feedback=feedback)
    if completer is not None:
        raw = completer(prompt)
    else:
        raw = complete_chat(prompt, system=_SYSTEM)
    data = extract_json_object(raw)
    return plan_from_llm_json(rel, data)


def instantiate(
    rel: ActuationRelation,
    prefix: str = "cr_auto",
    *,
    use_llm: bool = True,
    completer: Optional[Completer] = None,
    feedback: str = "",
) -> Plan:
    """Default: LLM instantiates from the recovered relation; template is fallback."""
    if not rel.sql_template:
        raise RuntimeError("no SQL template recovered; refusing to guess an operation")
    if use_llm or completer is not None:
        try:
            plan = instantiate_llm(rel, prefix, completer=completer, feedback=feedback)
            return plan
        except Exception as exc:
            fallback = instantiate_template(rel, prefix)
            fallback.notes.append(f"llm_failed={exc}")
            fallback.via = "template_fallback"
            return fallback
    return instantiate_template(rel, prefix)
