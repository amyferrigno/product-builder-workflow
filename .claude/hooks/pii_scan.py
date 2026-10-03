#!/usr/bin/env python3
"""
PostToolUse hook: scan anecdote and PRD artifacts for PII after a Write/Edit.
Reads the tool call from stdin as JSON. Scans runs/<run>/04-anecdotes.json,
runs/<run>/04-anecdotes.candidates.json and runs/<run>/prd.md using scripts/pii.py.
Exit 0 if not applicable or clean, exit 2 (findings on stderr) if PII is found.
Standard library only: scripts/pii.py reads pm.config.yaml with PyYAML when available,
otherwise with a small tolerant reader (defaults: no terms, allow_company_names false).
Never prints a traceback: any unexpected error fails open (exit 0).
"""

import os
import sys
import json
import importlib.util
from pathlib import Path

WATCHED = ("04-anecdotes.json", "04-anecdotes.candidates.json", "prd.md")


def is_watched(file_path: str, project_dir: str) -> bool:
    """True if the path is runs/<run>/<watched file> (case-insensitive on 'runs')."""
    p = Path(file_path)
    if not p.is_absolute():
        p = Path(project_dir) / p
    parts = Path(os.path.normpath(str(p))).parts
    for i, part in enumerate(parts):
        if part.lower() == "runs" and i + 3 == len(parts) and parts[i + 2] in WATCHED:
            return True
    return False


def load_pii_module(project_dir: str):
    path = Path(project_dir) / "scripts" / "pii.py"
    if not path.exists():
        path = Path(__file__).resolve().parent.parent.parent / "scripts" / "pii.py"
    spec = importlib.util.spec_from_file_location("pii", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    try:
        data = json.load(sys.stdin)
        file_path = data.get("tool_input", {}).get("file_path")
        if not file_path:
            sys.exit(0)

        project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parent.parent.parent)
        if not is_watched(file_path, project_dir):
            sys.exit(0)

        target = Path(os.path.normpath(str(Path(project_dir) / file_path if not Path(file_path).is_absolute() else file_path)))
        if not target.is_file():
            sys.exit(0)

        pii = load_pii_module(project_dir)
        pii_terms = {"people": [], "companies": []}
        allow = False
        config = Path(project_dir) / "pm.config.yaml"
        if config.exists():
            try:
                pii_terms, allow = pii.load_pii_config(str(config))
            except Exception:
                pass

        text = target.read_text(encoding="utf-8")
        findings = pii.scan(text, pii_terms, allow)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    if findings:
        lines = ["PII found:"]
        for f in findings:
            lines.append(f"{file_path}:{f['line']}: {f['type']}: {f['match']}")
        print("\n".join(lines), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
