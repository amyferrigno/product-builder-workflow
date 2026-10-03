#!/usr/bin/env python3
"""
Read-only SQL guard. Pure standard library so a hook can import it by path.

Usage: python scripts/sql_guard.py --sql "SELECT ..." [--config pm.config.yaml]
Exit 0 if the query is allowed, 1 with one error per line otherwise.

check_sql(sql, pii_tables, max_rows, aggregate_only=True) returns a list of
human-readable errors (empty list means the query is allowed).
"""

import re
import sys
import argparse
from pathlib import Path
from typing import List, Optional

FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "CREATE",
    "GRANT", "TRUNCATE", "REPLACE", "ATTACH", "PRAGMA",
]

AGGREGATE_RE = re.compile(r"\b(?:count|sum|avg|min|max)\s*\(|\bgroup\s+by\b", re.IGNORECASE)
COUNT_STAR_RE = re.compile(r"\bcount\s*\(\s*\*\s*\)", re.IGNORECASE)
STAR_SELECT_RE = re.compile(r"(?:\bselect|\bdistinct|,)\s*(?:\w+\s*\.\s*)?\*", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\s+(\d+)", re.IGNORECASE)


def mask_sql(sql: str) -> str:
    """
    Remove comments and mask string literals so keyword checks only see code.
    String literals become '' and quoted identifiers are unquoted.
    Raises ValueError on an unterminated string or comment.
    """
    out = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            if j == -1:
                raise ValueError("unterminated comment")
            i = j + 2
            out.append(" ")
        elif ch == "'":
            i += 1
            while True:
                if i >= n:
                    raise ValueError("unterminated string literal")
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append("''")
        elif ch in ('"', "`"):
            j = sql.find(ch, i + 1)
            if j == -1:
                raise ValueError("unterminated quoted identifier")
            out.append(re.sub(r"\W", "_", sql[i + 1:j]))
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def check_sql(
    sql: str,
    pii_tables: Optional[List[str]] = None,
    max_rows: int = 500,
    aggregate_only: bool = True,
) -> List[str]:
    """Return a list of errors for the query (empty means allowed)."""
    errors: List[str] = []
    pii_tables = pii_tables or []

    if not isinstance(sql, str) or not sql.strip():
        return ["query is empty"]

    try:
        masked = mask_sql(sql)
    except ValueError as e:
        return [f"query cannot be parsed: {e}"]

    body = masked.strip()
    while body.endswith(";"):
        body = body[:-1].rstrip()
    if not body:
        return ["query is empty"]

    if ";" in body:
        errors.append("multiple statements are not allowed")

    if not re.match(r"(?i)(select|with)\b", body):
        errors.append("only a single SELECT or WITH ... SELECT statement is allowed")

    for kw in FORBIDDEN_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", body, re.IGNORECASE):
            errors.append(f"forbidden keyword: {kw}")

    is_aggregate = bool(AGGREGATE_RE.search(body))
    if aggregate_only and not is_aggregate:
        errors.append("query must be aggregate (use COUNT/SUM/AVG/MIN/MAX or GROUP BY)")

    stars = bool(STAR_SELECT_RE.search(COUNT_STAR_RE.sub("count(1)", body)))
    for table in pii_tables:
        if re.search(r"\b" + re.escape(table) + r"\b", body, re.IGNORECASE):
            if stars:
                errors.append(f"SELECT * is not allowed on PII table '{table}'")
            if not is_aggregate:
                errors.append(f"PII table '{table}' can only be read through aggregate queries")

    for m in LIMIT_RE.finditer(body):
        if int(m.group(1)) > max_rows:
            errors.append(f"LIMIT {m.group(1)} exceeds max_rows {max_rows}")

    return errors


def load_guard_settings(config_path: str):
    """Read (pii_tables, max_rows, aggregate_only) from a pm config file."""
    import yaml
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise ValueError(f"Config not found: {config_path}")
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"Cannot read config {config_path}: {e}")
    try:
        data = config["data"]
        return (
            list(data["pii_tables"]),
            int(data["max_rows_returned"]),
            bool(data["aggregate_only"]),
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"Config {config_path} is missing the data section")


def main():
    parser = argparse.ArgumentParser(description="Check that a SQL query is read-only and aggregate.")
    parser.add_argument("--sql", required=True, help="SQL text to check")
    parser.add_argument("--config", default="pm.config.yaml", help="Path to pm config")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute() and not config_path.exists():
        config_path = Path(__file__).resolve().parent.parent / args.config
    try:
        pii_tables, max_rows, aggregate_only = load_guard_settings(str(config_path))
    except ValueError as e:
        print(str(e))
        sys.exit(1)

    errors = check_sql(args.sql, pii_tables, max_rows, aggregate_only)
    for error in errors:
        print(error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
