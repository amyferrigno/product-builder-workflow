#!/usr/bin/env python3
"""
PreToolUse hook: early warning against writing to Jira outside the approved path.
Blocks (exit 2):
  - a Jira/Atlassian MCP write tool while jira.mode is dry_run (or unreadable)
  - a Bash call to atlassian.net with curl, wget or http
  - a Bash call to jira_publish.py for a run whose tickets approval is not valid
The real control is jira_publish.py itself. Exit 0 if allowed, exit 2 if blocked.
"""

import os
import sys
import json
import shlex
import importlib.util
from pathlib import Path

WRITE_VERBS = (
    "create", "update", "edit", "delete", "transition", "add", "assign", "move", "link", "comment",
    "set", "post", "put", "patch", "upload", "archive", "clone", "upsert", "remove",
)
READ_PREFIXES = ("get", "search", "list", "read", "fetch", "lookup")
READ_ALLOWLIST = ("gettransitionsforjiraissue", "getjiraissueremoteissuelinks", "atlassianuserinfo")
SEPARATORS = {";", "&&", "||", "|", "&", "\n"}


def read_jira_mode(project_dir: str) -> str:
    """Read jira.mode from pm.config.yaml with a line parser. Unreadable means dry_run."""
    try:
        text = (Path(project_dir) / "pm.config.yaml").read_text(encoding="utf-8")
    except Exception:
        return "dry_run"
    in_jira = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indented = line[0] in " \t"
        if not indented:
            in_jira = line.strip() == "jira:"
            continue
        if in_jira and line.strip().startswith("mode:"):
            value = line.strip()[len("mode:"):].strip().strip("'\"")
            return value or "dry_run"
    return "dry_run"


def load_approval_status(project_dir: str):
    """Import approval_status from scripts/check_approval.py by file path."""
    path = Path(project_dir) / "scripts" / "check_approval.py"
    spec = importlib.util.spec_from_file_location("check_approval_for_hook", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.approval_status


def publish_run_dirs(command: str):
    """
    Return a list with one entry per jira_publish.py invocation in the command:
    the run dir argument (str) or None when there is none.
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    found = []
    for i, tok in enumerate(tokens):
        if os.path.basename(tok) != "jira_publish.py":
            continue
        prev = tokens[i - 1] if i > 0 else ""
        base_prev = os.path.basename(prev).lower()
        if not (i == 0 or prev in SEPARATORS or base_prev.startswith("python")):
            continue  # e.g. "cat scripts/jira_publish.py" does not run it
        run_dir = None
        j = i + 1
        while j < len(tokens) and tokens[j] not in SEPARATORS:
            arg = tokens[j]
            if arg == "--config":
                j += 2
                continue
            if arg.startswith("-"):
                j += 1
                continue
            run_dir = arg
            break
        found.append(run_dir)
    return found


def check_mcp(tool_name: str, project_dir: str):
    name = tool_name.lower()
    if "jira" not in name and "atlassian" not in name:
        return
    action = name.rsplit("__", 1)[-1]
    if action in READ_ALLOWLIST:
        return
    # A read prefix is not enough: "getOrCreate..." or "list_and_delete" still contain a write verb.
    # Anything that is neither allowlisted nor read-prefixed is treated as a write.
    if action.startswith(READ_PREFIXES) and not any(verb in action for verb in WRITE_VERBS):
        return
    if read_jira_mode(project_dir) == "dry_run":
        print(
            "Blocked: Jira is in dry-run mode, so Jira write tools are not allowed. "
            "Publishing to Jira arrives in M7. Use scripts/jira_publish.py for the dry-run payloads.",
            file=sys.stderr,
        )
        sys.exit(2)


def check_bash(command: str, project_dir: str):
    lowered = command.lower()
    if "atlassian.net" in lowered and any(w in lowered for w in ("curl", "wget", "http")):
        print(
            "Blocked: direct calls to atlassian.net are not allowed. "
            "Jira is in dry-run mode; publishing arrives in M7.",
            file=sys.stderr,
        )
        sys.exit(2)

    for run_arg in publish_run_dirs(command):
        if run_arg is None:
            print(
                "Blocked: jira_publish.py needs a run directory argument so the tickets "
                "approval can be checked.",
                file=sys.stderr,
            )
            sys.exit(2)
        run_dir = Path(run_arg)
        if not run_dir.is_absolute():
            run_dir = Path(project_dir) / run_dir
        approval_status = load_approval_status(project_dir)
        ok, message = approval_status(str(run_dir), "tickets")
        if not ok:
            print(
                f"Blocked: jira_publish.py needs a valid tickets approval ({message}). "
                f"A human must run: /pm-approve tickets {run_dir.name}",
                file=sys.stderr,
            )
            sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if not project_dir:
        project_dir = str(Path(__file__).parent.parent.parent)

    try:
        if not isinstance(data, dict):
            sys.exit(0)
        tool_name = data.get("tool_name") or ""
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
            sys.exit(0)

        if tool_name.startswith("mcp__"):
            check_mcp(tool_name, project_dir)
        elif tool_name == "Bash":
            command = tool_input.get("command")
            if isinstance(command, str) and command:
                check_bash(command, project_dir)
        sys.exit(0)

    except SystemExit:
        raise
    except Exception:
        # Any error: fail open (the control is jira_publish.py itself)
        sys.exit(0)


if __name__ == "__main__":
    main()
