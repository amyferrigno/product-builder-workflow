"""Helpers for ticket tests: build a temp run with approved PRD, approved UX and a valid manifest.

Usage in a test:
    from tickets_helpers import make_tickets_run, valid_manifest, write_manifest
    run = make_tickets_run(tmp_path, ai=True)       # manifest passes validate_tickets
    m = valid_manifest(run, ai=True)                # a fresh dict to edit
    m["epics"][0]["children"][0]["acceptance_criteria"].pop()
    write_manifest(run, m)

The run (tmp_path/run) holds state.json (run id "run-1"), prd.md and 02-problem.md copied from
a golden fixture (ai-clear-fit when ai, clean-meeting otherwise), a valid ux/ folder from
make_ux_run, valid PRD and UX approval files (written directly, no decisions file is touched)
and tickets.manifest.json. The manifest has a feature epic (EPIC-01: one Story per Must REQ on
SCR-001 with event screen_viewed, one instrumentation Task, one Spike) and a measure_quality
epic (EPIC-02: one eval Task).
"""

import json
import shutil
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from validate_prd import (  # noqa: E402
    extract_problem_ids,
    parse_problem_md_front_matter,
    parse_requirements,
)
from ux_gate_helpers import approve_prd_file, make_gate_run, sha  # noqa: E402
from ux_hash import ux_hash  # noqa: E402

MANIFEST_NAME = "tickets.manifest.json"


def slug_for(ai: bool) -> str:
    return "ai-clear-fit" if ai else "clean-meeting"


def approve_ux_file(run: Path) -> None:
    """Write a valid UX approval file for the current ux/ and prd.md."""
    (run / "approvals").mkdir(exist_ok=True)
    approval = {"artifact": "ux", "sha256": ux_hash(run), "prd_sha256": sha(run / "prd.md"),
                "verdict": "PASS", "override_reason": None, "approved_at": "2026-10-03T00:00:00Z"}
    (run / "approvals" / "ux.approved").write_text(json.dumps(approval), encoding="utf-8")


def _labels(slug: str, ticket_id: str, ai: bool) -> List[str]:
    labels = [f"prd-{slug}", "agentic-pm", f"ext-{slug}-{ticket_id.lower()}"]
    if ai:
        labels.append("ai-feature")
    return labels


def valid_manifest(run: Path, ai: bool) -> dict:
    """A manifest dict that passes validate_tickets for the run built by make_tickets_run."""
    slug = slug_for(ai)
    prd_text = (run / "prd.md").read_text(encoding="utf-8")
    must = [r for r, p in parse_requirements(prd_text) if p.strip().lower() == "must"]
    problem = sorted(extract_problem_ids(parse_problem_md_front_matter(run / "02-problem.md")))[0]

    children = []
    n = 0
    for req in must:
        n += 1
        tid = f"T-{n:03d}"
        story = {
            "id": tid, "type": "Story",
            "summary": f"[Scheduling] Deliver {req} behaviour",
            "description": f"Deliver the behaviour required by {req} so the user can rely on it.",
            "labels": _labels(slug, tid, ai), "priority": "High",
            "req_ids": [req], "screen_ids": ["SCR-001"],
            "acceptance_criteria": [
                f"Given a user on the home screen, When {req} applies, Then the result is shown",
                "Given an empty state, When the user opens the screen, Then guidance is shown",
                "Given an error, When the action fails, Then a clear message is shown",
            ],
            "blocks": [], "jira_key": None,
            "user_facing": True, "analytics_events": ["screen_viewed"],
        }
        if ai:
            story["ai_quality_criteria"] = [f"Accuracy for {req} meets the PRD threshold on the holdout set"]
        children.append(story)

    def other(kind: str, summary: str, extra: dict) -> dict:
        nonlocal n
        n += 1
        tid = f"T-{n:03d}"
        ticket = {
            "id": tid, "type": kind, "summary": summary,
            "description": f"{summary} so the team can check the feature works as intended.",
            "labels": _labels(slug, tid, ai), "priority": "Medium",
            "req_ids": [], "screen_ids": [],
            "acceptance_criteria": ["The work is done and checked by the team"],
            "blocks": [], "jira_key": None,
        }
        ticket.update(extra)
        return ticket

    children.append(other("Task", "[Analytics] Add events for the main screens", {"task_kind": "instrumentation"}))
    children.append(other("Spike", "[Scheduling] Investigate open question one", {"open_question_ref": "OQ-1"}))
    quality = other("Task", "[Quality] Report quality metrics weekly", {"task_kind": "eval"})

    def epic(eid: str, summary: str, kind: str, kids: List[dict]) -> dict:
        return {
            "id": eid, "summary": summary,
            "description": f"{summary} to solve the problem described in the PRD.",
            "labels": _labels(slug, eid, ai), "problem_ref": problem,
            "kind": kind, "jira_key": None, "children": kids,
        }

    return {
        "run_id": "run-1", "prd_slug": slug, "initiative": None,
        "epics": [
            epic("EPIC-01", "[Scheduling] Deliver the feature", "feature", children),
            epic("EPIC-02", "[Quality] Measure feature quality", "measure_quality", [quality]),
        ],
    }


def write_manifest(run: Path, manifest: dict) -> None:
    (run / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def make_tickets_run(tmp_path: Path, ai: bool = False) -> Path:
    """Build tmp_path/run with approved PRD and UX and a valid manifest; return the run dir."""
    run = make_gate_run(tmp_path, ai=ai, prd_approved=True)
    golden = REPO_ROOT / "fixtures" / slug_for(ai) / "golden" / "02-problem.md"
    shutil.copy(golden, run / "02-problem.md")
    approve_prd_file(run)
    approve_ux_file(run)
    write_manifest(run, valid_manifest(run, ai))
    return run
