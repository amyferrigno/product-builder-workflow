"""Test scripts/validate_evidence.py."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def good_card(card_id="EV-001", **overrides):
    card = {
        "id": card_id,
        "claim": "33% of 300 tickets are scheduling conflicts",
        "metric": "ticket_share",
        "value": 0.33,
        "segment": "all",
        "period": "2025-H2",
        "n": 300,
        "source": "mock_warehouse",
        "query_id": "ticket_share_by_category",
        "query_hash": "a" * 64,
        "run_at": "2026-01-01T00:00:00+00:00",
        "confidence": "high",
        "caveats": [],
        "supports_problem": "PB-1",
    }
    card.update(overrides)
    return card


def make_run(tmp_path, cards):
    """cards: dict of file name -> card dict."""
    run_dir = tmp_path / "runs" / "2026-01-15-clean-meeting"
    (run_dir / "03-evidence").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "fixtures" / "clean-meeting" / "golden" / "02-problem.md", run_dir / "02-problem.md")
    for name, card in cards.items():
        (run_dir / "03-evidence" / name).write_text(json.dumps(card))
    return run_dir


def validate(run_dir, *extra):
    result = subprocess.run(
        [sys.executable, "scripts/validate_evidence.py", str(run_dir), *extra],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return result.returncode, result.stdout.splitlines(), result.stderr


def test_good_run_passes(tmp_path):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(), "EV-002.json": good_card("EV-002", claim="300 tickets")})
    code, lines, stderr = validate(run_dir)
    assert code == 0, lines
    assert lines == []
    assert "Traceback" not in stderr


def test_duplicate_id_fails(tmp_path):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(), "EV-002.json": good_card("EV-001")})
    code, lines, stderr = validate(run_dir)
    assert code == 1
    assert "EV-002.json: duplicate id EV-001 (also in EV-001.json)" in lines
    assert "Traceback" not in stderr


def test_file_name_must_match_id(tmp_path):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card("EV-005")})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert "EV-001.json: file name does not match id EV-005" in lines


def test_unknown_problem_fails(tmp_path):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(supports_problem="PB-9")})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert "EV-001.json: unknown problem PB-9 (not in 02-problem.md)" in lines


def test_unknown_query_id_fails(tmp_path):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(query_id="made_up_query")})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert "EV-001.json: unknown query id made_up_query" in lines


def test_confidence_mismatch_fails(tmp_path):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(confidence="low")})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert ("EV-001.json: confidence low does not match query status reviewed (expected high)") in lines


def test_unreviewed_query_requires_low_confidence(tmp_path):
    queries = tmp_path / "queries"
    shutil.copytree(REPO_ROOT / "connectors" / "queries", queries)
    index = (queries / "index.yaml").read_text().replace("status: reviewed", "status: unreviewed", 1)
    (queries / "index.yaml").write_text(index)
    run_dir = make_run(tmp_path, {"EV-001.json": good_card()})
    code, lines, _ = validate(run_dir, "--queries-dir", str(queries))
    assert code == 1
    assert "EV-001.json: confidence high does not match query status unreviewed (expected low)" in lines


def test_claim_number_not_matching_fails(tmp_path):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(claim="45% of tickets")})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert "EV-001.json: claim number '45' does not match provider value" in lines


def test_schema_violation_is_reported(tmp_path):
    card = good_card()
    del card["n"]
    run_dir = make_run(tmp_path, {"EV-001.json": card})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert any(line.startswith("EV-001.json: card: ") and "'n' is a required property" in line for line in lines)


def test_invalid_json_card_is_reported(tmp_path):
    run_dir = make_run(tmp_path, {})
    (run_dir / "03-evidence" / "EV-001.json").write_text("{not json")
    code, lines, stderr = validate(run_dir)
    assert code == 1
    assert lines[0].startswith("EV-001.json: invalid JSON:")
    assert "Traceback" not in stderr


def test_no_cards_fails(tmp_path):
    run_dir = make_run(tmp_path, {})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert lines == ["no evidence cards found in 03-evidence"]


def test_missing_evidence_dir_fails(tmp_path):
    run_dir = make_run(tmp_path, {})
    shutil.rmtree(run_dir / "03-evidence")
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert lines == ["03-evidence directory not found"]


def test_missing_run_dir_fails(tmp_path):
    code, lines, stderr = validate(tmp_path / "nope")
    assert code == 1
    assert lines == [f"Run directory not found: {tmp_path / 'nope'}"]
    assert "Traceback" not in stderr
