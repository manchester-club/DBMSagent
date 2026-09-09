from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

_CTRL = {"if", "while", "for", "switch", "return", "sizeof", "foreach", "else"}
_FUNC_BOL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_FUNC_TYPED = re.compile(
    r"^(?:static|inline|extern)\s+(?:[\w\*]+\s+){0,4}([A-Za-z_][A-Za-z0-9_]*)\s*\("
)


@dataclass
class FunctionSpan:
    name: str
    start: int
    end: int
    path: Path


def _drop_block(src: str, in_block: bool) -> tuple[str, bool]:
    out: List[str] = []
    i = 0
    n = len(src)
    while i < n:
        if in_block:
            j = src.find("*/", i)
            if j < 0:
                return "".join(out), True
            i = j + 2
            in_block = False
            continue
        if src[i] == "/" and i + 1 < n and src[i + 1] == "*":
            in_block = True
            i += 2
            continue
        out.append(src[i])
        i += 1
    return "".join(out), in_block


def _strip_line_comments(src: str) -> str:
    out: List[str] = []
    i = 0
    n = len(src)
    in_s = in_d = False
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_s:
            if ch == "\\":
                i += 2
                continue
            if ch == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_d = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            break
        if ch == "'":
            in_s = True
            i += 1
            continue
        if ch == '"':
            in_d = True
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _brace_delta(src: str) -> int:
    delta = 0
    i = 0
    n = len(src)
    in_s = in_d = False
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_s:
            if ch == "\\":
                i += 2
                continue
            if ch == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_d = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            break
        if ch == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            if j < 0:
                break
            i = j + 2
            continue
        if ch == "'":
            in_s = True
            i += 1
            continue
        if ch == '"':
            in_d = True
            i += 1
            continue
        if ch == "{":
            delta += 1
        elif ch == "}":
            delta -= 1
        i += 1
    return delta


@lru_cache(maxsize=128)
def index_functions(path: Path) -> List[FunctionSpan]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    spans: List[FunctionSpan] = []
    i = 0
    n = len(lines)
    in_block = False
    while i < n:
        raw, in_block = _drop_block(lines[i], in_block)
        st = _strip_line_comments(raw).strip()
        if in_block or not st or st.startswith("#") or st.startswith("*") or st.endswith(";"):
            i += 1
            continue
        m = _FUNC_BOL.match(st) or _FUNC_TYPED.match(st)
        if not m:
            i += 1
            continue
        name = m.group(1)
        if name in _CTRL:
            i += 1
            continue
        buf = [st]
        j = i
        found_brace = False
        while j < min(n, i + 40):
            snippet = "\n".join(buf)
            if "{" in snippet:
                semi = snippet.find(";")
                brace = snippet.find("{")
                if semi >= 0 and semi < brace:
                    break
                found_brace = True
                break
            if ";" in snippet:
                break
            j += 1
            if j < n:
                nxt, _ = _drop_block(lines[j], False)
                buf.append(_strip_line_comments(nxt).strip())
        if not found_brace:
            i += 1
            continue
        depth = 0
        started = False
        end = j
        for k in range(i, n):
            delta = _brace_delta(lines[k])
            if not started:
                if delta > 0:
                    started = True
                    depth += delta
                continue
            depth += delta
            if depth <= 0:
                end = k
                break
        spans.append(FunctionSpan(name=name, start=i + 1, end=end + 1, path=path))
        i = end + 1
    return spans


def enclosing_function(path: Path, line: int) -> Optional[FunctionSpan]:
    for sp in index_functions(path):
        if sp.start <= line <= sp.end:
            return sp
    return None


def snippet(path: Path, start: int, end: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lo = max(1, start) - 1
    hi = min(len(lines), end)
    return "\n".join(lines[lo:hi])


def iter_backend_files(root: Path, suffix: str) -> Iterator[Path]:
    backend = root / "src" / "backend"
    if not backend.is_dir():
        backend = root
    skip = {"tmp_install", ".adt_cov_pgdata", "test", "regress"}
    for p in backend.rglob(f"*{suffix}"):
        if any(part in skip for part in p.parts):
            continue
        yield p


def grep_lines(root: Path, pattern: str, suffix: str = ".c") -> List[Tuple[Path, int, str]]:
    rx = re.compile(pattern)
    out: List[Tuple[Path, int, str]] = []
    files: Iterable[Path] = iter_backend_files(root, suffix)
    if suffix == ".y":
        files = (root / "src" / "backend" / "parser").rglob("*.y") if (root / "src").exists() else root.rglob("*.y")
    elif suffix == ".h":
        inc = root / "src" / "include"
        files = inc.rglob("*.h") if inc.is_dir() else root.rglob("*.h")
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                out.append((path, i, line.rstrip()))
    return out
