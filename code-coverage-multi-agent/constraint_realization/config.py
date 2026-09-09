from __future__ import annotations

import os
from pathlib import Path

_PKG = Path(__file__).resolve().parent
AGENT_ROOT = Path(os.environ.get("COVERAGE_AGENT_ROOT") or _PKG.parent)

PG_SRC = Path(
    os.environ.get("POSTGRESQL_SRC_DIR")
    or os.environ.get("PG_SRC")
    or "/root/postgresql-17.6"
)
SQL_LOG = Path(os.environ.get("SQL_LOG_DIR") or (AGENT_ROOT / "sql_log"))

PGHOST = os.environ.get("PGHOST") or "127.0.0.1"
PGPORT = int(os.environ.get("PGPORT") or 5433)
PGDATABASE = os.environ.get("PGDATABASE") or "postgres"
PGUSER = os.environ.get("PGUSER") or "postgres"

_PSQL = [
    os.environ.get("PSQL_BIN"),
    "/root/postgresql-17.6/tmp_install/usr/local/pgsql-17.6/bin/psql",
    "/usr/local/pgsql-17.6/bin/psql",
]


def psql_bin() -> str:
    for cand in _PSQL:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    raise FileNotFoundError("psql not found; set PSQL_BIN")
