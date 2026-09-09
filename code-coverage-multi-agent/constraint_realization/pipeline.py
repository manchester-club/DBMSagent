from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .extract import extract, extract_from_gcov_line
from .instantiate import instantiate
from .leftover import default_gcov_roots, scan_guard_gaps
from .recover import recover
from .split import Split, family_key, split_constraint


def _print(title: str, body: str = "") -> None:
    print(f"\n== {title} ==")
    if body:
        print(body)


def run_one(pg_src: Path, spec: str, *, do_execute: bool, use_llm: bool = True) -> Dict[str, Any]:
    from .execute import execute
    from .verify import compare, snapshot_then

    target = extract(pg_src, spec)
    sp = split_constraint(target)
    rec: Dict[str, Any] = {
        "target": f"{target.rel_path}:{target.line}",
        "function": target.function,
        "field": target.field,
        "catalog": target.catalog,
        "split": sp.kind,
        "reasons": sp.reasons,
    }
    _print("EXTRACT", f"{target.rel_path}:{target.line} {target.function}() {target.source}")
    _print("SPLIT", f"{sp.kind}: " + "; ".join(sp.reasons))
    if sp.kind != "PC_V":
        rec["verdict"] = sp.kind
        return rec
    rel = recover(pg_src, target)
    rec["relation"] = {
        "sql_template": rel.sql_template,
        "wait_for_lockers": rel.wait_for_lockers,
        "prevent_in_xact": rel.prevent_in_xact,
        "evidence": rel.evidence,
        "notes": rel.notes,
    }
    _print("RECOVER", json.dumps(rec["relation"], indent=2, ensure_ascii=False))
    if not rel.recoverable:
        rec["verdict"] = "UNKNOWN"
        return rec
    prefix = f"cr_{int(time.time()) % 100000}"
    plan = instantiate(rel, prefix=prefix, use_llm=use_llm)
    rec["plan"] = {
        "via": plan.via,
        "setup": plan.setup,
        "holder": plan.holder.statements,
        "writer": plan.writer.statements,
        "observer": plan.observer.statements,
        "notes": plan.notes,
    }
    _print("INSTANTIATE", f"via={plan.via}\n" + "\n".join(plan.writer.statements))
    if not do_execute:
        rec["verdict"] = "RECOVERED"
        return rec
    before = snapshot_then(target)
    result = execute(plan)
    after = snapshot_then(target)
    ver = compare(before, after, target.line)
    rec["execute"] = {"ok": result.ok, "flag_seen_true": result.flag_seen_true, "log": result.log}
    rec["verify"] = {"then_gained": ver.then_gained}
    rec["verdict"] = "REALIZABLE" if ver.ok or result.flag_seen_true else "FAILED"
    _print("VERIFY", rec["verdict"] + " gained=" + str(ver.then_gained))
    return rec


def run_all(
    pg_src: Path,
    *,
    do_execute: bool,
    gcov_roots: Optional[List[Path]] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    gaps = scan_guard_gaps(pg_src, gcov_roots)
    buckets: Dict[str, list] = defaultdict(list)
    kind_counts: Dict[str, int] = defaultdict(int)
    for row in gaps:
        try:
            target = extract_from_gcov_line(pg_src, row)
        except Exception:
            continue
        sp = split_constraint(target)
        kind_counts[sp.kind] += 1
        key = family_key(target, sp)
        buckets[key].append((target, sp, row.guard_hits))

    families: List[Dict[str, Any]] = []
    for key, items in sorted(buckets.items(), key=lambda kv: -max(x[2] for x in kv[1])):
        # representative: most-hit leftover in the family
        items.sort(key=lambda x: -x[2])
        target, sp, hits = items[0]
        entry: Dict[str, Any] = {
            "family": key,
            "kind": sp.kind,
            "members": len(items),
            "guard_hits": hits,
            "example": f"{target.rel_path}:{target.line}",
            "function": target.function,
            "reasons": sp.reasons,
        }
        if sp.kind == "PC_V":
            rel = recover(pg_src, target)
            entry["sql_template"] = rel.sql_template
            entry["wait_for_lockers"] = rel.wait_for_lockers
            entry["evidence"] = rel.evidence
            entry["notes"] = rel.notes
            if rel.recoverable:
                entry["verdict"] = "RECOVERED"
                try:
                    plan = instantiate(
                        rel,
                        prefix=f"cr_{abs(hash(key)) % 100000}",
                        use_llm=use_llm,
                    )
                    entry["plan_via"] = plan.via
                    entry["writer"] = plan.writer.statements
                    entry["instantiate_notes"] = plan.notes
                except Exception as exc:
                    entry["plan_via"] = "failed"
                    entry["error"] = str(exc)
                if do_execute and entry.get("plan_via") not in {None, "failed"}:
                    try:
                        from .execute import execute

                        plan = instantiate(
                            rel,
                            prefix=f"cr_{abs(hash(key)) % 100000}",
                            use_llm=use_llm,
                        )
                        result = execute(plan)
                        entry["execute_ok"] = result.ok
                        entry["flag_seen_true"] = result.flag_seen_true
                        entry["verdict"] = "REALIZABLE" if result.ok else "FAILED"
                    except Exception as exc:
                        entry["verdict"] = "UNKNOWN"
                        entry["error"] = str(exc)
            else:
                entry["verdict"] = "UNKNOWN"
        elif sp.kind == "ENV":
            entry["verdict"] = "CONDITIONALLY"
        elif sp.kind == "UNREALIZABLE":
            entry["verdict"] = "UNREALIZABLE UNDER A"
        elif sp.kind == "PC_A":
            entry["verdict"] = "INPUT_REALIZATION"
        else:
            entry["verdict"] = sp.kind
        families.append(entry)

    report = {
        "pg_src": str(pg_src),
        "guard_hit_then_miss": len(gaps),
        "kind_counts": dict(kind_counts),
        "family_count": len(families),
        "pc_v_recovered": sum(1 for f in families if f.get("verdict") in {"RECOVERED", "REALIZABLE"}),
        "families": families,
    }
    return report


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Constraint realization for leftover DBMS branches (all families, not one example)."
    )
    p.add_argument("--pg-src", default=str(config.PG_SRC), help="PostgreSQL source root")
    p.add_argument("--target", help="single FILE:LINE (relative to --pg-src)")
    p.add_argument("--all", action="store_true", help="scan catalog+adt guard-hit/then-miss leftovers")
    p.add_argument("--execute", action="store_true", help="run instantiated SQL on PGHOST/PGPORT")
    p.add_argument("--gcov-root", action="append", help="extra .gcov directory (repeatable)")
    p.add_argument("--json-out", help="write report JSON")
    p.add_argument(
        "--no-llm",
        action="store_true",
        help="use the deterministic template instantiator instead of the LLM",
    )
    args = p.parse_args(argv)
    pg_src = Path(args.pg_src)
    use_llm = not args.no_llm

    if args.all or not args.target:
        if not args.target:
            args.all = True
        roots = [Path(x) for x in args.gcov_root] if args.gcov_root else default_gcov_roots(pg_src)
        report = run_all(
            pg_src, do_execute=args.execute, gcov_roots=roots, use_llm=use_llm
        )
        _print(
            "ALL leftover families",
            f"guard-hit/then-miss={report['guard_hit_then_miss']} "
            f"kinds={report['kind_counts']} families={report['family_count']} "
            f"pc_v_recovered={report['pc_v_recovered']}",
        )
        for fam in report["families"]:
            extra = fam.get("writer") or fam.get("sql_template") or fam["kind"]
            via = fam.get("plan_via")
            via_s = f" via={via}" if via else ""
            print(
                f"  [{fam['verdict']}] {fam['family']}  n={fam['members']}  "
                f"hits={fam['guard_hits']}  {fam['example']}{via_s}  {extra}"
            )
    else:
        report = run_one(pg_src, args.target, do_execute=args.execute, use_llm=use_llm)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
