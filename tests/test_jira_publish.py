"""Test scripts/jira_publish.py (dry run only)."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from tickets_helpers import make_tickets_run  # noqa: E402
from ux_gate_helpers import write_state  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent


def approved_run(tmp_path, ai=False):
    run = make_tickets_run(tmp_path, ai=ai)
    write_state(run)
    result = subprocess.run(
        [sys.executable, "scripts/approve.py", str(run), "tickets",
         "--decisions-file", str(run / "decisions.test.md")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    return run


def write_config(tmp_path, mode="dry_run", project_key="PROJ", labels=("agentic-pm", "extra")):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"jira": {"mode": mode, "project_key": project_key,
                                             "default_labels": list(labels)}}))
    return path


def publish(run, config):
    return subprocess.run(
        [sys.executable, "scripts/jira_publish.py", str(run), "--config", str(config)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def test_refuses_without_approval(tmp_path):
    run = make_tickets_run(tmp_path)
    result = publish(run, write_config(tmp_path))
    assert result.returncode == 1
    assert "approval is not valid" in result.stderr
    assert not (run / "tickets.dryrun.json").exists()


def test_refuses_when_approval_stale(tmp_path):
    run = approved_run(tmp_path)
    m = json.loads((run / "tickets.manifest.json").read_text())
    m["epics"][0]["children"][0]["priority"] = "Low"
    (run / "tickets.manifest.json").write_text(json.dumps(m))
    result = publish(run, write_config(tmp_path))
    assert result.returncode == 1
    assert "stale" in result.stderr
    assert not (run / "tickets.dryrun.json").exists()


def test_refuses_when_mode_is_not_dry_run(tmp_path):
    run = approved_run(tmp_path)
    result = publish(run, write_config(tmp_path, mode="live"))
    assert result.returncode == 1
    assert "live publish is not available until M7" in result.stderr
    assert not (run / "tickets.dryrun.json").exists()


def test_writes_dryrun_payloads(tmp_path):
    run = approved_run(tmp_path, ai=True)
    result = publish(run, write_config(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "DRY RUN: nothing was sent to Jira" in result.stdout
    entries = json.loads((run / "tickets.dryrun.json").read_text())
    manifest = json.loads((run / "tickets.manifest.json").read_text())
    epics = manifest["epics"]
    children = [c for e in epics for c in e["children"]]
    assert len(entries) == len(epics) + len(children)
    kinds = [e["payload"]["fields"]["issuetype"]["name"] for e in entries]
    assert kinds[:len(epics)] == ["Epic"] * len(epics)
    assert "Epic" not in kinds[len(epics):]
    assert set(kinds) <= {"Epic", "Story", "Task", "Spike"}
    parent_of = {c["id"]: e["id"] for e in epics for c in e["children"]}
    by_id = {t["id"]: t for t in epics + children}
    for entry in entries:
        ticket = by_id[entry["ticket_id"]]
        fields = entry["payload"]["fields"]
        assert entry["action"] == "create"
        assert entry["idempotency_label"] in ticket["labels"]
        assert entry["idempotency_label"].startswith("ext-")
        assert entry["parent_ticket_id"] == parent_of.get(entry["ticket_id"])
        assert fields["project"] == {"key": "PROJ"}
        assert len(fields["labels"]) == len(set(fields["labels"]))
        assert "agentic-pm" in fields["labels"] and "extra" in fields["labels"]
        assert set(ticket["labels"]) <= set(fields["labels"])
        assert fields["priority"]["name"] == ticket.get("priority", "Medium")
        assert fields["issuetype"]["name"] == ticket.get("type", "Epic")
    story = next(e for e in entries if e["payload"]["fields"]["issuetype"]["name"] == "Story")
    description = story["payload"]["fields"]["description"]
    assert "Acceptance criteria:" in description and "AI quality criteria:" in description
    flat = json.dumps(entries).lower()
    assert "story_point" not in flat and "story point" not in flat and "storypoint" not in flat


def test_idempotency_label_is_distinct_and_computed_from_id(tmp_path):
    run = approved_run(tmp_path)
    assert publish(run, write_config(tmp_path)).returncode == 0
    entries = json.loads((run / "tickets.dryrun.json").read_text())
    slug = json.loads((run / "tickets.manifest.json").read_text())["prd_slug"]
    for entry in entries:
        assert entry["idempotency_label"] == f"ext-{slug}-{entry['ticket_id'].lower()}"
    labels = [e["idempotency_label"] for e in entries]
    assert len(labels) == len(set(labels))


def test_refuses_invalid_manifest_even_if_approval_passes(tmp_path, monkeypatch, capsys):
    run = make_tickets_run(tmp_path)
    m = json.loads((run / "tickets.manifest.json").read_text())
    m["epics"][0]["children"][0]["description"] = "Too short"
    (run / "tickets.manifest.json").write_text(json.dumps(m))
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import jira_publish

    monkeypatch.setattr(jira_publish, "approval_status", lambda run_dir, kind: (True, "ok"))
    monkeypatch.setattr(sys, "argv", ["jira_publish.py", str(run), "--config", str(write_config(tmp_path))])
    with pytest.raises(SystemExit) as exc:
        jira_publish.main()
    assert exc.value.code == 1
    assert "T-001" in capsys.readouterr().err
    assert not (run / "tickets.dryrun.json").exists()


def test_no_key_names_story_points(tmp_path):
    run = approved_run(tmp_path)
    publish(run, write_config(tmp_path))

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for item in node:
                yield from keys(item)

    for key in keys(json.loads((run / "tickets.dryrun.json").read_text())):
        assert not ("story" in key.lower() and "point" in key.lower())


def test_placeholder_project_key_warns_and_is_kept(tmp_path):
    run = approved_run(tmp_path)
    result = publish(run, write_config(tmp_path, project_key="[[KEY]]"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("project key is a placeholder") == 1
    entries = json.loads((run / "tickets.dryrun.json").read_text())
    assert entries[0]["payload"]["fields"]["project"]["key"] == "[[KEY]]"


def test_running_twice_is_byte_identical(tmp_path):
    run = approved_run(tmp_path)
    config = write_config(tmp_path)
    publish(run, config)
    first = (run / "tickets.dryrun.json").read_bytes()
    publish(run, config)
    assert (run / "tickets.dryrun.json").read_bytes() == first


def test_module_imports_no_network_library():
    tree = ast.parse((REPO_ROOT / "scripts" / "jira_publish.py").read_text())
    banned = {"urllib", "http", "socket", "requests", "subprocess"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "__import__":
            found.add("__import__")
    assert not (found & banned)
    assert "__import__" not in found
