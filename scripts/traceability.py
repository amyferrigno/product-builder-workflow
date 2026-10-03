#!/usr/bin/env python3
"""
Write runs/<id>/traceability.md: which screens cover which requirement.
Usage: python scripts/traceability.py <run_dir>

The approved prd.md is never edited; this file is generated from the PRD
requirement rows and the **REQs** lines of ux/spec.md.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_prd import parse_requirements  # noqa: E402
from validate_ux import spec_screen_reqs  # noqa: E402

JIRA_TEXT = "not yet created (Stage 3)"
NO_SCREEN = "-"
JIRA_SUFFIX = " (not yet published)"


def _tickets_by_req(run: Path) -> Optional[Dict[str, List[str]]]:
    """REQ id -> ids of the tickets citing it, or None when there is no readable manifest."""
    try:
        data = json.loads((run / "tickets.manifest.json").read_text(encoding="utf-8"))
        by_req: Dict[str, List[str]] = {}
        for epic in data["epics"]:
            for child in epic.get("children", []):
                for req in child.get("req_ids", []):
                    by_req.setdefault(req, []).append(child["id"])
        return by_req
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, AttributeError):
        return None


def build_traceability(run_dir) -> str:
    """Markdown table `| REQ | Priority | Screens | Jira |`. Raises OSError when prd.md or ux/spec.md is missing."""
    run = Path(run_dir)
    prd_text = (run / "prd.md").read_text(encoding="utf-8")
    spec_text = (run / "ux" / "spec.md").read_text(encoding="utf-8")
    by_req: Dict[str, List[str]] = {}
    for scr_id, reqs in spec_screen_reqs(spec_text).items():
        for req in reqs:
            by_req.setdefault(req, []).append(scr_id)
    tickets = _tickets_by_req(run)
    lines = [
        "# Traceability",
        "",
        "| REQ | Priority | Screens | Jira |",
        "|---|---|---|---|",
    ]
    for req_id, priority in parse_requirements(prd_text):
        screens = ", ".join(sorted(by_req.get(req_id, []))) or NO_SCREEN
        jira = JIRA_TEXT
        if tickets is not None:
            ids = ", ".join(sorted(tickets.get(req_id, []))) or NO_SCREEN
            jira = ids + JIRA_SUFFIX
        lines.append(f"| {req_id} | {priority} | {screens} | {jira} |")
    return "\n".join(lines) + "\n"


def write_traceability(run_dir) -> Path:
    path = Path(run_dir) / "traceability.md"
    path.write_text(build_traceability(run_dir), encoding="utf-8")
    return path


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/traceability.py <run_dir>")
        sys.exit(1)
    try:
        print(f"Wrote {write_traceability(sys.argv[1])}")
    except (OSError, UnicodeDecodeError) as e:
        print(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
