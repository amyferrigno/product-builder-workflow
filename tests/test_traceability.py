"""Test scripts/traceability.py."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from traceability import build_traceability, write_traceability
from validate_prd import parse_requirements
from ux_helpers import make_ux_run

REPO_ROOT = Path(__file__).parent.parent


def test_lists_every_req_with_priority_and_screens(tmp_path):
    run = make_ux_run(tmp_path)
    prd = (run / "prd.md").read_text()
    text = build_traceability(run)
    assert "| REQ | Priority | Screens | Jira |" in text
    for req_id, priority in parse_requirements(prd):
        assert f"| {req_id} | {priority} |" in text
    assert "| REQ-001 | Must | SCR-001, SCR-002 | not yet created (Stage 3) |" in text
    assert "| REQ-002 | Must | SCR-001 | not yet created (Stage 3) |" in text


def test_req_with_no_screen_shows_dash(tmp_path):
    run = make_ux_run(tmp_path)
    spec = run / "ux" / "spec.md"
    spec.write_text(spec.read_text().replace("REQ-002, ", "").replace(", REQ-002", ""))
    assert "| REQ-002 | Must | - | not yet created (Stage 3) |" in build_traceability(run)


def test_write_and_cli(tmp_path):
    run = make_ux_run(tmp_path)
    path = write_traceability(run)
    assert path == run / "traceability.md"
    assert path.read_text() == build_traceability(run)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "traceability.py"), str(run)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_missing_spec_is_clean_error(tmp_path):
    run = make_ux_run(tmp_path)
    (run / "ux" / "spec.md").unlink()
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "traceability.py"), str(run)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
