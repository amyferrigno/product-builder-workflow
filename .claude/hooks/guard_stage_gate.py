#!/usr/bin/env python3
"""
PreToolUse hook to enforce stage order.
Blocks Write/Edit to runs/<id>/ux/** until the PRD is approved, and to
runs/<id>/tickets.* until the UX is approved (and still current).
Exit 0 if allowed, exit 2 if blocked.
"""

import os
import sys
import json
import importlib.util
from pathlib import Path


def resolve_path(file_path: str, project_dir: str) -> Path:
    """Resolve a file path to absolute path (relative paths start from the project dir)."""
    p = Path(file_path)
    if p.is_absolute():
        return p
    return Path(project_dir) / p


def find_gated_target(resolved: Path):
    """
    Return (artifact_needed, run_dir) when the path is gated, else (None, None).
    ux/** needs the PRD approval; tickets.* needs the UX approval.
    """
    # Collapse ".." segments and follow symlinks
    real = Path(os.path.realpath(os.path.normpath(str(resolved))))
    parts = real.parts
    for i, part in enumerate(parts):
        if part.lower() != "runs" or i + 2 >= len(parts):
            continue
        run_dir = Path(*parts[:i + 2])
        name = parts[i + 2]
        if name.lower() == "ux" and i + 3 < len(parts):
            return "prd", run_dir
        if i + 3 == len(parts) and name.lower().startswith("tickets."):
            return "ux", run_dir
    return None, None


def load_approval_status(project_dir: str):
    """Import approval_status from scripts/check_approval.py by file path."""
    path = Path(project_dir) / "scripts" / "check_approval.py"
    spec = importlib.util.spec_from_file_location("check_approval_for_hook", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.approval_status


def main():
    """Main entry point."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        # Malformed or empty stdin: fail open (exit 0)
        sys.exit(0)

    try:
        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path")
        if not file_path:
            sys.exit(0)

        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if not project_dir:
            project_dir = str(Path(__file__).parent.parent.parent)

        needed, run_dir = find_gated_target(resolve_path(file_path, project_dir))
        if needed is None:
            sys.exit(0)

        approval_status = load_approval_status(project_dir)
        ok, message = approval_status(str(run_dir), needed)
        if ok:
            sys.exit(0)

        run_id = run_dir.name
        what = "UX screens" if needed == "prd" else "tickets"
        print(
            f"Blocked: {what} cannot be written until the {needed.upper()} approval is valid "
            f"({message}). A human must run: /pm-approve {needed} {run_id}",
            file=sys.stderr,
        )
        sys.exit(2)

    except SystemExit:
        raise
    except Exception:
        # Any error: fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
