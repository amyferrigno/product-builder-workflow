"""Test scripts/anecdotes.py."""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import anecdotes
from pii import scan

MOCK_REGISTRY = str(REPO_ROOT / "fixtures" / "registry.mock.yaml")
MOCK_CONFIG = str(REPO_ROOT / "fixtures" / "pm.config.mock.yaml")
TICKETS = REPO_ROOT / "fixtures" / "mock_anecdotes" / "tickets.json"
PII_TERMS = REPO_ROOT / "fixtures" / "mock_anecdotes" / "pii_terms.yaml"
WIDE_KEYWORDS = "scheduling,billing,login"


def load_tickets():
    return json.loads(TICKETS.read_text())


def planted_strings():
    """Every PII string planted in the fixture: names, companies and regex-detectable PII."""
    terms = yaml.safe_load(PII_TERMS.read_text())
    planted = list(terms["people"]) + list(terms["companies"])
    for ticket in load_tickets():
        for field in ("quote", "pain", "persona"):
            planted += [f["match"] for f in scan(ticket[field], terms)]
    return sorted(set(planted))


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
    for name in ("02-problem.md", "01-extraction.json"):
        shutil.copy(REPO_ROOT / "fixtures" / "clean-meeting" / "golden" / name, run_dir / name)
    return run_dir


def pull(tmp_path, run_dir, keywords=WIDE_KEYWORDS, *extra, provider="mock_anecdotes",
         problem="PB-1", registry=MOCK_REGISTRY, config=MOCK_CONFIG):
    cmd = [
        sys.executable, "scripts/anecdotes.py", "pull", str(run_dir),
        "--provider", provider, "--problem", problem, "--keywords", keywords,
        "--registry", registry, "--config", config, "--cache-dir", str(tmp_path / "cache"),
        *extra,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return result.returncode, result.stdout, result.stderr


def candidates_of(run_dir):
    return json.loads((run_dir / "04-anecdotes.candidates.json").read_text())


def test_pull_writes_schema_valid_candidates(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = pull(tmp_path, run_dir, "scheduling")
    assert code == 0, stderr
    assert "Traceback" not in stderr
    summary = json.loads(stdout)
    records = candidates_of(run_dir)
    assert len(records) == summary["candidates"] > 0
    schema = json.loads((REPO_ROOT / "schemas" / "anecdote.schema.json").read_text())
    validator = Draft202012Validator(schema)
    for rec in records:
        assert list(validator.iter_errors(rec)) == []
        assert rec["linked_problem"] == "PB-1"
        assert rec["frequency_hint"] is None
        assert rec["consent_ok"] is True


def test_no_planted_pii_reaches_candidates(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = pull(tmp_path, run_dir)
    assert code == 0, stderr
    text = (run_dir / "04-anecdotes.candidates.json").read_text()
    planted = planted_strings()
    assert len(planted) >= 8  # names, companies, 2 emails, 2 phones, a URL: not vacuous
    for item in planted:
        assert item not in text, f"planted PII leaked: {item}"
    for fragment in ("hunter2", "555 0101", "555-0102", "testperson", "front.desk"):
        assert fragment.lower() not in text.lower()
    assert "[email]" in text and "[phone]" in text and "[name]" in text and "[company]" in text


def test_non_consented_records_are_absent(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, _ = pull(tmp_path, run_dir)
    assert code == 0
    refused = [t for t in load_tickets() if t["consent_ok"] is False]
    assert len(refused) >= 3
    refs = {r["source_ref"] for r in candidates_of(run_dir)}
    for ticket in refused:
        assert ticket["source_ref"] not in refs
    assert json.loads(stdout)["dropped_consent"] == len(refused)


def test_long_quotes_are_cut_to_40_words_with_ellipsis(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, _ = pull(tmp_path, run_dir)
    assert code == 0
    by_ref = {r["source_ref"]: r for r in candidates_of(run_dir)}
    long_tickets = [t for t in load_tickets() if len(t["quote"].split()) > 40 and t["consent_ok"]]
    assert len(long_tickets) >= 2
    for ticket in long_tickets:
        quote = by_ref[ticket["source_ref"]]["quote"]
        assert quote.endswith("…")
        assert len(quote.rstrip("…").split()) == 40
        assert quote.rstrip("…") == " ".join(ticket["quote"].split()[:40])
    assert json.loads(stdout)["truncated"] == len(long_tickets)
    short = by_ref["ticket/48202"]["quote"]
    assert not short.endswith("…")


def test_ids_are_sequential(tmp_path):
    run_dir = make_run(tmp_path)
    pull(tmp_path, run_dir)
    ids = [r["id"] for r in candidates_of(run_dir)]
    assert ids == [f"AN-{i:03d}" for i in range(1, len(ids) + 1)]


def test_second_pull_is_deduplicated_and_other_keywords_continue_ids(tmp_path):
    run_dir = make_run(tmp_path)
    pull(tmp_path, run_dir, "scheduling")
    first = candidates_of(run_dir)
    code, stdout, _ = pull(tmp_path, run_dir, "scheduling")
    assert code == 0
    assert json.loads(stdout)["candidates"] == 0
    assert candidates_of(run_dir) == first

    code, stdout, stderr = pull(tmp_path, run_dir, "billing")
    assert code == 0, stderr
    after = candidates_of(run_dir)
    assert after[: len(first)] == first
    assert len(after) > len(first)
    assert [r["id"] for r in after] == [f"AN-{i:03d}" for i in range(1, len(after) + 1)]
    refs = [r["source_ref"] for r in after]
    assert len(refs) == len(set(refs))


def test_segment_and_limit_are_passed_through(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = pull(tmp_path, run_dir, "scheduling", "--segment", "SMB", "--limit", "2")
    assert code == 0, stderr
    records = candidates_of(run_dir)
    assert 0 < len(records) <= 2
    assert {r["segment"] for r in records} == {"SMB"}


def test_unknown_problem_is_refused(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = pull(tmp_path, run_dir, problem="PB-9")
    assert code == 1
    assert stderr.strip() == "unknown problem 'PB-9' (not in 02-problem.md)"
    assert "Traceback" not in stderr
    assert not (run_dir / "04-anecdotes.candidates.json").exists()


def test_missing_problem_file(tmp_path):
    run_dir = tmp_path / "runs" / "empty"
    run_dir.mkdir(parents=True)
    code, _, stderr = pull(tmp_path, run_dir)
    assert code == 1
    assert stderr.strip().startswith("File not found:")
    assert "Traceback" not in stderr


def test_disabled_provider_gives_one_line_error(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = pull(
        tmp_path, run_dir, provider="warehouse",
        registry=str(REPO_ROOT / "connectors" / "registry.yaml"),
    )
    assert code == 1
    assert stderr.strip() == "provider 'warehouse' is disabled"
    assert "Traceback" not in stderr


def test_unknown_provider_gives_one_line_error(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = pull(tmp_path, run_dir, provider="nope")
    assert code == 1
    assert stderr.strip() == "unknown provider 'nope'"
    assert not (run_dir / "04-anecdotes.candidates.json").exists()


def test_empty_keywords_refused(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = pull(tmp_path, run_dir, " , ")
    assert code == 1
    assert stderr.strip() == "--keywords must contain at least one keyword"


def test_zero_matches_writes_empty_array(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = pull(tmp_path, run_dir, "zzz-no-such-word")
    assert code == 0, stderr
    assert json.loads(stdout)["candidates"] == 0
    assert candidates_of(run_dir) == []


def test_without_pii_terms_regex_pii_is_still_scrubbed_but_names_leak(tmp_path):
    """
    No anecdotes.pii_terms configured: emails, phones and URLs with user info are still
    removed by regex, but planted person and company names cannot be recognised, so they
    pass through (the fail-closed scan uses the same terms, so it cannot catch them either).
    Configure pii_terms to protect names.
    """
    config = yaml.safe_load(Path(MOCK_CONFIG).read_text())
    config["anecdotes"]["pii_terms"] = {"people": [], "companies": []}
    bare = tmp_path / "bare.config.yaml"
    bare.write_text(yaml.safe_dump(config))
    run_dir = make_run(tmp_path)
    code, _, stderr = pull(tmp_path, run_dir, config=str(bare))
    assert code == 0, stderr
    text = (run_dir / "04-anecdotes.candidates.json").read_text()

    regex_pii = [s for s in planted_strings() if re.search(r"@|\d{3}", s)]
    assert len(regex_pii) >= 4
    for item in regex_pii:
        assert item not in text, f"regex-detectable PII leaked: {item}"
    assert "hunter2" not in text
    assert "[email]" in text and "[phone]" in text

    # Documented behaviour: names are not protected without pii_terms.
    assert "Casey Samplename" in text
    assert "Contoso Fakeworks Inc" in text


def test_fail_closed_when_scan_still_finds_pii(tmp_path, monkeypatch):
    run_dir = make_run(tmp_path)
    monkeypatch.setattr(anecdotes, "scrub", lambda text, *a, **k: text)
    args = argparse.Namespace(
        run_dir=str(run_dir), provider="mock_anecdotes", problem="PB-1", keywords="scheduling",
        segment=None, limit=None, registry=MOCK_REGISTRY, config=MOCK_CONFIG,
        cache_dir=str(tmp_path / "cache"),
    )
    with pytest.raises(anecdotes.AnecdoteError) as excinfo:
        anecdotes.pull(args)
    message = str(excinfo.value)
    assert message.startswith("PII still present after scrubbing, nothing written:")
    assert "email" in message
    assert not (run_dir / "04-anecdotes.candidates.json").exists()


def test_word_count_ignores_trailing_ellipsis():
    assert anecdotes.word_count("a b c…") == 3
    quote, cut = anecdotes.truncate_quote(" ".join(["w"] * 41))
    assert cut and anecdotes.word_count(quote) == 40
    quote, cut = anecdotes.truncate_quote(" ".join(["w"] * 40))
    assert not cut and not quote.endswith("…")


STUB_ANECDOTE_PROVIDER = '''
import json, sys
json.load(sys.stdin)
row = {
    "source": "zendesk", "source_ref": "ticket/stub1", "date": "2026-06-03", "segment": "SMB",
    "persona": "Office manager", "pain": "Scheduling is slow",
    "quote": "write to josé@example.com or call 555–010–9999 about scheduling",
    "sentiment": -1, "consent_ok": True,
}
print(json.dumps({"ok": True, "rows": [row], "n": 1, "run_at": "2026-01-01T00:00:00+00:00",
                  "query_hash": "abc", "caveats": []}))
'''


def test_non_ascii_email_and_typographic_dash_phone_do_not_reach_candidates(tmp_path):
    script = tmp_path / "stub_provider.py"
    script.write_text(STUB_ANECDOTE_PROVIDER, encoding="utf-8")
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"providers": [{
        "id": "stub_anecdotes", "kind": "script", "enabled": True,
        "command": f"python {script}", "capabilities": ["anecdotes"],
    }]}))
    run_dir = make_run(tmp_path)
    code, _, stderr = pull(tmp_path, run_dir, "scheduling", provider="stub_anecdotes", registry=str(registry))
    assert code == 0, stderr
    records = candidates_of(run_dir)
    assert len(records) == 1
    text = (run_dir / "04-anecdotes.candidates.json").read_text()
    assert "josé@example.com" not in text
    assert "555–010–9999" not in text
    assert "[email]" in records[0]["quote"] and "[phone]" in records[0]["quote"]
