from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .extract import Target
from .leftover import parse_gcov, then_uncovered

_GC = re.compile(r"^([^:]*):\s*(\d+):(.*)$")


def run_gcov(src: Path) -> None:
    gcda = src.parent / (src.stem + ".gcda")
    if not gcda.is_file():
        return
    subprocess.run(
        ["gcov", "-b", src.name],
        cwd=str(src.parent),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _hit(tok: str) -> int:
    if tok in {"#####", "=====", "-", ""}:
        return 0
    try:
        return int(tok.replace("*", ""))
    except ValueError:
        return 0


def snapshot_then(target: Target) -> Dict[int, str]:
    gcov = Path(str(target.abs_path) + ".gcov")
    run_gcov(target.abs_path)
    rows = parse_gcov(gcov)
    then_lines = [r.line for r in then_uncovered(rows, target.line)]
    # include already-covered then lines too
    depth = 0
    started = False
    watch = [target.line]
    for r in rows:
        if r.line < target.line:
            continue
        for ch in r.source:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
        if r.line == target.line:
            continue
        if started and depth <= 0:
            break
        if started and r.count not in {"-"}:
            watch.append(r.line)
    out: Dict[int, str] = {}
    for r in rows:
        if r.line in watch:
            out[r.line] = r.count
    return out


@dataclass
class Verify:
    before: Dict[int, str]
    after: Dict[int, str]
    then_gained: List[int]
    ok: bool


def compare(before: Dict[int, str], after: Dict[int, str], target_line: int) -> Verify:
    gained = []
    for ln, tok in after.items():
        if ln == target_line:
            continue
        if _hit(tok) > _hit(before.get(ln, "#####")):
            gained.append(ln)
    return Verify(before, after, gained, ok=bool(gained))
