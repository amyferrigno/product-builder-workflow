"""PRD fixtures: golden PRDs validate, audit to the expected verdict, and bad-prd is rejected."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent

FIXTURES = ["clean-meeting", "thin-evidence", "ai-clear-fit"]


def load_expected(name: str) -> dict:
    with open(REPO_ROOT / "fixtures" / name / "expected.yaml") as f:
        return yaml.safe_load(f)


def run_script(script: str, run_dir) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, f"scripts/{script}", str(run_dir)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def build_run_dir(name: str, tmp_path: Path) -> Path:
    """Run intake for the fixture and copy every golden file into the run dir."""
    expected = load_expected(name)
    result = subprocess.run(
        [
            sys.executable, "scripts/intake.py",
            str(REPO_ROOT / "fixtures" / name / "notes.md"),
            "--slug", name,
            "--runs-dir", str(tmp_path),
            "--date", expected["run_id"][:10],
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    run_dir = Path(json.loads(result.stdout)["run_dir"])
    for golden in (REPO_ROOT / "fixtures" / name / "golden").iterdir():
        if golden.is_file():
            shutil.copy(golden, run_dir / golden.name)
    return run_dir


@pytest.mark.parametrize("name", FIXTURES)
def test_golden_prd_validates_and_audits(name: str, tmp_path: Path):
    expected = load_expected(name)
    run_dir = build_run_dir(name, tmp_path)

    for script in ("validate_extraction.py", "validate_problem.py", "validate_prd.py"):
        result = run_script(script, run_dir)
        assert result.returncode == 0, f"{script} failed for {name}: {result.stdout}{result.stderr}"

    audit = json.loads((run_dir / "prd.audit.json").read_text())
    assert audit["run_id"] == expected["run_id"]
    assert audit["prd_hash"] == hashlib.sha256((run_dir / "prd.md").read_bytes()).hexdigest()

    result = run_script("render_audit.py", run_dir)
    assert result.stdout.strip() == expected["prd"]["verdict"]
    expected_code = 1 if expected["prd"]["verdict"] == "FAIL" else 0
    assert result.returncode == expected_code

    audit_md = (run_dir / "prd.audit.md").read_text()
    assert audit_md.startswith(f"# PRD Audit: {expected['prd']['verdict']}")
    state = json.loads((run_dir / "state.json").read_text())
    assert state["verdicts"]["prd"] == expected["prd"]["verdict"]


def test_expected_verdicts():
    # Without provider data evidence strength is capped at 2, so notes-only PRDs
    # get at best PASS_WITH_RISK.
    assert load_expected("clean-meeting")["prd"]["verdict"] == "PASS_WITH_RISK"
    assert load_expected("ai-clear-fit")["prd"]["verdict"] == "PASS_WITH_RISK"
    assert load_expected("thin-evidence")["prd"]["verdict"] == "FAIL"


def test_ai_fixture_has_ai_dimensions_and_addendum():
    audit = json.loads((REPO_ROOT / "fixtures/ai-clear-fit/golden/prd.audit.json").read_text())
    ids = {d["id"] for d in audit["dimensions"]}
    assert audit["ai_feature"] is True
    assert {"ai_appropriateness", "ai_ux_uncertainty", "ai_eval_plan"} <= ids
    prd = (REPO_ROOT / "fixtures/ai-clear-fit/golden/prd.md").read_text()
    for n in range(1, 11):
        assert f"## A{n}. " in prd


def test_clean_meeting_has_no_addendum():
    prd = (REPO_ROOT / "fixtures/clean-meeting/golden/prd.md").read_text()
    assert "## A1. " not in prd


def test_thin_evidence_scores_and_gaps():
    audit = json.loads((REPO_ROOT / "fixtures/thin-evidence/golden/prd.audit.json").read_text())
    scores = {d["id"]: d for d in audit["dimensions"]}
    assert scores["evidence_strength"]["score"] == 2
    assert scores["evidence_strength"]["fix"]
    assert scores["problem_clarity"]["score"] == 2
    prd = (REPO_ROOT / "fixtures/thin-evidence/golden/prd.md").read_text()
    assert "No data provider configured" in prd
    assert "### 6c. Evidence gaps" in prd


def test_bad_prd_names_number_and_requirement():
    result = run_script("validate_prd.py", REPO_ROOT / "fixtures" / "bad-prd")
    assert result.returncode == 1
    lines = result.stdout.strip().splitlines()
    assert "Unsupported number '9137' in section 3" in lines
    assert "Requirement REQ-003: acceptance criteria missing: Given, When, Then" in lines
    assert len(lines) == 2


def test_edited_golden_prd_gives_fail_for_stale_hash(tmp_path: Path):
    run_dir = build_run_dir("clean-meeting", tmp_path)
    with open(run_dir / "prd.md", "a") as f:
        f.write("\nAn extra line added after the audit.\n")
    result = run_script("render_audit.py", run_dir)
    assert result.returncode == 1
    assert result.stdout.strip() == "FAIL"
    assert "PRD hash mismatch" in (run_dir / "prd.audit.md").read_text()
