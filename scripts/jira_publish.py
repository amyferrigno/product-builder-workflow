#!/usr/bin/env python3
"""
Dry-run Jira publish: write the exact Jira payloads to runs/<id>/tickets.dryrun.json.
Usage: python scripts/jira_publish.py <run_dir> [--config pm.config.yaml]

Needs a valid tickets approval and jira.mode: dry_run. Nothing is sent anywhere:
this module imports no network library. Live publishing comes in M7.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_approval import approval_status  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DRYRUN_NAME = "tickets.dryrun.json"
MANIFEST_NAME = "tickets.manifest.json"
EPIC_PRIORITY = "Medium"  # epics carry no priority in the manifest


def _description(ticket: dict) -> str:
    """Plain-text description with the structured fields appended as sections."""
    parts = [str(ticket.get("description", "")).strip()]
    sections = (
        ("Acceptance criteria", ticket.get("acceptance_criteria")),
        ("Requirements", ticket.get("req_ids")),
        ("Screens", ticket.get("screen_ids")),
        ("Analytics events", ticket.get("analytics_events")),
        ("AI quality criteria", ticket.get("ai_quality_criteria")),
    )
    for title, items in sections:
        if items:
            parts.append(title + ":\n" + "\n".join(f"- {item}" for item in items))
    return "\n\n".join(parts)


def _labels(ticket: dict, defaults: List[str]) -> List[str]:
    out: List[str] = []
    for label in list(ticket.get("labels") or []) + defaults:
        if label not in out:
            out.append(label)
    return out


def _idempotency_label(ticket: dict) -> str:
    for label in ticket.get("labels") or []:
        if label.startswith("ext-"):
            return label
    return ""


def _entry(ticket: dict, issuetype: str, project_key: str, defaults: List[str], parent) -> dict:
    return {
        "ticket_id": ticket["id"],
        "action": "create",
        "idempotency_label": _idempotency_label(ticket),
        "parent_ticket_id": parent,
        "payload": {
            "fields": {
                "project": {"key": project_key},
                "summary": ticket["summary"],
                "description": _description(ticket),
                "issuetype": {"name": issuetype},
                "labels": _labels(ticket, defaults),
                "priority": {"name": ticket.get("priority") or EPIC_PRIORITY},
            }
        },
    }


def build_dryrun(manifest: dict, project_key: str, default_labels: List[str]) -> List[dict]:
    """Ordered entries: all epics first, then all children in manifest order."""
    epics = manifest["epics"]
    entries = [_entry(e, "Epic", project_key, default_labels, None) for e in epics]
    for epic in epics:
        for child in epic.get("children", []):
            entries.append(_entry(child, child["type"], project_key, default_labels, epic["id"]))
    return entries


def publish_dry_run(run_dir: str, config_path: str) -> List[dict]:
    """Write tickets.dryrun.json and return the entries. Raises ValueError when refused."""
    run_path = Path(run_dir)
    ok, message = approval_status(run_dir, "tickets")
    if not ok:
        raise ValueError(f"tickets approval is not valid ({message}); approve the tickets first")

    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"cannot read config {config_path}: {e}")
    jira = config.get("jira") if isinstance(config, dict) else None
    if not isinstance(jira, dict):
        raise ValueError(f"config {config_path} has no jira section")
    if jira.get("mode") != "dry_run":
        raise ValueError("live publish is not available until M7 (set jira.mode to dry_run)")

    project_key = str(jira.get("project_key", ""))
    default_labels = [str(x) for x in (jira.get("default_labels") or [])]

    try:
        manifest = json.loads((run_path / MANIFEST_NAME).read_text(encoding="utf-8"))
        entries = build_dryrun(manifest, project_key, default_labels)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"cannot read the ticket manifest: {e!r}")

    if project_key.startswith("[[") and project_key.endswith("]]"):
        print("Warning: project key is a placeholder")

    try:
        (run_path / DRYRUN_NAME).write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        raise ValueError(f"cannot write {DRYRUN_NAME}: {e}")
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run Jira publish (writes payloads, sends nothing).")
    parser.add_argument("run_dir", help="Run directory")
    parser.add_argument("--config", default=str(REPO_ROOT / "pm.config.yaml"), help="Config file")
    args = parser.parse_args()
    try:
        entries = publish_dry_run(args.run_dir, args.config)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    for entry in entries:
        fields = entry["payload"]["fields"]
        parent = f" (parent {entry['parent_ticket_id']})" if entry["parent_ticket_id"] else ""
        print(f"{entry['ticket_id']}: {fields['issuetype']['name']} {fields['summary']}{parent}")
    print(f"Wrote {Path(args.run_dir) / DRYRUN_NAME}")
    print("DRY RUN: nothing was sent to Jira")


if __name__ == "__main__":
    main()
