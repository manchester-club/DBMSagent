"""Instantiate a session plan from a recovered relation. No leftover C here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .recover import ActuationRelation


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


def _setup_objects(template: str, parent: str, child: str, keep: str) -> List[str]:
    u = template.upper()
    if "PARTITION" in u:
        # DETACH/ATTACH require a partitioned parent; DEFAULT is often forbidden
        # for CONCURRENTLY (recovered separately as no_default via errmsg).
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


def instantiate(rel: ActuationRelation, prefix: str = "cr_auto") -> Plan:
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
        notes=[
            f"template={rel.sql_template}",
            f"wait_for_lockers={rel.wait_for_lockers}",
            f"prevent_in_xact={rel.prevent_in_xact}",
        ],
    )
