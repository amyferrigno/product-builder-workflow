#!/usr/bin/env python3
"""
PreToolUse hook to block approval file writes.
Reads tool call from stdin as JSON and blocks Write/Edit to runs/*/approvals/*.
For Bash: an approve.py command always gets an "ask" decision (a human must confirm),
and shell commands that change approval files are blocked.
Exit 0 if allowed (or after printing an "ask" decision), exit 2 if blocked.
"""

import os
import sys
import json
import shlex
from pathlib import Path


def resolve_path(file_path: str) -> Path:
    """Resolve a file path to absolute path."""
    p = Path(file_path)
    if p.is_absolute():
        return p
    else:
        # If relative, resolve from current working directory
        return Path.cwd() / p


def check_approval_path(file_path: str) -> bool:
    """
    Check if file_path matches runs/<anything>/approvals/<anything>.
    Returns True if it matches the approval path pattern.
    """
    try:
        p = resolve_path(file_path)
        # Collapse any ".." segments before matching
        parts = Path(os.path.normpath(str(p))).parts

        # Look for "runs" somewhere in the path (case-insensitive: the volume is)
        for i, part in enumerate(parts):
            if part.lower() == "runs" and i + 2 < len(parts):
                # Check if part at i+2 is "approvals"
                if parts[i + 2].lower() == "approvals":
                    return True

        return False
    except Exception:
        return False


SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
GATES = ("prd", "ux", "tickets")
OPTIONS_WITH_VALUE = {"--override", "--decisions-file", "--config"}
READ_COMMANDS = ("ls", "cat", "head", "tail", "stat", "wc", "shasum", "file")


def tokenize(command: str):
    """Split a shell command into tokens, keeping separators as their own tokens."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return command.split()


def approve_invocations(command: str):
    """
    Return one (run_dir, gate) tuple per approve.py invocation in the command.
    Either part is None when it cannot be extracted.
    """
    tokens = tokenize(command)
    found = []
    for i, tok in enumerate(tokens):
        prev = tokens[i - 1] if i > 0 else ""
        is_script = os.path.basename(tok) == "approve.py"
        is_module = tok == "approve" and prev == "-m"
        if not (is_script or is_module):
            continue
        # Skip interpreter options such as -u between "python" and the script
        k = i - 1
        while k >= 0 and tokens[k].startswith("-"):
            k -= 1
        before = tokens[k] if k >= 0 else ""
        base_before = os.path.basename(before).lower()
        if is_script and not (k < 0 or before in SEPARATORS or base_before.startswith("python")):
            continue  # e.g. "cat scripts/approve.py" does not run it
        if is_module and not base_before.startswith("python"):
            continue
        positionals = []
        j = i + 1
        while j < len(tokens) and tokens[j] not in SEPARATORS:
            arg = tokens[j]
            if arg in OPTIONS_WITH_VALUE:
                j += 2
                continue
            if not arg.startswith("-"):
                positionals.append(arg)
            j += 1
        gate = next((a for a in positionals if a in GATES), None)
        run_dir = next((a for a in positionals if a not in GATES), None)
        found.append((run_dir, gate))
    return found


def is_plain_read(command: str) -> bool:
    """A single read-only command: no redirect, pipe, chaining or substitution."""
    if any(ch in command for ch in (">", "|", ";", "&", "`", "\n")) or "$(" in command:
        return False
    tokens = command.split()
    return bool(tokens) and tokens[0] in READ_COMMANDS


def check_bash(command: str):
    """Ask a human for approve.py; block shell tricks that touch approval files."""
    invocations = approve_invocations(command)
    if invocations:
        run_dir, gate = invocations[0]
        if run_dir and gate:
            reason = f"{gate} approval for {run_dir}: a human must confirm"
        elif gate:
            reason = f"{gate} approval: a human must confirm"
        else:
            reason = "an approval command: a human must confirm"
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        }))
        sys.exit(0)

    lowered = command.lower()
    if ("approvals/" in lowered or ".approved" in lowered) and not is_plain_read(command):
        print(
            "Blocked: approval files are written only by scripts/approve.py after a human "
            "runs /pm-approve. Shell commands that change them are not allowed.",
            file=sys.stderr,
        )
        sys.exit(2)


def main():
    """Main entry point."""
    try:
        # Read JSON from stdin
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, EOFError):
        # Malformed or empty stdin: fail open (exit 0)
        sys.exit(0)
    except Exception:
        # Any other error: fail open
        sys.exit(0)

    # Check for tool_input.file_path
    try:
        tool_input = data.get("tool_input", {})

        if data.get("tool_name") == "Bash":
            command = tool_input.get("command")
            if isinstance(command, str) and command:
                check_bash(command)
            sys.exit(0)

        file_path = tool_input.get("file_path")

        if not file_path:
            # No file_path in tool_input: allow
            sys.exit(0)

        # Check if this is an approval file path
        if check_approval_path(file_path):
            # Block this write
            print("Blocked: approval files are written only by scripts/approve.py after a human runs /pm-approve.", file=sys.stderr)
            sys.exit(2)

        # Allow other paths
        sys.exit(0)

    except Exception:
        # Any error: fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
