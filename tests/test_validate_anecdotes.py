"""Test scripts/validate_anecdotes.py."""

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MOCK_REGISTRY = str(REPO_ROOT / "fixtures" / "registry.mock.yaml")
MOCK_CONFIG = str(REPO_ROOT / "fixtures" / "pm.config.mock.yaml")


def make_run(tmp_path):
    result = subprocess.run(
        [
            sys.executable, "scripts/intake.py",
            str(REPO_ROOT / "fixtures" / "clean-meeting" / "notes.md"),
            "--slug", "clean-meeting", "--runs-dir", str(tmp_path), "--date", "2026-01-15",
        ],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    run_dir = Path(json.loads(result.stdout)["run_dir"])
    shutil.copy(REPO_ROOT / "fixtures" / "clean-meeting" / "golden" / "02-problem.md", run_dir / "02-problem.md")
    return run_dir


def make_pulled_run(tmp_path):
    """A run with real candidates from the mock anecdote provider."""
    run_dir = make_run(tmp_path)
    result = subprocess.run(
        [
            sys.executable, "scripts/anecdotes.py", "pull", str(run_dir),
            "--provider", "mock_anecdotes", "--problem", "PB-1", "--keywords", "scheduling",
            "--registry", MOCK_REGISTRY, "--config", MOCK_CONFIG, "--cache-dir", str(tmp_path / "cache"),
        ],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    return run_dir


def read_candidates(run_dir):
    return json.loads((run_dir / "04-anecdotes.candidates.json").read_text())


def write_curated(run_dir, records):
    (run_dir / "04-anecdotes.json").write_text(json.dumps(records, indent=2))


def validate(run_dir):
    result = subprocess.run(
        [sys.executable, "scripts/validate_anecdotes.py", str(run_dir), "--config", MOCK_CONFIG],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert "Traceback" not in result.stderr
    return result.returncode, result.stdout.strip().splitlines()


def pick(candidates, count=3):
    """Positive records first, then negatives, so a counter-anecdote is always included."""
    positive = [c for c in candidates if c["sentiment"] > 0]
    negative = [c for c in candidates if c["sentiment"] <= 0]
    return copy.deepcopy((positive[:1] + negative)[:count])


def valid_run(tmp_path, count=3):
    run_dir = make_pulled_run(tmp_path)
    write_curated(run_dir, pick(read_candidates(run_dir), count))
    return run_dir


def hand_run(tmp_path, candidates):
    run_dir = make_run(tmp_path)
    (run_dir / "04-anecdotes.candidates.json").write_text(json.dumps(candidates))
    return run_dir


def record(n, **overrides):
    rec = {
        "id": f"AN-{n:03d}", "source": "zendesk", "source_ref": f"ticket/{n}", "date": "2026-06-01",
        "segment": "SMB", "persona": "Owner", "pain": "Scheduling is slow",
        "quote": "Scheduling takes too long.", "sentiment": -1, "linked_problem": "PB-1",
        "frequency_hint": None, "consent_ok": True,
    }
    rec.update(overrides)
    return rec


def test_valid_curated_file_passes(tmp_path):
    run_dir = valid_run(tmp_path)
    assert any(r["sentiment"] > 0 for r in read_candidates(run_dir))
    code, lines = validate(run_dir)
    assert (code, lines) == (0, [])


def test_five_records_pass(tmp_path):
    code, lines = validate(valid_run(tmp_path, 5))
    assert (code, lines) == (0, [])


def test_edited_quote_fails(tmp_path):
    run_dir = valid_run(tmp_path)
    curated = json.loads((run_dir / "04-anecdotes.json").read_text())
    curated[1]["quote"] = "A better sounding quote."
    write_curated(run_dir, curated)
    code, lines = validate(run_dir)
    assert code == 1
    assert f"{curated[1]['id']}: field 'quote' differs from the candidate" in lines


def test_edited_pain_fails(tmp_path):
    run_dir = valid_run(tmp_path)
    curated = json.loads((run_dir / "04-anecdotes.json").read_text())
    curated[0]["pain"] = "Reworded pain"
    write_curated(run_dir, curated)
    code, lines = validate(run_dir)
    assert code == 1
    assert f"{curated[0]['id']}: field 'pain' differs from the candidate" in lines


def test_six_records_fail(tmp_path):
    run_dir = make_pulled_run(tmp_path)
    candidates = read_candidates(run_dir)
    assert len(candidates) >= 6
    write_curated(run_dir, pick(candidates, 6))
    code, lines = validate(run_dir)
    assert code == 1
    assert "too many anecdotes: 6 (maximum 5)" in lines


def test_two_records_fail_when_five_candidates_exist(tmp_path):
    candidates = [record(1), record(2), record(3), record(4), record(5, sentiment=1)]
    run_dir = hand_run(tmp_path, candidates)
    write_curated(run_dir, [candidates[4], candidates[0]])
    code, lines = validate(run_dir)
    assert code == 1
    assert "too few anecdotes: 2 (need at least 3, 5 candidates exist)" in lines


def test_fewer_than_three_allowed_when_fewer_candidates(tmp_path):
    candidates = [record(1), record(2, sentiment=1)]
    run_dir = hand_run(tmp_path, candidates)
    write_curated(run_dir, candidates)
    assert validate(run_dir) == (0, [])


def test_empty_candidates_and_empty_curated_pass(tmp_path):
    run_dir = hand_run(tmp_path, [])
    write_curated(run_dir, [])
    assert validate(run_dir) == (0, [])


def test_duplicate_id_fails(tmp_path):
    run_dir = valid_run(tmp_path)
    curated = json.loads((run_dir / "04-anecdotes.json").read_text())
    curated.append(copy.deepcopy(curated[0]))
    write_curated(run_dir, curated)
    code, lines = validate(run_dir)
    assert code == 1
    assert f"duplicate id {curated[0]['id']}" in lines


def test_quote_of_41_words_fails(tmp_path):
    long_quote = " ".join(f"word{i}" for i in range(41))
    candidates = [record(1, quote=long_quote), record(2), record(3, sentiment=1)]
    run_dir = hand_run(tmp_path, candidates)
    write_curated(run_dir, candidates)
    code, lines = validate(run_dir)
    assert code == 1
    assert "AN-001: quote has 41 words (maximum 40)" in lines


def test_quote_of_40_words_with_ellipsis_passes(tmp_path):
    quote = " ".join(f"word{i}" for i in range(40)) + "…"
    candidates = [record(1, quote=quote), record(2), record(3, sentiment=1)]
    run_dir = hand_run(tmp_path, candidates)
    write_curated(run_dir, candidates)
    assert validate(run_dir) == (0, [])


def test_planted_email_fails(tmp_path):
    run_dir = valid_run(tmp_path)
    curated = json.loads((run_dir / "04-anecdotes.json").read_text())
    curated[0]["quote"] += " mail jordan.testperson@example.invalid"
    write_curated(run_dir, curated)
    code, lines = validate(run_dir)
    assert code == 1
    assert f"{curated[0]['id']}: field 'quote': PII found (email): jordan.testperson@example.invalid" in lines


def test_planted_name_fails_with_configured_terms(tmp_path):
    candidates = [record(1, persona="Casey Samplename"), record(2), record(3, sentiment=1)]
    run_dir = hand_run(tmp_path, candidates)
    write_curated(run_dir, candidates)
    code, lines = validate(run_dir)
    assert code == 1
    assert "AN-001: field 'persona': PII found (term): Casey Samplename" in lines


def test_consent_false_fails(tmp_path):
    candidates = [record(1, consent_ok=False), record(2), record(3, sentiment=1)]
    run_dir = hand_run(tmp_path, candidates)
    write_curated(run_dir, candidates)
    code, lines = validate(run_dir)
    assert code == 1
    assert "AN-001: consent_ok must be true" in lines


def test_unknown_linked_problem_fails(tmp_path):
    candidates = [record(1, linked_problem="PB-9"), record(2), record(3, sentiment=1)]
    run_dir = hand_run(tmp_path, candidates)
    write_curated(run_dir, candidates)
    code, lines = validate(run_dir)
    assert code == 1
    assert "AN-001: linked_problem 'PB-9' not in 02-problem.md" in lines


def test_frequency_hint_without_card_fails(tmp_path):
    run_dir = valid_run(tmp_path)
    curated = json.loads((run_dir / "04-anecdotes.json").read_text())
    curated[0]["frequency_hint"] = "EV-009"
    write_curated(run_dir, curated)
    code, lines = validate(run_dir)
    assert code == 1
    assert f"{curated[0]['id']}: frequency_hint 'EV-009' is not an existing evidence card" in lines


def test_frequency_hint_with_existing_card_passes(tmp_path):
    run_dir = valid_run(tmp_path)
    evidence = run_dir / "03-evidence"
    evidence.mkdir()
    (evidence / "EV-009.json").write_text("{}")
    curated = json.loads((run_dir / "04-anecdotes.json").read_text())
    curated[0]["frequency_hint"] = "EV-009"
    write_curated(run_dir, curated)
    assert validate(run_dir) == (0, [])


def test_missing_counter_anecdote_fails(tmp_path):
    run_dir = make_pulled_run(tmp_path)
    negatives = [c for c in read_candidates(run_dir) if c["sentiment"] <= 0][:3]
    write_curated(run_dir, negatives)
    code, lines = validate(run_dir)
    assert code == 1
    assert "counter-anecdote missing: select a record with positive sentiment" in lines


def test_no_counter_anecdote_needed_when_candidates_have_none(tmp_path):
    candidates = [record(1), record(2), record(3)]
    run_dir = hand_run(tmp_path, candidates)
    write_curated(run_dir, candidates)
    assert validate(run_dir) == (0, [])


def test_record_not_in_candidates_fails(tmp_path):
    run_dir = valid_run(tmp_path)
    curated = json.loads((run_dir / "04-anecdotes.json").read_text())
    curated[0]["id"] = "AN-099"
    write_curated(run_dir, curated)
    code, lines = validate(run_dir)
    assert code == 1
    assert "AN-099: not found in 04-anecdotes.candidates.json" in lines


def test_schema_failure_names_record_and_field(tmp_path):
    run_dir = valid_run(tmp_path)
    curated = json.loads((run_dir / "04-anecdotes.json").read_text())
    del curated[1]["pain"]
    curated[2]["sentiment"] = 7
    write_curated(run_dir, curated)
    code, lines = validate(run_dir)
    assert code == 1
    assert any(line.startswith(f"{curated[1]['id']}: field 'record': ") and "'pain'" in line for line in lines)
    assert any(line.startswith(f"{curated[2]['id']}: field 'sentiment': ") for line in lines)


def test_missing_candidates_file(tmp_path):
    run_dir = make_run(tmp_path)
    write_curated(run_dir, [record(1)])
    code, lines = validate(run_dir)
    assert code == 1
    assert len(lines) == 1
    assert lines[0].startswith("04-anecdotes.candidates.json not found:")


def test_missing_curated_file(tmp_path):
    run_dir = hand_run(tmp_path, [record(1)])
    code, lines = validate(run_dir)
    assert code == 1
    assert lines[0].startswith("04-anecdotes.json not found:")


def test_invalid_json(tmp_path):
    run_dir = hand_run(tmp_path, [record(1)])
    (run_dir / "04-anecdotes.json").write_text("{not json")
    code, lines = validate(run_dir)
    assert code == 1
    assert lines[0].startswith("04-anecdotes.json is not valid JSON:")


def test_not_an_array(tmp_path):
    run_dir = hand_run(tmp_path, [record(1)])
    (run_dir / "04-anecdotes.json").write_text(json.dumps({"id": "AN-001"}))
    code, lines = validate(run_dir)
    assert code == 1
    assert lines == ["04-anecdotes.json must be a JSON array"]


def test_missing_run_dir(tmp_path):
    code, lines = validate(tmp_path / "nope")
    assert code == 1
    assert lines[0].startswith("Run directory not found:")
