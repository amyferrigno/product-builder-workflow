#!/usr/bin/env python3
"""
Jira publish. Default is a dry run: write the exact Jira payloads to runs/<id>/tickets.dryrun.json.
Usage: python scripts/jira_publish.py <run_dir> [--config pm.config.yaml] [--publish]

Needs a valid tickets approval. A dry run (jira.mode: dry_run, no --publish) sends nothing and
does not even import the Jira client. Going live needs two keys: jira.mode: publish in the
config AND the --publish flag. Credentials come only from JIRA_EMAIL and JIRA_API_TOKEN.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import yaml
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_approval import approval_status
from traceability import write_traceability
from validate_tickets import validate_tickets

REPO_ROOT = Path(__file__).resolve().parent.parent
DRYRUN_NAME = "tickets.dryrun.json"
MANIFEST_NAME = "tickets.manifest.json"
STATE_NAME = "state.json"
PUBLISHED_NAME = "tickets.published.json"
EPIC_PRIORITY = "Medium"  # epics carry no priority in the manifest
DEFAULT_ISSUE_TYPES = {"Epic": "Epic", "Story": "Story", "Task": "Task", "Spike": "Task"}
DEFAULT_MIN_INTERVAL = 0.2
DEFAULT_MAX_RETRIES = 5
DEFAULT_SEARCH_WAIT = 3
TWO_KEYS = "going live needs two keys: jira.mode: publish in the config AND the --publish flag"


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


def _idempotency_label(prd_slug: str, ticket: dict) -> str:
    return f"ext-{prd_slug}-{str(ticket['id']).lower()}"


def _entry(
    ticket: dict, issuetype: str, project_key: str, defaults: List[str], parent, prd_slug: str
) -> dict:
    return {
        "ticket_id": ticket["id"],
        "action": "create",
        "idempotency_label": _idempotency_label(prd_slug, ticket),
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
    slug = manifest["prd_slug"]
    entries = [_entry(e, "Epic", project_key, default_labels, None, slug) for e in epics]
    for epic in epics:
        for child in epic.get("children", []):
            entries.append(_entry(child, child["type"], project_key, default_labels, epic["id"], slug))
    return entries


def publish_dry_run(run_dir: str, config_path: str) -> List[dict]:
    """Write tickets.dryrun.json and return the entries. Raises ValueError when refused."""
    run_path = Path(run_dir)
    ok, message = approval_status(run_dir, "tickets")
    if not ok:
        raise ValueError(f"tickets approval is not valid ({message}); approve the tickets first")
    errors = validate_tickets(run_dir)
    if errors:
        raise ValueError("ticket manifest is not valid:\n" + "\n".join(errors))

    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"cannot read config {config_path}: {e}")
    jira = config.get("jira") if isinstance(config, dict) else None
    if not isinstance(jira, dict):
        raise ValueError(f"config {config_path} has no jira section")
    if jira.get("mode") == "publish":
        raise ValueError(f"jira.mode is publish but --publish was not given; {TWO_KEYS}")
    if jira.get("mode") != "dry_run":
        raise ValueError(f"unknown jira.mode {jira.get('mode')!r}: use dry_run or publish")

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


def _is_placeholder(value: str) -> bool:
    return "[[" in value


def _load_jira_config(config_path: str) -> dict:
    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"cannot read config {config_path}: {e}")
    jira = config.get("jira") if isinstance(config, dict) else None
    if not isinstance(jira, dict):
        raise ValueError(f"config {config_path} has no jira section")
    return jira


def _write_json_atomic(path: Path, data) -> None:
    """Write JSON to a temp file next to path, then replace path with it."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        raise ValueError(f"cannot write {path.name}: {e}")


def _read_json(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read {what}: {e}")


class PublishFailed(ValueError):
    """A Jira call failed midway. Keys already written stay; a rerun resumes."""


def _live_fields(entry: dict, issue_types: Dict[str, str], logical_type: str, to_adf) -> dict:
    fields = dict(entry["payload"]["fields"])
    fields["issuetype"] = {"name": issue_types.get(logical_type, logical_type)}
    fields["description"] = to_adf(fields["description"])
    return fields


def _blocks_section(ticket: dict, tickets: Dict[str, dict], keys: Dict[str, str]) -> str:
    """Plain 'Blocks' section for the live description; empty when the ticket blocks nothing."""
    lines = []
    for bid in ticket.get("blocks") or []:
        other = tickets.get(bid, {})
        ref = f"{bid} ({keys[bid]})" if bid in keys else str(bid)
        lines.append(f"- {ref}: {other.get('summary', '')}")
    return "Blocks:\n" + "\n".join(lines) if lines else ""


def publish(run_dir: str, config_path: str, client=None, sleep=None) -> dict:
    """Publish the approved manifest to Jira. Returns {"created": n, "updated": m}.

    Raises ValueError when a precondition fails (nothing was sent) and PublishFailed when a
    Jira call fails midway. `client` is injected by tests; otherwise it is built from the config
    and the JIRA_EMAIL / JIRA_API_TOKEN environment variables. `sleep` (seconds) is used to wait
    before the fallback search after a failed create; it defaults to the client's own sleep.
    """
    run_path = Path(run_dir)
    jira = _load_jira_config(config_path)
    if jira.get("mode") != "publish":
        raise ValueError(f"--publish was given but jira.mode is not publish; {TWO_KEYS}")

    ok, message = approval_status(run_dir, "tickets")
    if not ok:
        raise ValueError(f"tickets approval is not valid ({message}); approve the tickets first")
    errors = validate_tickets(run_dir)
    if errors:
        raise ValueError("ticket manifest is not valid:\n" + "\n".join(errors))

    site = str(jira.get("site") or "")
    project_key = str(jira.get("project_key") or "")
    if not site or _is_placeholder(site):
        raise ValueError("jira.site is missing or a placeholder; set the real Jira site in the config")
    if not project_key or _is_placeholder(project_key):
        raise ValueError("jira.project_key is missing or a placeholder; set the real project key in the config")
    if not site.startswith("https://"):
        raise ValueError("jira.site must start with https://")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    if client is None and not (email and token):
        raise ValueError("set the JIRA_EMAIL and JIRA_API_TOKEN environment variables before publishing")

    issue_types = dict(DEFAULT_ISSUE_TYPES)
    issue_types.update({str(k): str(v) for k, v in (jira.get("issue_types") or {}).items()})
    default_labels = [str(x) for x in (jira.get("default_labels") or [])]
    search_wait = jira.get("search_wait_seconds", DEFAULT_SEARCH_WAIT)
    if isinstance(search_wait, bool) or not isinstance(search_wait, (int, float)) or search_wait < 0:
        raise ValueError("jira.search_wait_seconds must be a number of seconds, 0 or more")

    manifest = _read_json(run_path / MANIFEST_NAME, "the ticket manifest")
    state = _read_json(run_path / STATE_NAME, STATE_NAME)
    state_schema = _read_json(REPO_ROOT / "schemas" / "state.schema.json", "the state schema")
    log_path = run_path / PUBLISHED_NAME
    log = _read_json(log_path, PUBLISHED_NAME) if log_path.exists() else []
    if not isinstance(log, list):
        raise ValueError(f"{PUBLISHED_NAME} must be a JSON list")
    state.setdefault("jira_keys", {})

    # Live branch only: the Jira client is imported here and nowhere else.
    from jira_client import JiraClient, JiraError, to_adf
    if client is None:
        try:
            client = JiraClient(
                site, email, token,
                min_interval=float(jira.get("min_request_interval_seconds", DEFAULT_MIN_INTERVAL)),
                max_retries=int(jira.get("max_retries", DEFAULT_MAX_RETRIES)),
            )
        except ValueError as e:
            raise ValueError(f"cannot build the Jira client: {e}")

    if sleep is None:
        sleep = getattr(client, "_sleep", time.sleep)

    entries = build_dryrun(manifest, project_key, default_labels)
    tickets: Dict[str, dict] = {}
    logical: Dict[str, str] = {}
    for epic in manifest["epics"]:
        tickets[epic["id"]] = epic
        logical[epic["id"]] = "Epic"
        for child in epic.get("children", []):
            tickets[child["id"]] = child
            logical[child["id"]] = child["type"]
    keys: Dict[str, str] = {tid: t["jira_key"] for tid, t in tickets.items() if t.get("jira_key")}
    base_url = site.rstrip("/")
    counts = {"created": 0, "updated": 0}

    def write_back(tid: str, key: str, action: str) -> None:
        tickets[tid]["jira_key"] = key
        keys[tid] = key
        state["jira_keys"][tid] = key
        log.append({"ticket_id": tid, "key": key, "action": action, "url": f"{base_url}/browse/{key}"})
        _write_json_atomic(run_path / MANIFEST_NAME, manifest)
        _write_json_atomic(run_path / STATE_NAME, state)
        _write_json_atomic(log_path, log)

    done = 0
    for entry in entries:
        tid = entry["ticket_id"]
        fields = _live_fields(entry, issue_types, logical[tid], lambda text: text)
        blocks = _blocks_section(tickets[tid], tickets, keys)
        if blocks:
            fields["description"] = fields["description"] + "\n\n" + blocks
        fields["description"] = to_adf(fields["description"])
        parent_id = entry["parent_ticket_id"]
        if parent_id:
            fields["parent"] = {"key": keys[parent_id]}
        try:
            key = keys.get(tid)
            label = entry["idempotency_label"]
            action = "updated"

            def find_one():
                found = client.search_by_label(project_key, label)
                if len(found) > 1:
                    raise PublishFailed(
                        f"duplicate idempotency label {label}: " + ", ".join(f["key"] for f in found)
                    )
                return found[0]["key"] if found else None

            if key is not None:
                if key.rsplit("-", 1)[0] != project_key:
                    raise PublishFailed(f"jira_key {key} for {tid} is not in project {project_key}")
                if find_one() != key:
                    raise PublishFailed(f"jira_key {key} for {tid} does not carry label {label}")
            else:
                key = find_one()
                if key is None:
                    action = "created"
                    try:
                        key = client.create_issue(fields)
                    except JiraError as e:
                        if e.status != 0 and e.status < 500:
                            raise
                        # The response may have been lost after Jira created the issue: wait for
                        # Jira's search index to catch up, then look first.
                        if search_wait > 0:
                            sleep(search_wait)
                        key = find_one()
                        if key is None:
                            key = client.create_issue(fields)
            if action == "updated":
                update = {k: v for k, v in fields.items() if k not in ("project", "issuetype")}
                client.update_issue(key, update)
        except JiraError as e:
            raise PublishFailed(
                f"FAILED at {tid}: {e}\n{done} published before the failure; rerun to resume"
            )
        except PublishFailed as e:
            raise PublishFailed(
                f"FAILED at {tid}: {e}\n{done} published before the failure; "
                "fix the jira_key in the manifest (or the duplicate in Jira), then rerun"
            )
        write_back(tid, key, action)
        counts[action] += 1
        done += 1
        print(f"{tid}: {action} {key}")

    state["stage"] = "done"
    errors = list(Draft202012Validator(state_schema).iter_errors(state))
    if errors:
        raise ValueError("state.json would be invalid after publishing; it was not marked done")
    _write_json_atomic(run_path / STATE_NAME, state)
    try:
        write_traceability(run_dir)
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"published, but cannot refresh traceability.md: {e}")
    print(f"PUBLISHED: {counts['created']} created, {counts['updated']} updated")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Jira publish: dry run by default, live with --publish.")
    parser.add_argument("run_dir", help="Run directory")
    parser.add_argument("--config", default=str(REPO_ROOT / "pm.config.yaml"), help="Config file")
    parser.add_argument("--publish", action="store_true",
                        help="Really publish to Jira (also needs jira.mode: publish)")
    args = parser.parse_args()
    if args.publish:
        try:
            publish(args.run_dir, args.config)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        except Exception as e:  # a transport bug must not print a traceback
            text = " ".join(f"{type(e).__name__}: {e}".split())
            print(f"FAILED unexpected error: {text}", file=sys.stderr)
            sys.exit(1)
        return
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
