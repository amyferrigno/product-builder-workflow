"""Test scripts/tickets_hash.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from tickets_hash import tickets_hash
from tickets_helpers import make_tickets_run, valid_manifest, write_manifest


def test_stable_across_calls(tmp_path):
    run = make_tickets_run(tmp_path)
    assert tickets_hash(run) == tickets_hash(run)
    assert len(tickets_hash(run)) == 64


@pytest.mark.parametrize("edit", [
    lambda m: m.update(prd_slug="other"),
    lambda m: m["epics"][0].update(summary="[Scheduling] Changed summary"),
    lambda m: m["epics"][0]["children"][0].update(priority="Low"),
    lambda m: m["epics"][0]["children"][0]["acceptance_criteria"].append("Given a, When b, Then c"),
])
def test_changes_when_a_field_changes(tmp_path, edit):
    run = make_tickets_run(tmp_path)
    before = tickets_hash(run)
    manifest = json.loads((run / "tickets.manifest.json").read_text())
    edit(manifest)
    write_manifest(run, manifest)
    assert tickets_hash(run) != before


def test_unchanged_when_only_jira_keys_change(tmp_path):
    run = make_tickets_run(tmp_path)
    before = tickets_hash(run)
    manifest = valid_manifest(run, ai=False)
    manifest["epics"][0]["jira_key"] = "PROJ-1"
    manifest["epics"][0]["children"][0]["jira_key"] = "PROJ-2"
    write_manifest(run, manifest)
    assert tickets_hash(run) == before


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(ValueError):
        tickets_hash(tmp_path)


def test_invalid_json_raises(tmp_path):
    (tmp_path / "tickets.manifest.json").write_text("{not json")
    with pytest.raises(ValueError):
        tickets_hash(tmp_path)


def test_cli_prints_hash_and_fails_cleanly(tmp_path):
    run = make_tickets_run(tmp_path)
    ok = subprocess.run([sys.executable, "scripts/tickets_hash.py", str(run)],
                        capture_output=True, text=True, cwd=REPO_ROOT)
    assert ok.returncode == 0 and ok.stdout.strip() == tickets_hash(run)
    bad = subprocess.run([sys.executable, "scripts/tickets_hash.py", str(tmp_path / "none")],
                         capture_output=True, text=True, cwd=REPO_ROOT)
    assert bad.returncode == 1 and "Traceback" not in bad.stderr
