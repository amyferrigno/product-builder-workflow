#!/usr/bin/env python3
"""
PreToolUse hook to block approval file writes.
Reads tool call from stdin as JSON and blocks Write/Edit to runs/*/approvals/*.
Exit 0 if allowed, exit 2 if blocked.
"""

import os
import sys
import json
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
