"""Agentic constraint realization: supervisor + analysis tools.

This is not the 金箍 LangGraph loop (try seed SQL, then read C to guess more
SQL). Recovery stays program analysis. The LLM supervisor only schedules
families and retries instantiation; the instantiator LLM only fills legal
SQL from an already-recovered relation.

Tools:
  scan_leftovers / load_target
  recover_family          # write-site → callers → grammar
  instantiate_plan        # LLM or template; optional feedback on retry
  execute_plan / verify_family
  record_verdict / finish
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .concolic import InputRealization, plan_from_realization, realize
from .extract import Target, extract, extract_from_gcov_line
from .instantiate import Plan, instantiate
from .leftover import default_gcov_roots, scan_guard_gaps
from .llm import LLMError, complete_chat
from .recover import ActuationRelation, recover
from .split import family_key, split_constraint

SupervisorComplete = Callable[..., str]
ExecuteFn = Callable[[Plan], Any]
VerifyFn = Callable[[Target], Any]

_KIND_VERDICT = {
    "ENV": "CONDITIONALLY",
    "NAMED_SQL": "NAMED_SQL",
    "SKIP": "SKIP",
}

TOOL_SCHEMAS = """
scan_leftovers()
  Group catalog/adt leftovers that hit the guard and missed the then-block.

recover_family(family_id)
  PC_V only. Write-true → callers → grammar. Returns sql_template.
  REQUIRED before instantiate_plan. Do not invent SQL from leftover C.
  Do not use this for PC_A.

realize_input(family_id)
  PC_A leftover-branch concolic: negate the last decision over alphabet A.
  Pointer/GUC conjuncts are discharged by live callers (B), not as free SMT vars.
  Catalog conjuncts are rejected (use recover_family). Slice SAT is not coverage.

instantiate_plan(family_id, feedback?)
  Fill legal SQL from the recovered sql_template only.
  On execute/verify failure, call again with feedback=the error.

execute_plan(family_id)
  Run the instantiated sessions (holder / writer / observer).

verify_family(family_id)
  Compare gcov then-block hits after execute.

record_verdict(family_id, verdict)
  REALIZABLE | RECOVERED | INPUT_REALIZED | FAILED | UNKNOWN | CONDITIONALLY |
  UNREALIZABLE UNDER A,E,B | NAMED_SQL | SKIP

finish()
  Stop when every family has a verdict.
"""

SUPERVISOR_SYSTEM = f"""You are the constraint-realization supervisor.

One method, two solvers. Leftover families split PC_A / PC_V / ENV:
- PC_V: recover actuation relation by program analysis, then instantiate.
- PC_A: leftover-branch concolic over alphabet A (realize_input).
Standard concolic must NOT symbolize catalog memory (inhdetachpending etc.).

You MUST:
- Call scan_leftovers first (unless a single target is already loaded).
- For ENV / NAMED_SQL / SKIP: record_verdict from the split. Do not recover
  or realize those.
- For PC_V: call recover_family BEFORE instantiate_plan. Never invent SQL
  from leftover C, function names, or write-site text.
- For PC_A (and UNREALIZABLE ABI leftovers): call realize_input. Do not
  recover_family. Do not record INPUT_REALIZED without a SAT model over A.
  If realize_input reports sat_on_slice but realizable_under_callers=false,
  record_verdict UNREALIZABLE UNDER A,E,B (slice HIT ≠ coverage).
- instantiate_plan fills identifiers/session order from sql_template only.
- If execute_plan or verify_family fails, instantiate_plan again with
  feedback set to the error (at most 3 attempts per family), then
  record_verdict FAILED if still unsuccessful.
- If execute is disabled: PC_V → RECOVERED after instantiate_plan;
  PC_A → INPUT_REALIZED after realize_input SAT. Do not call execute_plan.
- After every family has a verdict, call finish.

You never recover write-sites yourself. recover_family is the only source
of sql_template. realize_input is the only PC_A solver.

Reply in this form:
Thought: <one sentence>
Action: <tool name>
Action Input: <JSON object or empty {{}}>

Tools:
{TOOL_SCHEMAS}
"""


@dataclass
class AgentConfig:
    pg_src: Path
    gcov_roots: Optional[List[Path]] = None
    use_llm_instantiate: bool = True
    use_llm_supervisor: bool = True
    do_execute: bool = False
    dry_run_execute: bool = False
    max_steps: int = 40
    max_retries: int = 3
    target: Optional[str] = None
    instantiate_completer: Optional[Callable[[str], str]] = None
    supervisor_complete: Optional[SupervisorComplete] = None
    execute_fn: Optional[ExecuteFn] = None
    verify_fn: Optional[VerifyFn] = None


@dataclass
class FamilyRecord:
    family: str
    kind: str
    members: int
    guard_hits: int
    example: str
    function: str
    reasons: List[str]
    target: Target
    relation: Optional[ActuationRelation] = None
    realization: Optional[InputRealization] = None
    plan: Optional[Plan] = None
    before: Optional[Dict[int, str]] = None
    last_execute: Optional[Dict[str, Any]] = None
    last_verify: Optional[Dict[str, Any]] = None
    verdict: Optional[str] = None
    attempts: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class AgentState:
    families: Dict[str, FamilyRecord] = field(default_factory=dict)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    scanned: bool = False
    finished: bool = False


def parse_react_action(text: str) -> tuple[str, str, dict]:
    """Return (thought, action, args). action is '' if unparseable."""
    thought = ""
    tm = re.search(r"Thought\s*:\s*(.*?)(?=\nAction\s*:|\Z)", text or "", re.S | re.I)
    if tm:
        thought = tm.group(1).strip()
    blob = (text or "").strip()
    if blob.startswith("```"):
        blob = blob.split("\n", 1)[-1]
        if blob.endswith("```"):
            blob = blob[: blob.rfind("```")]
        blob = blob.strip()
        if blob.lower().startswith("json"):
            blob = blob[4:].strip()
    if blob.startswith("{"):
        try:
            obj = json.loads(blob[blob.find("{") : blob.rfind("}") + 1])
            action = str(obj.get("action") or obj.get("tool") or "")
            args = obj.get("action_input") or obj.get("args") or obj.get("input") or {}
            if isinstance(args, str):
                args = _args_from_text(action, args)
            return thought, action, dict(args)
        except Exception:
            pass
    am = re.search(r"Action\s*:\s*([A-Za-z_][A-Za-z0-9_]*)", text or "", re.I)
    if not am:
        return thought, "", {}
    action = am.group(1)
    im = re.search(r"Action\s*Input\s*:\s*(.*)", text or "", re.S | re.I)
    raw = im.group(1).strip() if im else ""
    raw = raw.split("\nThought:")[0].split("\nAction:")[0].strip()
    return thought, action, _args_from_text(action, raw)


def _args_from_text(action: str, raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw or raw in {"{}", "null", "None"}:
        return {}
    if raw.startswith("{") or raw.startswith("["):
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    token = raw.strip().strip('"').strip("'")
    if action in {
        "recover_family",
        "instantiate_plan",
        "execute_plan",
        "verify_family",
        "realize_input",
    }:
        return {"family_id": token}
    if action == "record_verdict" and " " in token:
        fid, verd = token.split(None, 1)
        return {"family_id": fid, "verdict": verd}
    return {}


def _plan_public(plan: Plan) -> Dict[str, Any]:
    return {
        "via": plan.via,
        "setup": plan.setup,
        "holder": plan.holder.statements,
        "writer": plan.writer.statements,
        "observer": plan.observer.statements,
        "teardown": plan.teardown,
        "notes": plan.notes,
    }


def _relation_public(rel: ActuationRelation) -> Dict[str, Any]:
    return {
        "recoverable": rel.recoverable,
        "sql_template": rel.sql_template,
        "wait_for_lockers": rel.wait_for_lockers,
        "prevent_in_xact": rel.prevent_in_xact,
        "observer_sql": rel.observer_sql,
        "concurrent_required": rel.concurrent_required,
        "lock_object": rel.lock_object,
        "catalog": rel.catalog,
        "field": rel.field,
        "evidence": rel.evidence,
        "notes": rel.notes,
    }


class ToolBox:
    def __init__(self, cfg: AgentConfig, state: AgentState):
        self.cfg = cfg
        self.state = state

    def scan_leftovers(self) -> Dict[str, Any]:
        pg_src = self.cfg.pg_src
        roots = self.cfg.gcov_roots or default_gcov_roots(pg_src)
        gaps = scan_guard_gaps(pg_src, roots)
        buckets: Dict[str, list] = defaultdict(list)
        for row in gaps:
            try:
                target = extract_from_gcov_line(pg_src, row)
            except Exception:
                continue
            sp = split_constraint(target)
            key = family_key(target, sp)
            buckets[key].append((target, sp, row.guard_hits))
        self.state.families.clear()
        for key, items in sorted(buckets.items(), key=lambda kv: -max(x[2] for x in kv[1])):
            items.sort(key=lambda x: -x[2])
            target, sp, hits = items[0]
            self.state.families[key] = FamilyRecord(
                family=key,
                kind=sp.kind,
                members=len(items),
                guard_hits=hits,
                example=f"{target.rel_path}:{target.line}",
                function=target.function,
                reasons=list(sp.reasons),
                target=target,
            )
        self.state.scanned = True
        return {
            "family_count": len(self.state.families),
            "families": [
                {
                    "family": f.family,
                    "kind": f.kind,
                    "members": f.members,
                    "guard_hits": f.guard_hits,
                    "example": f.example,
                    "function": f.function,
                    "verdict": f.verdict,
                }
                for f in self.state.families.values()
            ],
        }

    def load_target(self, spec: str) -> Dict[str, Any]:
        target = extract(self.cfg.pg_src, spec)
        sp = split_constraint(target)
        key = family_key(target, sp)
        self.state.families[key] = FamilyRecord(
            family=key,
            kind=sp.kind,
            members=1,
            guard_hits=0,
            example=f"{target.rel_path}:{target.line}",
            function=target.function,
            reasons=list(sp.reasons),
            target=target,
        )
        self.state.scanned = True
        return {
            "family": key,
            "kind": sp.kind,
            "example": f"{target.rel_path}:{target.line}",
            "reasons": sp.reasons,
        }

    def recover_family(self, family_id: str) -> Dict[str, Any]:
        rec = self._fam(family_id)
        if rec.kind != "PC_V":
            return {
                "error": f"{family_id} is {rec.kind}, not PC_V; record_verdict instead of recover",
                "kind": rec.kind,
            }
        rel = recover(self.cfg.pg_src, rec.target)
        rec.relation = rel
        out = _relation_public(rel)
        out["family_id"] = family_id
        return out

    def realize_input(self, family_id: str) -> Dict[str, Any]:
        rec = self._fam(family_id)
        if rec.kind == "PC_V" and rec.target.catalog:
            return {
                "error": (
                    "conjunct not in alphabet A; use recover_family. "
                    "Do not SMT-symbolize catalog memory."
                ),
                "kind": rec.kind,
            }
        ir = realize(self.cfg.pg_src, rec.target)
        rec.realization = ir
        rec.attempts += 1
        out = ir.public()
        out["family_id"] = family_id
        if ir.status == "SAT" and ir.sql:
            rec.plan = plan_from_realization(ir)
            out["plan"] = _plan_public(rec.plan)
        return out

    def instantiate_plan(self, family_id: str, feedback: str = "") -> Dict[str, Any]:
        rec = self._fam(family_id)
        if rec.relation is None:
            return {"error": "recover_family first; instantiator cannot invent SQL from leftover C"}
        if not rec.relation.sql_template:
            return {"error": "no sql_template recovered; refusing to guess an operation"}
        if rec.attempts >= self.cfg.max_retries:
            return {"error": f"max_retries={self.cfg.max_retries}; record_verdict FAILED"}
        rec.attempts += 1
        fb = feedback or (rec.errors[-1] if rec.errors else "")
        prefix = f"cr_{abs(hash(family_id)) % 100000}_{rec.attempts}"
        try:
            plan = instantiate(
                rec.relation,
                prefix=prefix,
                use_llm=self.cfg.use_llm_instantiate,
                completer=self.cfg.instantiate_completer,
                feedback=fb,
            )
        except Exception as exc:
            rec.errors.append(str(exc))
            return {"error": str(exc), "attempt": rec.attempts}
        rec.plan = plan
        return {"family_id": family_id, "attempt": rec.attempts, "plan": _plan_public(plan)}

    def execute_plan(self, family_id: str) -> Dict[str, Any]:
        rec = self._fam(family_id)
        if rec.plan is None:
            return {"error": "instantiate_plan first"}
        if not self.cfg.do_execute and self.cfg.execute_fn is None:
            return {"error": "execute disabled; record_verdict RECOVERED or pass --execute"}
        if rec.before is None and not self.cfg.dry_run_execute:
            try:
                from .verify import snapshot_then

                rec.before = snapshot_then(rec.target)
            except Exception:
                rec.before = {}
        try:
            result = self._run_execute(rec.plan)
        except Exception as exc:
            rec.errors.append(str(exc))
            rec.last_execute = {"ok": False, "error": str(exc)}
            return rec.last_execute
        rec.last_execute = {
            "ok": bool(result.ok),
            "flag_seen_true": bool(getattr(result, "flag_seen_true", False)),
            "log": list(getattr(result, "log", []) or []),
        }
        if not rec.last_execute["ok"]:
            rec.errors.append("execute failed: " + " | ".join(rec.last_execute["log"][-4:]))
        return rec.last_execute

    def verify_family(self, family_id: str) -> Dict[str, Any]:
        rec = self._fam(family_id)
        if rec.last_execute is None:
            return {"error": "execute_plan first"}
        if self.cfg.verify_fn is not None:
            ver = self.cfg.verify_fn(rec.target)
            rec.last_verify = {
                "ok": bool(getattr(ver, "ok", ver)),
                "then_gained": list(getattr(ver, "then_gained", []) or []),
            }
            return rec.last_verify
        if self.cfg.dry_run_execute:
            rec.last_verify = {"ok": True, "then_gained": [rec.target.line + 1], "dry_run": True}
            return rec.last_verify
        from .verify import compare, snapshot_then

        after = snapshot_then(rec.target)
        ver = compare(rec.before or {}, after, rec.target.line)
        rec.last_verify = {"ok": ver.ok, "then_gained": ver.then_gained}
        if not ver.ok:
            rec.errors.append("verify: no then-block gain")
        return rec.last_verify

    def record_verdict(self, family_id: str, verdict: str) -> Dict[str, Any]:
        rec = self._fam(family_id)
        rec.verdict = str(verdict)
        return {"family_id": family_id, "verdict": rec.verdict}

    def finish(self) -> Dict[str, Any]:
        self.state.finished = True
        missing = [f.family for f in self.state.families.values() if not f.verdict]
        return {
            "ok": not missing,
            "missing_verdicts": missing,
            "verdicts": {f.family: f.verdict for f in self.state.families.values()},
        }

    def dispatch(self, name: str, args: Optional[dict] = None) -> Dict[str, Any]:
        aliases = {
            "scan": "scan_leftovers",
            "recover": "recover_family",
            "instantiate": "instantiate_plan",
            "concolic": "realize_input",
            "realize": "realize_input",
        }
        name = aliases.get(name, name)
        fn = getattr(self, name, None)
        if not callable(fn) or name.startswith("_"):
            return {"error": f"unknown tool {name!r}"}
        kwargs = dict(args or {})
        try:
            return fn(**kwargs)
        except TypeError as exc:
            return {"error": str(exc)}
        except KeyError as exc:
            return {"error": str(exc)}

    def _fam(self, family_id: str) -> FamilyRecord:
        if family_id not in self.state.families:
            raise KeyError(f"unknown family {family_id!r}; scan_leftovers first")
        return self.state.families[family_id]

    def _run_execute(self, plan: Plan):
        if self.cfg.execute_fn is not None:
            return self.cfg.execute_fn(plan)
        if self.cfg.dry_run_execute:
            from .execute import ExecResult

            return ExecResult(True, True, "t", "", "", ["dry_run"])
        from .execute import execute

        return execute(plan)


class ConstraintAgent:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self.state = AgentState()
        self.tools = ToolBox(cfg, self.state)

    def report(self) -> Dict[str, Any]:
        families = []
        for rec in self.state.families.values():
            entry: Dict[str, Any] = {
                "family": rec.family,
                "kind": rec.kind,
                "members": rec.members,
                "guard_hits": rec.guard_hits,
                "example": rec.example,
                "function": rec.function,
                "reasons": rec.reasons,
                "verdict": rec.verdict,
                "attempts": rec.attempts,
            }
            if rec.relation is not None:
                entry["sql_template"] = rec.relation.sql_template
                entry["wait_for_lockers"] = rec.relation.wait_for_lockers
                entry["evidence"] = rec.relation.evidence
                entry["notes"] = rec.relation.notes
            if rec.realization is not None:
                entry["realization"] = rec.realization.public()
                entry["sat_on_slice"] = rec.realization.sat_on_slice
                entry["sql"] = rec.realization.sql
            if rec.plan is not None:
                entry["plan_via"] = rec.plan.via
                entry["writer"] = rec.plan.writer.statements
                entry["instantiate_notes"] = rec.plan.notes
            if rec.last_execute is not None:
                entry["execute"] = rec.last_execute
            if rec.last_verify is not None:
                entry["verify"] = rec.last_verify
            if rec.errors:
                entry["errors"] = rec.errors
            families.append(entry)
        return {
            "mode": "agent",
            "pg_src": str(self.cfg.pg_src),
            "family_count": len(families),
            "pc_v_recovered": sum(
                1 for f in families if f.get("verdict") in {"RECOVERED", "REALIZABLE"} and f.get("kind") == "PC_V"
            ),
            "pc_a_realized": sum(
                1 for f in families if f.get("verdict") in {"INPUT_REALIZED", "REALIZABLE"} and f.get("kind") == "PC_A"
            ),
            "families": families,
            "trace": self.state.trace,
            "steps": len(self.state.trace),
            "finished": self.state.finished,
        }

    def note(self, thought: str, action: str, args: dict, observation: dict) -> None:
        self.state.trace.append(
            {
                "thought": thought,
                "action": action,
                "args": args,
                "observation": observation,
            }
        )


def _kickoff(cfg: AgentConfig) -> str:
    exec_s = "enabled" if cfg.do_execute or cfg.execute_fn is not None else "disabled"
    extra = f"Single leftover already specified: {cfg.target}\n" if cfg.target else ""
    return (
        f"Run constraint realization over leftover families.\n"
        f"pg_src={cfg.pg_src}\n"
        f"execute={exec_s}\n"
        f"{extra}"
        "Scan, recover each PC_V family, concolic-realize each PC_A family, "
        f"{'execute and verify, ' if exec_s == 'enabled' else ''}"
        "record a verdict, then finish."
    )


def _call_supervisor(cfg: AgentConfig, messages: List[dict], system: str) -> str:
    if cfg.supervisor_complete is not None:
        try:
            return cfg.supervisor_complete(messages=messages, system=system)
        except TypeError:
            return cfg.supervisor_complete(json.dumps(messages, default=str))
    return complete_chat(system=system, messages=messages, temperature=0.1)


def _drive_pc_a(agent: ConstraintAgent, family_id: str) -> None:
    rec = agent.state.families[family_id]
    obs = agent.tools.realize_input(family_id)
    agent.note("leftover-branch concolic over A", "realize_input", {"family_id": family_id}, obs)
    if obs.get("error"):
        v = agent.tools.record_verdict(family_id, "UNKNOWN")
        agent.note("realize_input failed", "record_verdict", {"family_id": family_id}, v)
        return
    if obs.get("status") == "UNREALIZABLE" or (
        obs.get("sat_on_slice") and not obs.get("realizable_under_callers")
    ):
        v = agent.tools.record_verdict(family_id, "UNREALIZABLE UNDER A,E,B")
        agent.note("slice SAT is not coverage", "record_verdict", {"family_id": family_id}, v)
        return
    if obs.get("status") != "SAT" or rec.plan is None:
        v = agent.tools.record_verdict(family_id, "UNKNOWN")
        agent.note("no preimage in A", "record_verdict", {"family_id": family_id}, v)
        return
    if not agent.cfg.do_execute and agent.cfg.execute_fn is None:
        v = agent.tools.record_verdict(family_id, "INPUT_REALIZED")
        agent.note("execute disabled", "record_verdict", {"family_id": family_id}, v)
        return
    last_err = ""
    for _ in range(agent.cfg.max_retries):
        ex = agent.tools.execute_plan(family_id)
        agent.note("run input SQL", "execute_plan", {"family_id": family_id}, ex)
        if ex.get("error") or not ex.get("ok"):
            last_err = str(ex.get("error") or "execute failed")
            rec.errors.append(last_err)
            continue
        ver = agent.tools.verify_family(family_id)
        agent.note("gcov then-delta", "verify_family", {"family_id": family_id}, ver)
        if ver.get("ok") or ex.get("flag_seen_true"):
            v = agent.tools.record_verdict(family_id, "REALIZABLE")
            agent.note("covered", "record_verdict", {"family_id": family_id}, v)
            return
        last_err = "verify: no then-block gain"
    v = agent.tools.record_verdict(family_id, "FAILED")
    agent.note("retries exhausted", "record_verdict", {"family_id": family_id}, v)


def drive_family(agent: ConstraintAgent, family_id: str) -> None:
    """Deterministic tool policy for one family (no supervisor LLM)."""
    rec = agent.state.families[family_id]
    if rec.verdict:
        return
    if rec.kind in {"PC_A", "UNREALIZABLE"}:
        _drive_pc_a(agent, family_id)
        return
    if rec.kind != "PC_V":
        obs = agent.tools.record_verdict(family_id, _KIND_VERDICT.get(rec.kind, rec.kind))
        agent.note("non-PC_V family", "record_verdict", {"family_id": family_id}, obs)
        return
    obs = agent.tools.recover_family(family_id)
    agent.note("recover actuation relation", "recover_family", {"family_id": family_id}, obs)
    if obs.get("error") or not obs.get("recoverable"):
        v = agent.tools.record_verdict(family_id, "UNKNOWN")
        agent.note("unrecoverable", "record_verdict", {"family_id": family_id}, v)
        return
    last_err = ""
    for _ in range(agent.cfg.max_retries):
        inst = agent.tools.instantiate_plan(family_id, feedback=last_err)
        agent.note("instantiate from relation", "instantiate_plan", {"family_id": family_id}, inst)
        if inst.get("error"):
            last_err = str(inst["error"])
            continue
        if not agent.cfg.do_execute and agent.cfg.execute_fn is None:
            v = agent.tools.record_verdict(family_id, "RECOVERED")
            agent.note("execute disabled", "record_verdict", {"family_id": family_id}, v)
            return
        ex = agent.tools.execute_plan(family_id)
        agent.note("run sessions", "execute_plan", {"family_id": family_id}, ex)
        if ex.get("error") or not ex.get("ok"):
            last_err = str(ex.get("error") or "execute failed")
            continue
        ver = agent.tools.verify_family(family_id)
        agent.note("gcov then-delta", "verify_family", {"family_id": family_id}, ver)
        if ver.get("ok") or ex.get("flag_seen_true"):
            v = agent.tools.record_verdict(family_id, "REALIZABLE")
            agent.note("covered", "record_verdict", {"family_id": family_id}, v)
            return
        last_err = "verify: no then-block gain"
    v = agent.tools.record_verdict(family_id, "FAILED")
    agent.note("retries exhausted", "record_verdict", {"family_id": family_id}, v)


def run_scripted(agent: ConstraintAgent, only_unresolved: bool = False) -> Dict[str, Any]:
    if not agent.state.scanned:
        if agent.cfg.target:
            obs = agent.tools.load_target(agent.cfg.target)
            agent.note("load single leftover", "load_target", {"spec": agent.cfg.target}, obs)
        else:
            obs = agent.tools.scan_leftovers()
            agent.note("scan leftover families", "scan_leftovers", {}, obs)
    for family_id in list(agent.state.families):
        if only_unresolved and agent.state.families[family_id].verdict:
            continue
        drive_family(agent, family_id)
    fin = agent.tools.finish()
    agent.note("all families handled", "finish", {}, fin)
    return agent.report()


def run_react(agent: ConstraintAgent) -> Dict[str, Any]:
    if agent.cfg.target and not agent.state.scanned:
        obs = agent.tools.load_target(agent.cfg.target)
        agent.note("load single leftover", "load_target", {"spec": agent.cfg.target}, obs)
    messages: List[dict] = [{"role": "user", "content": _kickoff(agent.cfg)}]
    for _ in range(agent.cfg.max_steps):
        if agent.state.finished:
            break
        raw = _call_supervisor(agent.cfg, messages, SUPERVISOR_SYSTEM)
        thought, action, args = parse_react_action(raw)
        if not action:
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": "Unparseable. Reply with Action and Action Input.",
                }
            )
            agent.note(thought or "unparseable", "", {}, {"error": "unparseable", "raw": raw[:500]})
            continue
        obs = agent.tools.dispatch(action, args)
        agent.note(thought, action, args, obs)
        if action == "finish":
            break
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": "Observation:\n"
                + json.dumps(obs, default=str)[:6000]
                + "\nNext Action.",
            }
        )
    if not agent.state.finished or any(not f.verdict for f in agent.state.families.values()):
        run_scripted(agent, only_unresolved=True)
    return agent.report()


def run_agent(cfg: AgentConfig) -> Dict[str, Any]:
    """ReAct supervisor if an LLM (or injectable completer) is available; else scripted tools."""
    agent = ConstraintAgent(cfg)
    if cfg.supervisor_complete is not None:
        return run_react(agent)
    if not cfg.use_llm_supervisor:
        return run_scripted(agent)
    try:
        return run_react(agent)
    except LLMError as exc:
        agent.note("supervisor LLM unavailable", "fallback_scripted", {}, {"error": str(exc)})
        return run_scripted(agent, only_unresolved=True)
