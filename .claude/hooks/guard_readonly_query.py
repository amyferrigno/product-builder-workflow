#!/usr/bin/env python3
"""
PreToolUse hook that blocks mutating or non-aggregate SQL.
Reads the tool call from stdin as JSON.
  - Bash: looks for a --sql argument in tool_input.command (shlex.split, tolerant of failure).
  - mcp__*: checks the string fields sql, query, statement and sql_query (key names matched
    case-insensitively) in tool_input and in any dict nested one level inside it (for example
    tool_input.params.sql), but only when a statement in the text parses as SQL: the first keyword
    must be followed by SQL-shaped words (SELECT ... FROM, UPDATE t SET, DELETE FROM, DROP TABLE, ...).
    Plain-text search queries such as "Update on scheduling complaints" are ignored.
Runs scripts/sql_guard.py check_sql (imported by path). Standard library only, so
pii_tables and max_rows_returned are read from $CLAUDE_PROJECT_DIR/pm.config.yaml with a
tolerant line parser (defaults: no PII tables, 500 rows if the file is unreadable).
Exit 0 if allowed (and on malformed input), exit 2 with the reasons on stderr if blocked.
"""

import os
import re
import sys
import json
import shlex
import importlib.util
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parent.parent.parent)
MCP_SQL_FIELDS = ("sql", "query", "statement", "sql_query")
_IDENT = r"[\w.\"`\[\]]+"
_OBJECTS = (
    r"(?:OR|TABLE|TEMP|TEMPORARY|VIEW|MATERIALIZED|INDEX|UNIQUE|SCHEMA|DATABASE|USER|ROLE|FUNCTION|PROCEDURE"
    r"|TRIGGER|SEQUENCE|EXTENSION|TYPE|DOMAIN|POLICY|VIRTUAL|EXTERNAL|STAGE|WAREHOUSE|COLUMN)"
)
SQL_STATEMENT_PATTERNS = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in (
        r"^SELECT\b.+?\bFROM\b",
        r"^WITH\s+(?:RECURSIVE\s+)?" + _IDENT + r"\s+AS\s*\(",
        r"^INSERT\s+(?:OR\s+\w+\s+)?INTO\b",
        r"^UPDATE\s+" + _IDENT + r"(?:\s+(?:AS\s+)?\w+)?\s+SET\b",
        r"^DELETE\s+FROM\b",
        r"^MERGE\s+INTO\b",
        r"^(?:DROP|ALTER|CREATE)\s+" + _OBJECTS + r"\b",
        r"^TRUNCATE\s+(?:TABLE\s+\S|" + _IDENT + r"\s*(?:$|CASCADE\b|RESTART\b|CONTINUE\b))",
        r"^GRANT\b.+?\b(?:ON|TO)\b",
        r"^REPLACE\s+INTO\b",
        r"^ATTACH\s+(?:DATABASE\s+)?(?:['\"]|:memory:|\S+\s+AS\s+\w)",
        r"^PRAGMA\s+" + _IDENT,
    )
]


def looks_like_sql(text: str) -> bool:
    """True if any ';'-separated statement in the text parses as the start of an SQL statement."""
    stripped = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    stripped = re.sub(r"--[^\n]*", " ", stripped)
    for statement in stripped.split(";"):
        statement = statement.strip()
        if statement and any(p.match(statement) for p in SQL_STATEMENT_PATTERNS):
            return True
    return False


def mcp_sql_texts(tool_input: dict):
    """String values of the SQL-like fields in tool_input and in dicts nested one level inside it."""
    scopes = [tool_input] + [v for v in tool_input.values() if isinstance(v, dict)]
    found = []
    for scope in scopes:
        for key, value in scope.items():
            if isinstance(key, str) and key.lower() in MCP_SQL_FIELDS and isinstance(value, str):
                found.append(value)
    return found


def load_check_sql():
    path = Path(__file__).resolve().parent.parent.parent / "scripts" / "sql_guard.py"
    spec = importlib.util.spec_from_file_location("sql_guard", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_sql


def read_data_settings(config_path: Path):
    """
    Tolerant read of data.pii_tables and data.max_rows_returned without a YAML library.
    Understands `pii_tables: [a, b]` and a dash list under `pii_tables:`.
    """
    pii_tables = []
    max_rows = 500
    aggregate_only = True
    try:
        lines = config_path.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return pii_tables, max_rows, aggregate_only

    in_data = False
    in_pii_list = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            in_data = line.strip() == "data:"
            in_pii_list = False
            continue
        if not in_data:
            continue
        stripped = line.strip()
        m = re.match(r"max_rows_returned:\s*(\d+)", stripped)
        if m:
            max_rows = int(m.group(1))
            in_pii_list = False
            continue
        m = re.match(r"aggregate_only:\s*(true|false)", stripped, re.IGNORECASE)
        if m:
            aggregate_only = m.group(1).lower() == "true"
            in_pii_list = False
            continue
        m = re.match(r"pii_tables:\s*(.*)$", stripped)
        if m:
            rest = m.group(1).split("#")[0].strip()
            in_pii_list = rest == ""
            if rest.startswith("["):
                pii_tables = [t.strip().strip("'\"") for t in rest.strip("[]").split(",") if t.strip()]
            continue
        if in_pii_list and stripped.startswith("- "):
            pii_tables.append(stripped[2:].split("#")[0].strip().strip("'\""))
        else:
            in_pii_list = False
    return pii_tables, max_rows, aggregate_only


def sql_from_bash(command: str):
    """Return the SQL text following --sql (or --sql=...), or None."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    found = []
    for i, token in enumerate(tokens):
        if token == "--sql" and i + 1 < len(tokens):
            found.append(tokens[i + 1])
        elif token.startswith("--sql="):
            found.append(token[len("--sql="):])
    return found


def main():
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
            sys.exit(0)

        queries = []
        if tool_name == "Bash":
            command = tool_input.get("command")
            if isinstance(command, str) and "--sql" in command:
                queries = sql_from_bash(command)
        elif tool_name.startswith("mcp__"):
            queries = [text for text in mcp_sql_texts(tool_input) if looks_like_sql(text)]
        if not queries:
            sys.exit(0)

        check_sql = load_check_sql()
        pii_tables, max_rows, aggregate_only = read_data_settings(PROJECT_DIR / "pm.config.yaml")
        errors = []
        for sql in queries:
            errors.extend(check_sql(sql, pii_tables, max_rows, aggregate_only))
    except SystemExit:
        raise
    except Exception:
        # Malformed input or an unexpected failure: fail open
        sys.exit(0)

    if errors:
        print("Blocked: query is not allowed (read-only, aggregate queries only):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
