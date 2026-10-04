#!/usr/bin/env python3
"""
Write runs/<id>/tickets.preview.md: a readable preview of the ticket manifest.
Usage: python scripts/preview_tickets.py <run_dir>

Sections: totals by type, a tree (epic, then its children), the Must coverage
table (REQ to tickets) and the Definition of Ready result from validate_tickets.
Exit 0 when the file is written, 1 when the manifest cannot be read.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_prd import parse_requirements
from validate_tickets import MANIFEST_NAME, validate_tickets

PREVIEW_NAME = "tickets.preview.md"


def _load(run: Path) -> dict:
    try:
        data = json.loads((run / MANIFEST_NAME).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"manifest not found: {run / MANIFEST_NAME}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"cannot read manifest: {e}")
    if not isinstance(data, dict):
        raise ValueError("manifest top level must be an object")
    return data


def _epics(data: dict) -> List[dict]:
    return [e for e in data.get("epics", []) if isinstance(e, dict)]


def _children(epic: dict) -> List[dict]:
    return [c for c in epic.get("children", []) if isinstance(c, dict)]


def build_preview(run_dir, repo_root=None) -> str:
    """Markdown preview text. ValueError when the manifest is missing or unreadable."""
    run = Path(run_dir)
    data = _load(run)
    epics = _epics(data)

    counts: Dict[str, int] = {"Epic": len(epics), "Story": 0, "Task": 0, "Spike": 0}
    for epic in epics:
        for child in _children(epic):
            ctype = child.get("type")
            if ctype in counts:
                counts[ctype] += 1
    total = sum(counts.values())

    lines = [
        f"# Ticket preview: {data.get('prd_slug', 'unknown')}",
        "",
        f"Run: {data.get('run_id', 'unknown')}",
        "",
        "## Totals",
        "",
        f"- Total tickets: {total}",
    ]
    for name in ("Epic", "Story", "Task", "Spike"):
        lines.append(f"- {name}: {counts[name]}")

    lines += ["", "## Tickets", ""]
    by_req: Dict[str, List[str]] = {}
    for epic in epics:
        lines.append(
            f"- Epic {epic.get('id', '?')}: {epic.get('summary', '')} "
            f"(kind: {epic.get('kind', 'feature')}, problem: {epic.get('problem_ref', '-')})"
        )
        for child in _children(epic):
            cid = str(child.get("id", "?"))
            reqs = [r for r in child.get("req_ids", []) if isinstance(r, str)]
            screens = [s for s in child.get("screen_ids", []) if isinstance(s, str)]
            blocks = [b for b in child.get("blocks", []) if isinstance(b, str)]
            criteria = child.get("acceptance_criteria", [])
            lines.append(
                f"  - {child.get('type', '?')} {cid}: {child.get('summary', '')} | "
                f"priority {child.get('priority', '-')} | "
                f"REQs {', '.join(reqs) or '-'} | screens {', '.join(screens) or '-'} | "
                f"criteria {len(criteria) if isinstance(criteria, list) else 0} | "
                f"blocks {', '.join(blocks) or '-'}"
            )
            if child.get("type") == "Story":
                for req in reqs:
                    by_req.setdefault(req, []).append(cid)

    lines += ["", "## Must coverage", "", "| REQ | Tickets |", "| --- | --- |"]
    try:
        prd_text = (run / "prd.md").read_text(encoding="utf-8")
        must = [r for r, p in parse_requirements(prd_text) if p.strip().lower() == "must"]
    except OSError:
        must = []
        lines.append("| (prd.md not found) | - |")
    for req in must:
        lines.append(f"| {req} | {', '.join(by_req.get(req, [])) or 'NOT COVERED'} |")

    errors = validate_tickets(run, repo_root=repo_root)
    lines += ["", "## Definition of Ready", ""]
    if errors:
        lines.append(f"FAIL: {len(errors)} error(s)")
        lines.append("")
        lines.extend(f"- {e}" for e in errors)
    else:
        lines.append("PASS: no errors")
    return "\n".join(lines) + "\n"


def write_preview(run_dir, repo_root=None) -> Path:
    """Write tickets.preview.md into the run folder and return its path."""
    text = build_preview(run_dir, repo_root=repo_root)
    path = Path(run_dir) / PREVIEW_NAME
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise ValueError(f"cannot write {path}: {e}")
    return path


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/preview_tickets.py <run_dir>")
        sys.exit(1)
    try:
        path = write_preview(sys.argv[1])
    except ValueError as e:
        print(str(e))
        sys.exit(1)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
