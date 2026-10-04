"""Test M8 fixtures: reference PRDs for messy-transcript and contradictory-decisions."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from test_fixtures_prd import REPO_ROOT, build_run_dir, load_expected, run_script

FIXTURES = ["messy-transcript", "contradictory-decisions"]


def section(prd: str, number: int) -> str:
    match = re.search(rf"^## {number}\. .*?(?=^## \d+\. |\Z)", prd, re.S | re.M)
    assert match, f"section {number} not found"
    return match.group(0)


@pytest.mark.parametrize("name", FIXTURES)
def test_golden_prd_validates_and_audits(name: str, tmp_path: Path):
    expected = load_expected(name)
    run_dir = build_run_dir(name, tmp_path)

    result = run_script("validate_prd.py", run_dir)
    assert result.returncode == 0, f"validate_prd failed for {name}: {result.stdout}{result.stderr}"

    audit = json.loads((run_dir / "prd.audit.json").read_text())
    assert audit["run_id"] == expected["run_id"]
    assert audit["ai_feature"] is False
    assert audit["prd_hash"] == hashlib.sha256((run_dir / "prd.md").read_bytes()).hexdigest()

    result = run_script("render_audit.py", run_dir)
    assert result.stdout.strip() == expected["prd"]["verdict"]
    assert result.returncode == (1 if expected["prd"]["verdict"] == "FAIL" else 0)


@pytest.mark.parametrize("name", FIXTURES)
def test_golden_prd_has_no_addendum_and_states_no_providers(name: str):
    prd = (REPO_ROOT / "fixtures" / name / "golden" / "prd.md").read_text()
    assert "## A1. " not in prd
    assert "No data provider configured" in prd
    assert "No anecdote provider configured" in prd


def test_contradictory_decisions_keeps_disagreement_open():
    prd = (REPO_ROOT / "fixtures/contradictory-decisions/golden/prd.md").read_text()
    open_questions = section(prd, 17)
    assert open_questions.strip().splitlines()[1:], "open questions section is empty"
    assert "DIS-1" in open_questions
    assert "all plans or Enterprise only" in open_questions
    assert "Owner:" in open_questions
    decisions = section(prd, 19)
    assert "None. The extraction records no decisions" in decisions


def test_messy_transcript_lists_parked_problems():
    prd = (REPO_ROOT / "fixtures/messy-transcript/golden/prd.md").read_text()
    for parked in ("PB-2", "PB-3"):
        assert parked in prd
        assert parked in section(prd, 13)
    assert "PB-1" in section(prd, 3)
