#!/usr/bin/env python3
"""
PreToolUse hook that blocks mutating or non-aggregate SQL.
Reads the tool call from stdin as JSON.
  - Bash: looks for a --sql argument in tool_input.command (shlex.split, tolerant of failure).
  - mcp__*: checks the string fields sql, query and statement in tool_input, but only when the
    text begins with an SQL statement keyword or has a second statement after ';'
    (plain-text search queries are ignored).
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
MCP_SQL_FIELDS = ("sql", "query", "statement")
SQL_START = re.compile(
    r"^(SELECT|WITH|INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|GRANT|TRUNCATE|REPLACE|ATTACH|PRAGMA)\b",
    re.IGNORECASE,
)


def looks_like_sql(text: str) -> bool:
    """True if the text begins with an SQL statement keyword or has a second statement after ';'."""
    stripped = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    stripped = re.sub(r"--[^\n]*", " ", stripped).strip()
    if SQL_START.match(stripped):
        return True
    head, sep, tail = stripped.partition(";")
    return bool(sep and tail.strip())


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
            queries = [
                tool_input[f] for f in MCP_SQL_FIELDS
                if isinstance(tool_input.get(f), str) and looks_like_sql(tool_input[f])
            ]
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
