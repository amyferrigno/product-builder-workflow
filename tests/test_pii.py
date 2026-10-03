"""Test scripts/pii.py: scan, scrub, config loading and CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import pii  # noqa: E402

REPO = Path(__file__).parent.parent
TICKETS = REPO / "fixtures" / "mock_anecdotes" / "tickets.json"
TERMS = REPO / "fixtures" / "mock_anecdotes" / "pii_terms.yaml"
TERMS_CFG = {"people": ["Jordan Testperson"], "companies": ["Northwind Example Ltd"]}


def run_cli(*args, cwd=REPO):
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "pii.py")] + [str(a) for a in args],
        capture_output=True, text=True, cwd=cwd,
    )
    return result.returncode, result.stdout, result.stderr


def types(text, **kw):
    return [f["type"] for f in pii.scan(text, **kw)]


# Patterns detected and scrubbed

def test_email_detected_and_scrubbed():
    text = "write to jo.test@example.invalid today"
    assert pii.scan(text) == [{"type": "email", "match": "jo.test@example.invalid", "line": 1}]
    assert pii.scrub(text) == "write to [email] today"


@pytest.mark.parametrize("phone", ["+00 000 555 0101", "(000) 555-0102", "000-555-0103", "000.555.0104", "555-0105"])
def test_phone_forms_detected_and_scrubbed(phone):
    text = f"call {phone} now"
    assert pii.scan(text) == [{"type": "phone", "match": phone, "line": 1}]
    assert pii.scrub(text) == "call [phone] now"


def test_url_userinfo_detected_and_scrubbed():
    text = "see https://jordan:hunter2@example.invalid/billing please"
    findings = pii.scan(text)
    assert [f["type"] for f in findings] == ["url_userinfo"]
    assert findings[0]["match"] == "https://jordan:hunter2@example.invalid/billing"
    assert pii.scrub(text) == "see [url] please"


def test_url_without_userinfo_not_flagged():
    assert pii.scan("see https://example.invalid/billing") == []


# Look-alikes that must NOT be flagged

def test_iso_date_not_flagged():
    assert pii.scan("audit on 2026-09-12 ok") == []


def test_iso_date_with_time_not_flagged():
    assert pii.scan("at 2026-09-12 10:30 ok") == []


def test_ev_token_not_flagged():
    assert pii.scan("see EV-003 for data") == []


def test_req_token_not_flagged():
    assert pii.scan("see REQ-001 and REQ-002") == []


def test_plain_count_not_flagged():
    assert pii.scan("12450 meetings were booked") == []


def test_long_plain_digit_run_not_flagged():
    assert pii.scan("total 1234567890 events") == []


def test_sha256_hex_not_flagged():
    digest = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert pii.scan(f"hash {digest} end") == []


def test_version_number_not_flagged():
    assert pii.scan("upgrade to v1.2.3 or 10.20.30") == []


def test_numeric_range_not_flagged():
    assert pii.scan("takes 3-4 days") == []


def test_id_followed_by_count_not_flagged():
    assert pii.scan("REQ-001 12450") == []


def test_year_range_not_flagged():
    assert pii.scan("fiscal 2026-2027 plan") == []


# Config-driven terms

def test_people_terms_case_insensitive_whole_phrase():
    cfg = {"people": ["Jordan Testperson"], "companies": []}
    text = "JORDAN testperson and jordan Testperson spoke; Jordan Testpersonal did not"
    assert pii.scrub(text, cfg) == "[name] and [name] spoke; Jordan Testpersonal did not"
    assert types(text, pii_terms=cfg) == ["term", "term"]


def test_company_terms_scrubbed_by_default():
    text = "Northwind Example Ltd is a customer"
    assert pii.scrub(text, TERMS_CFG) == "[company] is a customer"
    assert types(text, pii_terms=TERMS_CFG) == ["term"]


def test_company_terms_kept_when_allowed():
    text = "Northwind Example Ltd asked Jordan Testperson"
    assert pii.scrub(text, TERMS_CFG, allow_company_names=True) == "Northwind Example Ltd asked [name]"
    assert types(text, pii_terms=TERMS_CFG, allow_company_names=True) == ["term"]


def test_people_scrubbed_even_when_companies_allowed():
    assert pii.scrub("Jordan Testperson", TERMS_CFG, allow_company_names=True) == "[name]"


def test_no_terms_means_no_term_findings():
    assert pii.scan("Jordan Testperson at Northwind Example Ltd") == []


def test_scrub_is_idempotent():
    text = "a@example.invalid +00 000 555 0101 https://u:p@example.invalid Jordan Testperson Northwind Example Ltd"
    once = pii.scrub(text, TERMS_CFG)
    assert once == "[email] [phone] [url] [name] [company]"
    assert pii.scrub(once, TERMS_CFG) == once
    assert pii.scan(once, TERMS_CFG) == []


def test_scan_line_numbers():
    text = "clean line\nmail a@example.invalid\n\ncall 000-555-0103 now\nJordan Testperson"
    got = [(f["type"], f["line"]) for f in pii.scan(text, TERMS_CFG)]
    assert got == [("email", 2), ("phone", 4), ("term", 5)]


def test_email_inside_url_userinfo_reported_once():
    findings = pii.scan("https://bob@example.invalid/x")
    assert [f["type"] for f in findings] == ["url_userinfo"]


# Config loading

def test_load_pii_config_reads_both_keys(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("anecdotes:\n  allow_company_names: true\n  pii_terms:\n    people: [Ann Example]\n    companies: [Acme Fake]\n")
    assert pii.load_pii_config(str(cfg)) == ({"people": ["Ann Example"], "companies": ["Acme Fake"]}, True)


def test_load_pii_config_defaults(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("anecdotes:\n  allow_company_names: false\n")
    assert pii.load_pii_config(str(cfg)) == ({"people": [], "companies": []}, False)


def test_simple_config_reader_matches_yaml_reader():
    content = (
        "product:\n  name: x\nanecdotes:\n  allow_company_names: true\n"
        "  pii_terms:\n    people:\n      - Ann Example\n      - \"Bob Fake\"\n    companies: [Acme Fake, 'Zed Co']\n"
    )
    terms, allow = pii._simple_config(content)
    assert terms == {"people": ["Ann Example", "Bob Fake"], "companies": ["Acme Fake", "Zed Co"]}
    assert allow is True


def test_simple_config_reader_defaults():
    assert pii._simple_config("product:\n  name: x\n") == ({"people": [], "companies": []}, False)


def test_repo_config_has_empty_pii_terms():
    assert pii.load_pii_config(str(REPO / "pm.config.yaml")) == ({"people": [], "companies": []}, False)


# CLI

def test_cli_scan_dirty_exits_1_with_finding_line(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("ok\nmail a@example.invalid\n")
    code, out, err = run_cli("scan", f)
    assert code == 1
    assert out.strip() == f"{f}:2: email: a@example.invalid"
    assert "Traceback" not in out + err


def test_cli_scan_clean_exits_0(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("nothing here on 2026-09-12\n")
    code, out, err = run_cli("scan", f)
    assert code == 0 and out == ""
    assert "Traceback" not in err


def test_cli_scan_uses_config_terms(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("Jordan Testperson was here\n")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("anecdotes:\n  allow_company_names: false\n  pii_terms: { people: [Jordan Testperson], companies: [] }\n")
    code, out, _ = run_cli("scan", f, "--config", cfg)
    assert code == 1
    assert out.strip() == f"{f}:1: term: Jordan Testperson"


def test_cli_scrub_prints_scrubbed_text(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("mail a@example.invalid\n")
    code, out, err = run_cli("scrub", f)
    assert code == 0
    assert out == "mail [email]\n"
    assert "Traceback" not in err


def test_cli_missing_file_one_line_error(tmp_path):
    missing = tmp_path / "nope.txt"
    code, out, err = run_cli("scan", missing)
    assert code == 1
    assert out.strip() == f"Error: File not found: {missing}"
    assert "Traceback" not in out + err


def test_cli_missing_config_one_line_error(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("x\n")
    code, out, err = run_cli("scan", f, "--config", tmp_path / "nope.yaml")
    assert code == 1
    assert out.strip() == f"Error: Config not found: {tmp_path / 'nope.yaml'}"
    assert "Traceback" not in out + err


def test_cli_bad_usage_exits_1():
    code, out, err = run_cli("frobnicate")
    assert code == 1
    assert out.startswith("Usage:")
    assert "Traceback" not in out + err


# Planted PII in the mock source

def _planted():
    """Strings planted in tickets.json by construction."""
    terms = yaml.safe_load(TERMS.read_text())
    return {
        "email": ["jordan.testperson@example.invalid", "front.desk@example.invalid"],
        "phone": ["+00 000 555 0101", "(000) 555-0102"],
        "url_userinfo": ["https://jordan:hunter2@example.invalid/billing"],
        "term": terms["people"] + terms["companies"],
    }


def test_planted_pii_found_by_scan_on_raw_file():
    terms = yaml.safe_load(TERMS.read_text())
    findings = pii.scan(TICKETS.read_text(), terms, allow_company_names=False)
    found = {(f["type"], f["match"]) for f in findings}
    for ftype, matches in _planted().items():
        for m in matches:
            assert (ftype, m) in found, f"{ftype} not found: {m}"


def test_planted_pii_gone_after_scrub_of_quote_and_pain():
    terms = yaml.safe_load(TERMS.read_text())
    records = json.loads(TICKETS.read_text())
    all_planted = [m for ms in _planted().values() for m in ms]
    for rec in records:
        for field in ("quote", "pain"):
            clean = pii.scrub(rec[field], terms, allow_company_names=False)
            assert pii.scan(clean, terms, allow_company_names=False) == [], rec["source_ref"]
            for m in all_planted:
                assert m not in clean


def test_clean_records_unchanged_by_scrub():
    terms = yaml.safe_load(TERMS.read_text())
    records = json.loads(TICKETS.read_text())
    unchanged = [r for r in records if pii.scrub(r["quote"], terms) == r["quote"]]
    assert len(unchanged) >= 10
