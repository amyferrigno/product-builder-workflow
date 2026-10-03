"""Test scripts/preview_tickets.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from preview_tickets import write_preview
from tickets_helpers import make_tickets_run, write_manifest


@pytest.mark.parametrize("ai", [False, True])
def test_preview_written_with_all_sections(tmp_path, ai):
    run = make_tickets_run(tmp_path, ai=ai)
    path = write_preview(run)
    assert path == run / "tickets.preview.md"
    text = path.read_text()
    manifest = json.loads((run / "tickets.manifest.json").read_text())
    ids = [e["id"] for e in manifest["epics"]]
    ids += [c["id"] for e in manifest["epics"] for c in e["children"]]
    for ticket_id in ids:
        assert ticket_id in text
    assert f"Total tickets: {len(ids)}" in text
    assert "Epic: 2" in text and "Spike: 1" in text
    assert "## Must coverage" in text and "REQ-001" in text
    assert "NOT COVERED" not in text
    assert "PASS: no errors" in text


def test_preview_lists_validator_errors(tmp_path):
    run = make_tickets_run(tmp_path)
    manifest = json.loads((run / "tickets.manifest.json").read_text())
    manifest["epics"][0]["children"][0]["acceptance_criteria"].pop()
    write_manifest(run, manifest)
    text = write_preview(run).read_text()
    assert "FAIL" in text
    assert "T-001: story needs at least 3 acceptance criteria" in text
    assert "NOT COVERED" not in text


def test_cli_missing_manifest_exits_1(tmp_path):
    result = subprocess.run([sys.executable, "scripts/preview_tickets.py", str(tmp_path)],
                            capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 1 and "Traceback" not in result.stderr


def test_cli_writes_file(tmp_path):
    run = make_tickets_run(tmp_path)
    result = subprocess.run([sys.executable, "scripts/preview_tickets.py", str(run)],
                            capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0
    assert (run / "tickets.preview.md").is_file()
