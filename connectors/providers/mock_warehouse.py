#!/usr/bin/env python3
"""
Mock warehouse provider (script contract: request JSON on stdin, output JSON on stdout).

Loads fixtures/mock_warehouse/*.csv into in-memory sqlite, then switches the
connection to read-only (PRAGMA query_only = ON) and installs a sqlite authorizer
before running any query. The authorizer is the enforcing layer; the text guard runs before it.
Authorizer policy (deny by default):
  - allowed actions: SELECT, READ, FUNCTION, RECURSIVE; every other action (insert, update,
    delete, create, drop, alter, attach, pragma, transaction, ...) is denied;
  - READ of a column of a table in data.pii_tables is denied. sqlite reports an empty column
    name for COUNT(*) (checked on sqlite 3.51), so a plain row count of a PII table still works;
  - READ of sqlite_master / sqlite_schema / sqlite_temp_master (any sqlite_* table) is denied;
  - FUNCTION is an ALLOWLIST (ALLOWED_FUNCTIONS): aggregates and common safe scalar functions.
    load_extension, readfile, writefile, edit, fts3_tokenizer and table-valued pragma_* are
    not on it, so they are denied.
A denied statement is answered with "query not authorized: reads a PII column or is not read-only".
As a second belt, a result with a non-numeric string cell is refused when the query names a PII table.

Request: {"question", "query_id", "params"} per schemas/provider-io.schema.json.
  - Library query: query_id is looked up in connectors/queries/index.yaml
    (directory overridable with env PM_QUERIES_DIR); params are bound by name.
  - Ad-hoc query (issued by scripts/enrich.py --sql): params carries the SQL text
    under the key "__sql"; keys starting with "__" are not bound.
Every query goes through scripts/sql_guard.py first, using pii_tables and
data.max_rows_returned from the config path in env PM_CONFIG (default pm.config.yaml).
A query that returns no rows, or a NULL first value, is answered with the error
"query returned no rows for these params" (the filter matched nothing).
A guard failure or bad request is answered with {"ok": false, "error": ...} and
exit 0: a refusal is data, not a crash.
"""

import csv
import os
import sys
import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from sql_guard import check_sql, load_guard_settings  # noqa: E402

try:
    import yaml
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(1)

WAREHOUSE_DIR = REPO_ROOT / "fixtures" / "mock_warehouse"

NOT_AUTHORIZED = "query not authorized: reads a PII column or is not read-only"
ALLOWED_ACTIONS = frozenset({
    sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE,
})
SCHEMA_TABLES = frozenset({"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema"})
ALLOWED_FUNCTIONS = frozenset({
    "count", "sum", "avg", "min", "max", "total", "group_concat",
    "round", "abs", "coalesce", "ifnull", "nullif", "iif",
    "substr", "substring", "lower", "upper", "length", "trim", "ltrim", "rtrim", "replace", "instr",
    "like", "glob", "typeof",
    "strftime", "date", "time", "datetime", "julianday",
})


def make_authorizer(pii_tables):
    """Build the sqlite authorizer callback (see module docstring). It never raises."""
    pii = {t.lower() for t in pii_tables}
    denied = []  # filled when something is denied; sqlite words the error differently per case

    def decide(action, arg1, arg2):
        if action not in ALLOWED_ACTIONS:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ:
            table = (arg1 or "").lower()
            if table in SCHEMA_TABLES or table.startswith("sqlite_"):
                return sqlite3.SQLITE_DENY
            if table in pii and arg2:
                return sqlite3.SQLITE_DENY
        elif action == sqlite3.SQLITE_FUNCTION:
            if (arg2 or "").lower() not in ALLOWED_FUNCTIONS:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def authorizer(action, arg1, arg2, db_name, trigger):
        verdict = decide(action, arg1, arg2)
        if verdict != sqlite3.SQLITE_OK:
            denied.append(action)
        return verdict

    authorizer.denied = denied
    return authorizer


def _convert(value: str):
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value


def _is_numeric_text(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def load_warehouse() -> sqlite3.Connection:
    """Load every CSV into an in-memory database, then make it read-only."""
    conn = sqlite3.connect(":memory:")
    for csv_path in sorted(WAREHOUSE_DIR.glob("*.csv")):
        with open(csv_path, newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        cols = ", ".join(f'"{c}"' for c in header)
        conn.execute(f'CREATE TABLE "{csv_path.stem}" ({cols})')
        marks = ", ".join("?" for _ in header)
        conn.executemany(
            f'INSERT INTO "{csv_path.stem}" VALUES ({marks})',
            [[_convert(v) for v in row] for row in rows],
        )
    conn.commit()
    conn.execute("PRAGMA query_only = ON")
    return conn


def resolve_sql(request: dict) -> str:
    params = request["params"]
    if "__sql" in params:
        return str(params["__sql"])
    queries_dir = Path(os.environ.get("PM_QUERIES_DIR") or REPO_ROOT / "connectors" / "queries")
    with open(queries_dir / "index.yaml", "r") as f:
        index = yaml.safe_load(f) or {}
    for query in index.get("queries", []):
        if query.get("id") == request["query_id"]:
            with open(queries_dir / query["file"], "r") as f:
                return f.read()
    raise ValueError(f"unknown query_id '{request['query_id']}'")


def build_output(request: dict) -> dict:
    run_at = datetime.now(timezone.utc).isoformat()
    out = {"ok": False, "rows": [], "n": 0, "run_at": run_at, "query_hash": "", "caveats": []}
    try:
        sql = resolve_sql(request)
        out["query_hash"] = hashlib.sha256(sql.encode("utf-8")).hexdigest()

        config_path = os.environ.get("PM_CONFIG") or "pm.config.yaml"
        if not Path(config_path).is_absolute():
            config_path = str(REPO_ROOT / config_path)
        pii_tables, max_rows, aggregate_only = load_guard_settings(config_path)

        errors = check_sql(sql, pii_tables, max_rows, aggregate_only)
        if errors:
            out["error"] = "query refused by guard: " + "; ".join(errors)
            return out

        bind = {k: v for k, v in request["params"].items() if not k.startswith("__")}
        conn = load_warehouse()
        authorizer = make_authorizer(pii_tables)
        conn.set_authorizer(authorizer)
        try:
            cursor = conn.execute(sql, bind)
            if cursor.description is None:
                out["error"] = NOT_AUTHORIZED
                return out
            names = [d[0] for d in cursor.description]
            rows = [dict(zip(names, row)) for row in cursor.fetchall()]
        except sqlite3.DatabaseError as e:
            message = str(e).lower()
            if getattr(authorizer, "denied", None) or "not authorized" in message or "prohibited" in message:
                out["error"] = NOT_AUTHORIZED
                return out
            raise
        finally:
            conn.close()
        lowered = sql.lower()
        if any(t.lower() in lowered for t in pii_tables) and any(
            isinstance(v, str) and not _is_numeric_text(v) for row in rows for v in row.values()
        ):
            out["error"] = NOT_AUTHORIZED
            return out
    except (ValueError, OSError, KeyError, yaml.YAMLError) as e:
        out["error"] = str(e) or e.__class__.__name__
        return out
    except (sqlite3.Error, sqlite3.Warning) as e:
        out["error"] = f"query failed: {e}"
        return out

    if not rows or next(iter(rows[0].values()), None) is None:
        out["error"] = "query returned no rows for these params"
        return out

    out.update({"ok": True, "rows": rows, "n": len(rows)})
    out["caveats"] = ["synthetic mock warehouse data"]
    return out


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("params"), dict) \
                or not isinstance(request.get("query_id"), str):
            raise ValueError("request must have query_id and params")
    except (json.JSONDecodeError, ValueError) as e:
        out = {"ok": False, "error": f"invalid request: {e}", "rows": [], "n": 0,
               "run_at": datetime.now(timezone.utc).isoformat(), "query_hash": "", "caveats": []}
        print(json.dumps(out))
        return
    print(json.dumps(build_output(request)))


if __name__ == "__main__":
    main()
