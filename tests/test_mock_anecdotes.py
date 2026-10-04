"""Test the mock anecdote provider and its fixture."""

import json
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import pii

REPO = Path(__file__).parent.parent
PROVIDER = REPO / "connectors" / "providers" / "mock_anecdotes.py"
TICKETS = REPO / "fixtures" / "mock_anecdotes" / "tickets.json"
TERMS = REPO / "fixtures" / "mock_anecdotes" / "pii_terms.yaml"
SOURCES = {"zendesk", "nps", "gong", "interview"}
SEGMENTS = {"SMB", "Mid-market", "Enterprise"}


def call(request, raw=None):
    stdin = raw if raw is not None else json.dumps(request)
    result = subprocess.run([sys.executable, str(PROVIDER)], input=stdin, capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    return json.loads(result.stdout)


def req(params, query_id="anecdotes_by_keyword"):
    return {"question": "scheduling pain", "query_id": query_id, "params": params}


def output_validator():
    schema = json.loads((REPO / "schemas" / "provider-io.schema.json").read_text())
    return Draft202012Validator({"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/output"})


def test_output_validates_against_provider_io_schema():
    out = call(req({"keywords": ["scheduling"]}))
    errors = [e.message for e in output_validator().iter_errors(out)]
    assert errors == []
    assert out["ok"] is True and out["n"] == len(out["rows"]) > 0
    assert out["caveats"] == ["synthetic mock data"]


def test_error_output_validates_too():
    out = call(req({}))
    assert [e.message for e in output_validator().iter_errors(out)] == []


def test_keyword_filter_returns_scheduling_not_billing():
    out = call(req({"keywords": ["scheduling"]}))
    refs = {r["source_ref"] for r in out["rows"]}
    assert "ticket/48201" in refs
    assert "ticket/48204" not in refs  # billing invoice
    assert "ticket/48205" not in refs  # login
    for r in out["rows"]:
        text = (" ".join(r["keywords"]) + r["pain"] + r["quote"]).lower()
        assert "scheduling" in text


def test_keywords_as_comma_string_and_case_insensitive():
    a = call(req({"keywords": "BILLING, refund"}))
    assert {r["source_ref"] for r in a["rows"]} >= {"ticket/48204", "ticket/48209"}
    b = call(req({"keywords": ["billing", "refund"]}))
    assert a["rows"] == b["rows"]


def test_matches_keyword_in_quote_text():
    out = call(req({"keywords": ["spins"]}))
    assert [r["source_ref"] for r in out["rows"]] == ["ticket/48210"]


def test_segment_filter():
    out = call(req({"keywords": ["scheduling"], "segment": "Enterprise"}))
    assert out["rows"] and all(r["segment"] == "Enterprise" for r in out["rows"])
    allseg = call(req({"keywords": ["scheduling"]}))
    assert out["n"] < allseg["n"]


def test_limit_caps_rows_but_n_counts_matches():
    out = call(req({"keywords": ["scheduling"], "limit": 2}))
    assert len(out["rows"]) == 2
    assert out["n"] > 2


def test_no_match_is_ok_with_zero_rows():
    out = call(req({"keywords": ["zzz-no-such-word"]}))
    assert out["ok"] is True and out["rows"] == [] and out["n"] == 0


def test_rows_are_raw_unscrubbed():
    out = call(req({"keywords": ["scheduling"]}))
    terms = yaml.safe_load(TERMS.read_text())
    assert pii.scan(json.dumps(out["rows"]), terms), "provider must return raw rows"


def test_bad_inputs_give_ok_false_with_required_fields():
    cases = [
        (req({}), "params.keywords must be a non-empty list or comma string"),
        (req({"keywords": []}), "params.keywords must be a non-empty list or comma string"),
        (req({"keywords": " , "}), "params.keywords must be a non-empty list or comma string"),
        (req({"keywords": ["a"], "limit": 0}), "params.limit must be a positive integer"),
        (req({"keywords": ["a"], "segment": 5}), "params.segment must be a string"),
        (req({"keywords": ["a"]}, query_id="other"), "unknown query_id: other"),
        ({"question": "q", "query_id": "anecdotes_by_keyword", "params": "x"}, "params must be an object"),
    ]
    for request, message in cases:
        out = call(request)
        assert out["ok"] is False and out["error"] == message
        assert out["rows"] == [] and out["n"] == 0
        assert out["run_at"] and out["query_hash"] and out["caveats"]


def test_malformed_stdin_gives_ok_false():
    out = call(None, raw="not json")
    assert out["ok"] is False and out["error"] == "invalid JSON on stdin"
    assert [e.message for e in output_validator().iter_errors(out)] == []


# Fixture shape

def records():
    return json.loads(TICKETS.read_text())


def test_fixture_fields_and_value_sets():
    recs = records()
    assert 20 <= len(recs) <= 30
    for r in recs:
        assert set(r) == {
            "source", "source_ref", "date", "segment", "persona", "pain", "quote", "sentiment", "consent_ok",
            "keywords",
        }
        assert r["source"] in SOURCES and r["segment"] in SEGMENTS
        assert -2 <= r["sentiment"] <= 2 and isinstance(r["consent_ok"], bool)
        assert isinstance(r["keywords"], list) and r["keywords"]
    assert len({r["source_ref"] for r in recs}) == len(recs)
    assert {r["source"] for r in recs} == SOURCES
    assert {r["segment"] for r in recs} == SEGMENTS


def test_fixture_has_required_counts():
    recs = records()
    terms = yaml.safe_load(TERMS.read_text())
    with_pii = [r for r in recs if pii.scan(r["quote"] + "\n" + r["pain"], terms)]
    assert len(with_pii) >= 6
    positive = [r for r in recs if r["sentiment"] >= 1 and "scheduling" in r["keywords"]]
    assert len(positive) >= 2
    assert len([r for r in recs if r["consent_ok"] is False]) >= 3
    assert len([r for r in recs if len(r["quote"].split()) > 40]) >= 1


def test_fixture_has_unrelated_themes():
    kws = {k for r in records() for k in r["keywords"]}
    assert {"billing", "login"} <= kws
