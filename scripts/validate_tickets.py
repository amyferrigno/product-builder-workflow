#!/usr/bin/env python3
"""
Validate runs/<id>/tickets.manifest.json against the Definition of Ready.
Usage: python scripts/validate_tickets.py <run_dir>

Checks the schema, ids, labels, summaries, descriptions, acceptance criteria,
REQ / screen / event / problem links, Must coverage, blocks cycles and that no
jira_key is set yet. Every error starts with the ticket id.
One error per line; exit 0 when clean, 1 otherwise. Never a traceback.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_verdict import prd_has_ai_addendum  # noqa: E402
from validate_prd import (  # noqa: E402
    extract_problem_ids,
    parse_problem_md_front_matter,
    parse_requirements,
)
from validate_ux import spec_screen_events  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(2)

MANIFEST_NAME = "tickets.manifest.json"
EPIC_ID_RE = re.compile(r'^EPIC-\d{2}$')
CHILD_ID_RE = re.compile(r'^T-\d{3}$')
SUMMARY_RE = re.compile(r'^\[[^\]]+\] [A-Z][a-z]+ \S')
BANNED_RE = re.compile(r'TODO|TBD|\[\[|lorem', re.IGNORECASE)
PRIORITIES = ("Highest", "High", "Medium", "Low")
MAX_SUMMARY = 80
MIN_DESCRIPTION = 40
MIN_STORY_CRITERIA = 3


def default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def expected_labels(prd_slug: str, ticket_id: str, ai: bool) -> List[str]:
    """Labels every ticket must carry."""
    labels = [f"prd-{prd_slug}", "agentic-pm", f"ext-{prd_slug}-{ticket_id.lower()}"]
    if ai:
        labels.append("ai-feature")
    return labels


def _schema_errors(data: dict, repo_root: Path) -> List[str]:
    schema_path = repo_root / "schemas" / "ticket-manifest.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"manifest: cannot load schema {schema_path}"]
    errors: List[str] = []
    for err in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(map(str, e.path))):
        where = "manifest"
        path = list(err.absolute_path)
        try:
            if len(path) >= 2 and path[0] == "epics":
                epic = data["epics"][path[1]]
                where = str(epic.get("id", where))
                if len(path) >= 4 and path[2] == "children":
                    where = str(epic["children"][path[3]].get("id", where))
        except (KeyError, IndexError, TypeError, AttributeError):
            pass
        location = "/".join(str(p) for p in path) or "(root)"
        errors.append(f"{where}: schema: {location}: {err.message}")
    return errors


def _text_fields(ticket: dict) -> List[str]:
    texts = [ticket.get("summary", ""), ticket.get("description", "")]
    for key in ("acceptance_criteria", "ai_quality_criteria"):
        texts.extend(t for t in ticket.get(key, []) if isinstance(t, str))
    return [t for t in texts if isinstance(t, str)]


def _non_blank(ticket: dict, key: str) -> List[str]:
    """Entries of a list field that are non-blank strings."""
    return [x for x in ticket.get(key, []) if isinstance(x, str) and x.strip()]


def _blank_errors(tid: str, ticket: dict) -> List[str]:
    errors: List[str] = []
    for key in ("acceptance_criteria", "ai_quality_criteria", "analytics_events"):
        for item in ticket.get(key, []):
            if not isinstance(item, str) or not item.strip():
                errors.append(f"{tid}: {key} has a blank entry")
    return errors


def _check_common(tid: str, ticket: dict, prd_slug: str, ai: bool) -> List[str]:
    errors: List[str] = []
    summary = ticket.get("summary", "")
    if len(summary) > MAX_SUMMARY:
        errors.append(f"{tid}: summary longer than {MAX_SUMMARY} characters")
    if not SUMMARY_RE.match(summary):
        errors.append(f"{tid}: summary must match '[Area] Verb object': '{summary}'")
    if any(BANNED_RE.search(t) for t in _text_fields(ticket)):
        errors.append(f"{tid}: contains TODO, TBD, [[ or lorem text")
    if len(ticket.get("description", "").strip()) < MIN_DESCRIPTION:
        errors.append(f"{tid}: description shorter than {MIN_DESCRIPTION} characters")
    labels = ticket.get("labels", [])
    for label in expected_labels(prd_slug, tid, ai)[:3]:
        if label not in labels:
            errors.append(f"{tid}: missing label '{label}'")
    errors.extend(_blank_errors(tid, ticket))
    own_ext = f"ext-{prd_slug}-{tid.lower()}"
    for label in labels:
        if isinstance(label, str) and label.startswith("ext-") and label != own_ext:
            errors.append(f"{tid}: label '{label}' belongs to another ticket (only '{own_ext}' is allowed)")
    if ai and "ai-feature" not in labels:
        errors.append(f"{tid}: missing label 'ai-feature' (the PRD has an AI addendum)")
    if not ai and "ai-feature" in labels:
        errors.append(f"{tid}: label 'ai-feature' not allowed (the PRD has no AI addendum)")
    if ticket.get("jira_key") is not None:
        errors.append(f"{tid}: jira_key must be null (nothing is published in M6)")
    return errors


def _find_cycle(graph: Dict[str, List[str]]) -> Optional[str]:
    """Return an id on a cycle of the blocks graph, or None."""
    state: Dict[str, int] = {}

    def visit(node: str) -> Optional[str]:
        state[node] = 1
        for nxt in graph.get(node, []):
            if nxt not in graph or nxt == node:
                continue
            if state.get(nxt) == 1:
                return nxt
            if nxt not in state:
                found = visit(nxt)
                if found:
                    return found
        state[node] = 2
        return None

    for start in graph:
        if start not in state:
            found = visit(start)
            if found:
                return found
    return None


def validate_tickets(run_dir, repo_root=None) -> List[str]:
    """Return a list of error strings for the run's ticket manifest (empty list means ready)."""
    run = Path(run_dir)
    root = Path(repo_root) if repo_root else default_repo_root()
    manifest_path = run / MANIFEST_NAME
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"manifest: file not found: {manifest_path}"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"manifest: cannot read as JSON: {e}"]
    if not isinstance(data, dict):
        return ["manifest: top level must be an object"]

    errors = _schema_errors(data, root)
    if errors:
        return errors

    try:
        prd_text = (run / "prd.md").read_text(encoding="utf-8")
    except OSError:
        return [f"manifest: prd.md not found in {run}"]
    requirements = parse_requirements(prd_text)
    prd_reqs = {r for r, _ in requirements}
    must_reqs = [r for r, p in requirements if p.strip().lower() == "must"]
    ai = prd_has_ai_addendum(prd_text)

    try:
        state = json.loads((run / "state.json").read_text(encoding="utf-8"))
        state_run_id = state.get("run_id") if isinstance(state, dict) else None
    except (OSError, json.JSONDecodeError):
        state_run_id = None
        errors.append("manifest: state.json missing or unreadable")
    if state_run_id is not None and data["run_id"] != state_run_id:
        errors.append(f"manifest: run_id '{data['run_id']}' does not match state run id '{state_run_id}'")

    problem_ids: Optional[Set[str]] = None
    try:
        problem_ids = extract_problem_ids(parse_problem_md_front_matter(run / "02-problem.md"))
    except (OSError, ValueError, AttributeError) as e:
        errors.append(f"manifest: cannot read 02-problem.md: {e}")

    screen_events: Dict[str, List[str]] = {}
    try:
        screen_events = spec_screen_events((run / "ux" / "spec.md").read_text(encoding="utf-8"))
    except OSError:
        errors.append("manifest: ux/spec.md not found")

    prd_slug = data["prd_slug"]
    seen: Set[str] = set()
    child_ids: Set[str] = set()
    graph: Dict[str, List[str]] = {}
    measure_epics = 0

    for epic in data["epics"]:
        eid = epic["id"]
        if not EPIC_ID_RE.match(eid):
            errors.append(f"{eid}: epic id must look like EPIC-##")
        if eid in seen:
            errors.append(f"{eid}: duplicate id")
        seen.add(eid)
        errors.extend(_check_common(eid, epic, prd_slug, ai))
        if problem_ids is not None and epic["problem_ref"] not in problem_ids:
            errors.append(f"{eid}: problem_ref '{epic['problem_ref']}' not found in 02-problem.md")
        children = epic["children"]
        if not children:
            errors.append(f"{eid}: epic has no child tickets")
        kind = epic.get("kind", "feature")
        if kind == "measure_quality":
            measure_epics += 1
        else:
            instr = [c for c in children if c["type"] == "Task" and c.get("task_kind") == "instrumentation"]
            if len(instr) != 1:
                errors.append(
                    f"{eid}: feature epic needs exactly one Task with task_kind 'instrumentation', found {len(instr)}"
                )

        for child in children:
            cid = child["id"]
            if not CHILD_ID_RE.match(cid):
                errors.append(f"{cid}: ticket id must look like T-###")
            if cid in seen:
                errors.append(f"{cid}: duplicate id")
            seen.add(cid)
            child_ids.add(cid)
            graph[cid] = list(child["blocks"])
            errors.extend(_check_common(cid, child, prd_slug, ai))
            if child["priority"] not in PRIORITIES:
                errors.append(f"{cid}: priority must be one of {', '.join(PRIORITIES)}")
            criteria = _non_blank(child, "acceptance_criteria")
            ctype = child["type"]

            if ctype == "Story":
                reqs = child["req_ids"]
                if not reqs:
                    errors.append(f"{cid}: story needs at least one req_ids entry")
                for req in reqs:
                    if req not in prd_reqs:
                        errors.append(f"{cid}: unknown requirement {req} (not in prd.md)")
                if len(criteria) < MIN_STORY_CRITERIA:
                    errors.append(
                        f"{cid}: story needs at least {MIN_STORY_CRITERIA} acceptance criteria, found {len(criteria)}"
                    )
                for crit in criteria:
                    missing = [w for w in ("Given", "When", "Then") if w not in crit]
                    if missing:
                        errors.append(f"{cid}: criterion lacks {', '.join(missing)}: '{crit}'")
                if "user_facing" not in child:
                    errors.append(f"{cid}: user_facing is required (true or false)")
                elif child["user_facing"]:
                    screens = child["screen_ids"]
                    if not screens:
                        errors.append(f"{cid}: user-facing story needs at least one screen_ids entry")
                    known: Set[str] = set()
                    for scr in screens:
                        if scr not in screen_events:
                            errors.append(f"{cid}: unknown screen {scr} (not in ux/spec.md)")
                        else:
                            known.update(screen_events[scr])
                    events = _non_blank(child, "analytics_events")
                    if not events:
                        errors.append(f"{cid}: user-facing story needs at least one analytics_events entry")
                    for event in events:
                        if event not in known:
                            errors.append(f"{cid}: analytics event '{event}' is not listed on its screens")
                if ai and not _non_blank(child, "ai_quality_criteria"):
                    errors.append(f"{cid}: story needs at least one ai_quality_criteria entry (AI feature)")
            else:
                for scr in child["screen_ids"]:
                    if scr not in screen_events:
                        errors.append(f"{cid}: unknown screen {scr} (not in ux/spec.md)")
                if not criteria:
                    errors.append(f"{cid}: {ctype.lower()} needs at least 1 acceptance criterion")
                if ctype == "Task" and "task_kind" not in child:
                    errors.append(f"{cid}: task_kind is required for a Task")
                if ctype == "Spike" and not child.get("open_question_ref", "").strip():
                    errors.append(f"{cid}: spike needs a non-empty open_question_ref")

    if measure_epics != 1:
        errors.append(f"manifest: exactly one epic must have kind 'measure_quality', found {measure_epics}")

    story_covered: Set[str] = set()
    for epic in data["epics"]:
        for child in epic["children"]:
            if child["type"] == "Story":
                story_covered.update(child["req_ids"])
    for req in must_reqs:
        if req not in story_covered:
            errors.append(f"{req}: Must requirement is not covered by any Story")

    for cid, blocked in graph.items():
        for target in blocked:
            if target == cid:
                errors.append(f"{cid}: blocks itself")
            elif target not in child_ids:
                errors.append(f"{cid}: blocks unknown ticket {target}")
    cyclic = _find_cycle(graph)
    if cyclic:
        errors.append(f"{cyclic}: blocks cycle detected")
    return errors


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_tickets.py <run_dir>")
        sys.exit(1)
    try:
        errors = validate_tickets(sys.argv[1])
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError) as e:
        print(f"manifest: {e}")
        sys.exit(1)
    for error in errors:
        print(error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
