#!/usr/bin/env python3
"""
Read-only SQL guard. Pure standard library so a hook can import it by path.

This is a BEST-EFFORT EARLY WARNING, not the control. Text scanning cannot understand every
spelling of SQL. Enforcement is the provider: the sqlite authorizer in
connectors/providers/mock_warehouse.py, or, for real warehouses, a read-only database role
with PII-free views.

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

AGGREGATE_CALL_RE = re.compile(
    r"\b(count|sum|avg|min|max|total|group_concat|string_agg)\s*\(", re.IGNORECASE)
COUNT_STAR_RE = re.compile(r"\bcount\s*\(\s*\*\s*\)", re.IGNORECASE)
WINDOW_AFTER_RE = re.compile(r"\s*(?:filter\s*\([^)]*\)\s*)?over\b", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\b", re.IGNORECASE)
LIMIT_OK_RE = re.compile(
    r"\blimit\s+(\d+)(?:\s+offset\s+\d+)?\s*(?=$|[);]|\b(?:union|intersect|except)\b)",
    re.IGNORECASE,
)
PII_BANNED_RE = re.compile(
    r"\bgroup\s+by\b|\b(?:min|max|sum|avg|total|group_concat|string_agg)\s*\(", re.IGNORECASE)
COUNT_ITEM_RE = re.compile(
    r"count\s*\(.*\)(?:\s+(?:as\s+)?\w+)?", re.IGNORECASE | re.DOTALL)
LITERAL_ITEM_RE = re.compile(r"(?:\d+(?:\.\d+)?|'')(?:\s+(?:as\s+)?\w+)?", re.IGNORECASE)


class BracketIdentifierError(ValueError):
    """The query uses a [bracket] identifier."""


def mask_sql(sql: str) -> str:
    """
    Remove comments and mask string literals so keyword checks only see code.
    String literals become '' and quoted identifiers are unquoted.
    Raises ValueError on an unterminated string or comment, and BracketIdentifierError
    (a ValueError) on any [ or ] outside strings and comments.
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
        elif ch in ("'", '"', "`"):
            quote = ch
            i += 1
            text = []
            while True:
                if i >= n:
                    if quote == "'":
                        raise ValueError("unterminated string literal")
                    raise ValueError("unterminated quoted identifier")
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:
                        text.append(quote)
                        i += 2
                        continue
                    i += 1
                    break
                text.append(sql[i])
                i += 1
            if quote == "'":
                out.append("''")
            else:
                ident = re.sub(r"\W", "_", "".join(text))
                if ident[:1].isdigit():
                    ident = "_" + ident  # a quoted "5" is a name, not the number 5
                out.append(" " + ident + " ")  # spaces so it cannot fuse with neighbouring tokens
        elif ch in "[]":
            raise BracketIdentifierError("bracket identifiers are not allowed")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _matching_paren(text: str, open_index: int) -> int:
    """Index of the ) that closes the ( at open_index, or -1."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def aggregate_calls(body: str) -> List[str]:
    """Names (lower case) of aggregate function calls that are not window calls."""
    names = []
    for m in AGGREGATE_CALL_RE.finditer(body):
        close = _matching_paren(body, m.end() - 1)
        if close != -1 and WINDOW_AFTER_RE.match(body, close + 1):
            continue
        names.append(m.group(1).lower())
    return names


def select_lists(body: str) -> List[str]:
    """The text between each SELECT and its FROM (or the end of that select)."""
    lists = []
    for m in re.finditer(r"\bselect\b", body, re.IGNORECASE):
        depth = 0
        i = m.end()
        start = i
        while i < len(body):
            ch = body[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            elif ch == ";" and depth == 0:
                break
            elif depth == 0 and re.match(r"(?:from|union|intersect|except)\b", body[i:], re.IGNORECASE) \
                    and (i == 0 or not re.match(r"\w", body[i - 1])):
                break
            i += 1
        lists.append(body[start:i])
    return lists


def split_top_level(text: str) -> List[str]:
    """Split on commas that are not inside parentheses."""
    items, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return items


def pii_select_errors(body: str, table: str) -> List[str]:
    """Strict rule for a query that references a PII table."""
    errors = []
    banned = PII_BANNED_RE.search(body)
    if banned:
        found = re.sub(r"\s+", " ", banned.group(0)).strip(" (").upper()
        errors.append(f"PII table '{table}' allows only COUNT aggregates ({found} is not allowed)")
    for sel in select_lists(body):
        text = re.sub(r"^\s*(?:distinct|all)\b", "", sel, flags=re.IGNORECASE)
        for item in split_top_level(text):
            item = item.strip()
            if COUNT_ITEM_RE.fullmatch(item) and _single_call(item):
                continue
            if LITERAL_ITEM_RE.fullmatch(item):
                continue
            errors.append(
                f"PII table '{table}': every selected column must be a COUNT(...) expression or a literal")
            return errors
    return errors


def _single_call(item: str) -> bool:
    """True if item is one count(...) call (optionally aliased), not count(..) + more."""
    open_index = item.index("(")
    close = _matching_paren(item, open_index)
    if close == -1:
        return False
    return re.fullmatch(r"\s*(?:(?:as\s+)?\w+)?\s*", item[close + 1:], re.IGNORECASE) is not None \
        and not re.match(r"\s*over\b", item[close + 1:], re.IGNORECASE)


def check_sql(
    sql: str,
    pii_tables: Optional[List[str]] = None,
    max_rows: int = 500,
    aggregate_only: bool = True,
) -> List[str]:
    """
    Return a list of errors for the query (empty means allowed).

    Rules: a single SELECT / WITH ... SELECT; no mutating keywords; no [bracket] identifiers;
    LIMIT only as `LIMIT <integer>` or `LIMIT <integer> OFFSET <integer>` with the integer <= max_rows.
    Under aggregate_only the query needs at least one aggregate function call (GROUP BY alone
    does not count), window functions (OVER) are rejected, and group_concat / string_agg are
    rejected because they return row-level text.
    PII tables: if a PII table is referenced anywhere (FROM, JOIN, subquery, CTE) the statement
    must not contain GROUP BY, MIN, MAX, SUM, AVG, group_concat or string_agg, any `*` other
    than inside COUNT(*) is treated as SELECT *, and every select-list item must be a COUNT(...)
    expression or a literal. Reviewed library queries that need to group by a PII-joined table
    must avoid the PII table.
    """
    errors: List[str] = []
    pii_tables = pii_tables or []

    if not isinstance(sql, str) or not sql.strip():
        return ["query is empty"]

    try:
        masked = mask_sql(sql)
    except BracketIdentifierError as e:
        return [str(e)]
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

    calls = aggregate_calls(body)
    is_aggregate = bool(calls)
    if aggregate_only:
        if re.search(r"\bover\b", body, re.IGNORECASE):
            errors.append("window functions are not allowed")
        if any(c in ("group_concat", "string_agg") for c in calls) or re.search(
                r"\b(?:group_concat|string_agg)\s*\(", body, re.IGNORECASE):
            errors.append("group_concat and string_agg are not allowed (they return row-level text)")
        if not is_aggregate:
            errors.append("query must be aggregate (use at least one COUNT/SUM/AVG/MIN/MAX call)")

    stars = "*" in COUNT_STAR_RE.sub("count(1)", body)
    for table in pii_tables:
        if re.search(r"\b" + re.escape(table) + r"\b", body, re.IGNORECASE):
            if stars:
                errors.append(f"SELECT * is not allowed on PII table '{table}'")
            if not is_aggregate:
                errors.append(f"PII table '{table}' can only be read through aggregate queries")
            errors.extend(pii_select_errors(body, table))

    for m in LIMIT_RE.finditer(body):
        ok = LIMIT_OK_RE.match(body, m.start())
        if not ok:
            errors.append("LIMIT must be an integer, optionally followed by OFFSET and an integer")
        elif int(ok.group(1)) > max_rows:
            errors.append(f"LIMIT {ok.group(1)} exceeds max_rows {max_rows}")

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
