"""Tests for scripts/prd_decision.py: PRD or no-PRD memo."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from prd_decision import decide  # noqa: E402

FIXTURES = REPO_ROOT / "fixtures"
EXPECTED = {
    "solution-first-chatbot": "MEMO",
    "thin-evidence": "MEMO",
    "clean-meeting": "PRD",
    "ai-clear-fit": "PRD",
    "messy-transcript": "PRD",
    "contradictory-decisions": "PRD",
}


def make_run(tmp_path: Path, fixture: str, with_state: bool = True) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    shutil.copy(FIXTURES / fixture / "golden" / "02-problem.md", run / "02-problem.md")
    if with_state:
        state = {
            "run_id": "run-1", "stage": "stage1", "status": "in_progress",
            "verdicts": {"prd": None, "ux": None}, "artifact_hashes": {},
            "approval_hashes": {"prd": None, "ux": None, "tickets": None},
            "jira_keys": {}, "updated_at": "2026-01-15T00:00:00Z",
        }
        (run / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return run


def cli(run: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/prd_decision.py", str(run), *extra],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def state_of(run: Path) -> dict:
    return json.loads((run / "state.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture,expected", sorted(EXPECTED.items()))
def test_original_fixtures(tmp_path, fixture, expected):
    run = make_run(tmp_path, fixture)
    decision, reasons = decide(run)
    assert decision == expected
    assert reasons and all(r.endswith(".") for r in reasons)
    result = cli(run)
    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == expected
    assert state_of(run)["outcome"] == ("no_prd_memo" if expected == "MEMO" else "prd")


def test_unvalidated_without_support_is_memo(tmp_path):
    run = make_run(tmp_path, "thin-evidence")
    decision, reasons = decide(run)
    assert decision == "MEMO"
    assert any("UNVALIDATED" in r for r in reasons)


def test_evidence_card_supports_problem(tmp_path):
    run = make_run(tmp_path, "thin-evidence")
    (run / "03-evidence").mkdir()
    card = {"id": "EV-001", "supports_problem": "PB-1"}
    (run / "03-evidence" / "EV-001.json").write_text(json.dumps(card), encoding="utf-8")
    assert decide(run)[0] == "PRD"


def test_evidence_card_for_other_problem_does_not_count(tmp_path):
    run = make_run(tmp_path, "thin-evidence")
    (run / "03-evidence").mkdir()
    card = {"id": "EV-001", "supports_problem": "PB-9"}
    (run / "03-evidence" / "EV-001.json").write_text(json.dumps(card), encoding="utf-8")
    assert decide(run)[0] == "MEMO"


def test_anecdote_supports_problem(tmp_path):
    run = make_run(tmp_path, "thin-evidence")
    (run / "04-anecdotes.json").write_text(json.dumps([{"id": "AN-001", "linked_problem": "PB-1"}]), encoding="utf-8")
    assert decide(run)[0] == "PRD"


def test_validated_problem_is_prd(tmp_path):
    run = make_run(tmp_path, "clean-meeting")
    decision, reasons = decide(run)
    assert decision == "PRD"
    assert "VALIDATED" in reasons[0] or "supported" in reasons[0]


def test_force_records_reason(tmp_path):
    run = make_run(tmp_path, "thin-evidence")
    result = cli(run, "--force-prd", "Sponsor needs a PRD for planning")
    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == "PRD"
    state = state_of(run)
    assert state["outcome"] == "prd"
    assert state["forced_prd_reason"] == "Sponsor needs a PRD for planning"


def test_force_with_empty_reason_refused(tmp_path):
    run = make_run(tmp_path, "thin-evidence")
    for reason in ("", "   "):
        result = cli(run, "--force-prd", reason)
        assert result.returncode == 1
        assert "outcome" not in state_of(run)


def test_missing_problem_file_exits_1_one_line(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    result = cli(run)
    assert result.returncode == 1
    assert len(result.stderr.strip().splitlines()) == 1
    assert "Traceback" not in result.stderr


def test_missing_state_is_tolerated(tmp_path):
    run = make_run(tmp_path, "thin-evidence", with_state=False)
    result = cli(run)
    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == "MEMO"
    assert not (run / "state.json").exists()
