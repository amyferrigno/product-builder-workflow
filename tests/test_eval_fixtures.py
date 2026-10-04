"""Tests for scripts/eval_fixtures.py: every fixture evaluates OK, and broken goldens are caught."""
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import eval_fixtures

FIXTURE_NAMES = {
    "clean-meeting", "messy-transcript", "solution-first-chatbot", "contradictory-decisions",
    "thin-evidence", "ai-clear-fit", "clean-meeting-evidence",
}


def expected_decision(name: str) -> str:
    return yaml.safe_load((REPO / "fixtures" / name / "expected.yaml").read_text())["decision"]


@pytest.fixture
def fixtures_copy(tmp_path):
    copy = tmp_path / "fixtures"
    shutil.copytree(REPO / "fixtures", copy)
    return copy


def run_eval(fixtures_dir, capsys, *extra):
    code = eval_fixtures.main(["--fixtures-dir", str(fixtures_dir), *extra])
    return code, capsys.readouterr().out


def test_all_fixtures_ok(capsys):
    code, out = run_eval(REPO / "fixtures", capsys)
    assert code == 0, out
    assert out.strip().splitlines()[-1] == "EVAL: 7 fixtures, 0 failed"


def test_rows_have_expected_decision_and_all_seven_fixtures():
    rows = eval_fixtures.evaluate(REPO / "fixtures")
    assert {r["name"] for r in rows} == FIXTURE_NAMES
    for row in rows:
        assert row["ok"], row
        assert row["decision"] == expected_decision(row["name"])
        assert row["validators_passed"] == row["validators_total"] > 0
    by_name = {r["name"]: r for r in rows}
    assert by_name["solution-first-chatbot"]["decision"] == "MEMO"
    assert by_name["thin-evidence"]["decision"] == "MEMO"
    assert by_name["thin-evidence"]["prd_verdict"] == "FAIL"
    assert by_name["ai-clear-fit"]["ux_verdict"] == "PASS"
    assert by_name["ai-clear-fit"]["tickets"] == 14


def test_json_mode_parses(capsys):
    code, out = run_eval(REPO / "fixtures", capsys, "--json")
    assert code == 0
    rows = json.loads(out)
    assert len(rows) == 7
    assert all(r["ok"] for r in rows)
    assert {"name", "decision", "prd_verdict", "ux_verdict", "tickets", "errors"} <= set(rows[0])


def assert_fails_naming(fixtures_dir, capsys, name):
    code, out = run_eval(fixtures_dir, capsys)
    assert code == 1
    assert "Traceback" not in out
    assert out.strip().splitlines()[-1] == "EVAL: 7 fixtures, 1 failed"
    row = next(line for line in out.splitlines() if line.startswith(name))
    assert row.rstrip().endswith("FAIL")


def test_missing_required_heading_fails(fixtures_copy, capsys):
    prd = fixtures_copy / "clean-meeting" / "golden" / "prd.md"
    lines = [ln for ln in prd.read_text().splitlines(keepends=True) if not ln.startswith("## 7. ")]
    prd.write_text("".join(lines))
    assert_fails_naming(fixtures_copy, capsys, "clean-meeting ")


def test_changed_expected_verdict_fails(fixtures_copy, capsys):
    path = fixtures_copy / "messy-transcript" / "expected.yaml"
    path.write_text(path.read_text().replace('verdict: "PASS_WITH_RISK"', 'verdict: "PASS"'))
    assert_fails_naming(fixtures_copy, capsys, "messy-transcript")


def test_corrupt_golden_json_fails(fixtures_copy, capsys):
    (fixtures_copy / "thin-evidence" / "golden" / "01-extraction.json").write_text("{not json")
    assert_fails_naming(fixtures_copy, capsys, "thin-evidence")


def snapshot_runs():
    runs = REPO / "runs"
    return sorted((str(p.relative_to(runs)), p.stat().st_mtime_ns, p.stat().st_size) for p in runs.rglob("*"))


def test_eval_leaves_repo_runs_untouched(capsys):
    before = snapshot_runs()
    active = REPO / "runs" / ".active"
    active_before = active.read_bytes() if active.exists() else None
    code, _ = run_eval(REPO / "fixtures", capsys)
    assert code == 0
    assert snapshot_runs() == before
    assert (active.read_bytes() if active.exists() else None) == active_before
