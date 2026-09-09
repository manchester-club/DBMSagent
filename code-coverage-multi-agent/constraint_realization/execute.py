from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import List

from . import config
from .instantiate import Plan


@dataclass
class ExecResult:
    ok: bool
    flag_seen_true: bool
    observer_stdout: str
    holder_out: str
    writer_out: str
    log: List[str] = field(default_factory=list)


def _cmd() -> List[str]:
    return [
        config.psql_bin(),
        "-h",
        config.PGHOST,
        "-p",
        str(config.PGPORT),
        "-U",
        config.PGUSER,
        "-d",
        config.PGDATABASE,
        "-v",
        "ON_ERROR_STOP=1",
        "-P",
        "pager=off",
    ]


def run_sql(sql: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(_cmd() + ["-c", sql], capture_output=True, text=True, timeout=timeout)


def _start(sql: str) -> subprocess.Popen:
    return subprocess.Popen(
        _cmd() + ["-c", sql],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _probe_sql(plan: Plan) -> str:
    if plan.catalog and plan.catalog_field:
        return f"SELECT {plan.catalog_field} FROM {plan.catalog} WHERE {plan.catalog_field} IS TRUE LIMIT 5;"
    return ";\n".join(plan.observer.statements) + ";"


def _flag_true(text: str) -> bool:
    for ln in text.splitlines():
        s = ln.strip()
        if s in {"t", "true"}:
            return True
        if s.endswith("| t") or s.endswith(" t"):
            return True
    return False


def execute(plan: Plan) -> ExecResult:
    log: List[str] = []
    r = run_sql(";\n".join(plan.setup) + ";")
    if r.returncode != 0:
        return ExecResult(False, False, "", "", r.stderr or r.stdout, [r.stdout, r.stderr])
    log.append("setup ok")

    hold = plan.holder.role != "noop"
    writer_sql = ";\n".join(plan.writer.statements) + ";"
    flag_true = False
    observer_out = ""
    h_out = ""
    w_out = ""
    s1 = None

    if hold:
        s1 = _start(";\n".join(plan.holder.statements) + ";")
        time.sleep(1.2)
        if s1.poll() is not None:
            out = s1.stdout.read() if s1.stdout else ""
            run_sql(";\n".join(plan.teardown) + ";")
            return ExecResult(False, False, "", out, "", ["holder died early", out])

    s2 = _start(writer_sql)
    if hold:
        probe = _probe_sql(plan)
        for i in range(48):
            time.sleep(0.25)
            st = run_sql(probe)
            text = (st.stdout or "") + (st.stderr or "")
            if st.returncode == 0 and _flag_true(text):
                flag_true = True
                log.append(f"catalog flag true after {0.25 * (i + 1):.2f}s")
                obs = run_sql(";\n".join(plan.observer.statements) + ";")
                observer_out = (obs.stdout or "") + (obs.stderr or "")
                break
            if s2.poll() is not None:
                log.append("writer finished before flag observed")
                break
        h_out, _ = s1.communicate(timeout=40) if s1 else ("", None)
        w_out, _ = s2.communicate(timeout=40)
    else:
        w_out, _ = s2.communicate(timeout=40)
        obs = run_sql(";\n".join(plan.observer.statements) + ";")
        observer_out = (obs.stdout or "") + (obs.stderr or "")
        flag_true = s2.returncode == 0
        h_out = ""

    log.append(f"writer rc={s2.returncode}")
    run_sql(";\n".join(plan.teardown) + ";")
    ok = s2.returncode == 0 and (flag_true if hold else True)
    return ExecResult(ok, flag_true, observer_out, h_out, w_out, log)
