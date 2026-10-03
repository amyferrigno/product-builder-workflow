"""Test scripts/validate_evidence.py."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from validate_evidence import render_claim, format_value, format_value_pct, claim_number_errors

REPO_ROOT = Path(__file__).parent.parent
SHARE_HASH = hashlib.sha256(
    (REPO_ROOT / "connectors" / "queries" / "ticket_share_by_category.sql").read_text().encode("utf-8")
).hexdigest()


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
        "query_hash": SHARE_HASH,
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


def test_hand_written_card_with_fake_query_hash_fails(tmp_path):
    card = good_card("EV-050", value=0.87, n=12000, claim="87% of 12000 tickets", query_hash="0" * 64)
    run_dir = make_run(tmp_path, {"EV-050.json": card})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert "EV-050.json: query_hash does not match the library query" in lines


def test_source_must_match_query_provider(tmp_path):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(source="somewhere_else")})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert "EV-001.json: source somewhere_else does not match the query provider" in lines


@pytest.mark.parametrize("claim", [
    "0 tickets",
    "0.3 of tickets",
    "0.33% of tickets",
    "300% of tickets",
    "33k tickets",
    "33% of 300 million tickets",
    "33 million tickets",
    "33 percent of 300 thousand tickets",
])
def test_bad_claims_are_refused(tmp_path, claim):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(claim=claim, n=300)})
    code, lines, _ = validate(run_dir)
    assert code == 1
    assert any(line.startswith("EV-001.json: claim number ") for line in lines)


@pytest.mark.parametrize("claim", [
    "33% of 300 tickets",
    "33 percent of 300 tickets",
    "0.33 of tickets, n 300",
    "300 tickets",
])
def test_good_claim_forms_pass(tmp_path, claim):
    run_dir = make_run(tmp_path, {"EV-001.json": good_card(claim=claim, n=300)})
    code, lines, _ = validate(run_dir)
    assert code == 0, lines


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


def test_format_helpers():
    assert format_value(12) == "12"
    assert format_value(12.0) == "12"
    assert format_value(0.3333) == "0.33"
    assert format_value(0.5) == "0.5"
    assert format_value(74.0) == "74"
    assert format_value_pct(0.333) == "33.3"
    assert format_value_pct(0.5) == "50"
    assert format_value_pct(1) == "100"
    with pytest.raises(ValueError):
        format_value_pct(1.5)


def test_render_claim_fills_placeholders():
    assert render_claim("{value_pct}% of {n} tickets", 0.3333, 300) == "33.3% of 300 tickets"
    assert render_claim("median is {value} minutes over {n} meetings", 74.0, 142) == \
        "median is 74 minutes over 142 meetings"
    assert render_claim("{value_pct} percent of tickets", 0.5, 10) == "50 percent of tickets"
    assert claim_number_errors(render_claim("{value_pct}% of {n} tickets", 0.3333, 300), 0.3333, 300) == []


@pytest.mark.parametrize("template,message", [
    ("3 tickets {value}", "claim template must not contain literal numbers; use {value}, {value_pct} or {n}"),
    ("tickets {n}", "claim template must contain {value} or {value_pct}"),
    ("{value} {other}", "unknown placeholder '{other}' in claim template"),
    ("{value}k tickets", "claim template must not put a magnitude word (k, m, bn, thousand, million, billion) after a number"),
    ("{n} Million {value}", "claim template must not put a magnitude word (k, m, bn, thousand, million, billion) after a number"),
    ("{value}% of tickets", "% may follow only {value_pct}"),
    ("{value_pct} of tickets", "{value_pct} must be followed directly by % or the word percent"),
])
def test_render_claim_refuses_bad_templates(template, message):
    with pytest.raises(ValueError) as exc:
        render_claim(template, 0.5, 10)
    assert str(exc.value) == message


def test_value_pct_refused_outside_zero_to_one():
    with pytest.raises(ValueError, match="between 0 and 1"):
        render_claim("{value_pct}% of tickets", 74.0, 10)


def test_meetings_word_is_not_a_magnitude_word():
    assert render_claim("{value} minutes across {n} meetings", 74.0, 10) == "74 minutes across 10 meetings"
