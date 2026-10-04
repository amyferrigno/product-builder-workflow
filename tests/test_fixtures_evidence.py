"""Evidence-citing fixture: goldens validate, cited ids exist, quotes and numbers trace to script output."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
FIXTURE = REPO_ROOT / "fixtures" / "clean-meeting-evidence"
GOLDEN = FIXTURE / "golden"
MOCK_REGISTRY = str(REPO_ROOT / "fixtures" / "registry.mock.yaml")
MOCK_CONFIG = str(REPO_ROOT / "fixtures" / "pm.config.mock.yaml")


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=REPO_ROOT)


def make_run(tmp_path: Path) -> Path:
    """Intake for the fixture, then copy every golden file and the evidence folder into the run."""
    expected = yaml.safe_load((FIXTURE / "expected.yaml").read_text())
    intake = run(
        "scripts/intake.py", FIXTURE / "notes.md", "--slug", "clean-meeting-evidence",
        "--runs-dir", tmp_path, "--date", expected["run_id"][:10],
    )
    assert intake.returncode == 0, intake.stderr
    run_dir = Path(json.loads(intake.stdout)["run_dir"])
    for golden in GOLDEN.iterdir():
        if golden.is_file():
            shutil.copy(golden, run_dir / golden.name)
    shutil.copytree(GOLDEN / "03-evidence", run_dir / "03-evidence")
    return run_dir


@pytest.fixture
def run_dir(tmp_path):
    return make_run(tmp_path)


def section(prd: str, start: str, end: str) -> str:
    return prd[prd.index(start):prd.index(end)]


def test_notes_are_the_clean_meeting_notes():
    assert (FIXTURE / "notes.md").read_bytes() == (REPO_ROOT / "fixtures" / "clean-meeting" / "notes.md").read_bytes()


def test_all_validators_pass(run_dir):
    for script, extra in (
        ("validate_extraction.py", []),
        ("validate_problem.py", []),
        ("validate_evidence.py", []),
        ("validate_anecdotes.py", ["--config", MOCK_CONFIG]),
        ("validate_prd.py", []),
    ):
        result = run(f"scripts/{script}", run_dir, *extra)
        assert result.returncode == 0, f"{script}: {result.stdout}{result.stderr}"


def test_prd_cites_existing_evidence_and_anecdotes(run_dir):
    prd = (run_dir / "prd.md").read_text()
    card_ids = {p.stem for p in (run_dir / "03-evidence").glob("EV-*.json")}
    anecdote_ids = {a["id"] for a in json.loads((run_dir / "04-anecdotes.json").read_text())}
    cited_ev = set(re.findall(r"\bEV-\d{3}\b", prd))
    cited_an = set(re.findall(r"\bAN-\d{3}\b", prd))
    assert cited_ev and cited_ev <= card_ids
    assert cited_an and cited_an <= anecdote_ids
    assert "No data provider configured" not in prd
    assert "No anecdote provider configured" not in prd


def test_section_6b_quotes_equal_anecdote_quotes(run_dir):
    prd = (run_dir / "prd.md").read_text()
    anecdotes = {a["id"]: a for a in json.loads((run_dir / "04-anecdotes.json").read_text())}
    section_6b = section(prd, "### 6b.", "### 6c.")
    lines = [ln for ln in section_6b.splitlines() if re.match(r"- .*AN-\d{3}", ln)]
    assert len(lines) >= 3
    for line in lines:
        an_id = re.search(r"\bAN-\d{3}\b", line).group()
        quote = re.search(r'"(.*)"', line).group(1)
        assert quote == anecdotes[an_id]["quote"]
    assert any(a["sentiment"] > 0 for a in anecdotes.values())  # a counter-example is kept


def test_card_values_in_prd_match_cards(run_dir):
    prd = (run_dir / "prd.md").read_text()
    section_6a = section(prd, "### 6a.", "### 6b.")
    for path in (run_dir / "03-evidence").glob("EV-*.json"):
        card = json.loads(path.read_text())
        assert card["claim"] in section_6a
        assert f"| {card['n']} |" in section_6a


def test_audit_hash_and_verdict(run_dir):
    expected = yaml.safe_load((FIXTURE / "expected.yaml").read_text())
    audit = json.loads((run_dir / "prd.audit.json").read_text())
    assert audit["run_id"] == expected["run_id"]
    assert audit["prd_hash"] == hashlib.sha256((run_dir / "prd.md").read_bytes()).hexdigest()
    result = run("scripts/render_audit.py", run_dir)
    assert result.stdout.strip() == expected["prd"]["verdict"]
    assert result.returncode == 0


def test_pii_scan_is_clean(run_dir):
    for name in ("prd.md", "04-anecdotes.json", "04-anecdotes.candidates.json"):
        scan = run("scripts/pii.py", "scan", run_dir / name, "--config", MOCK_CONFIG)
        assert scan.returncode == 0, scan.stdout + scan.stderr


def test_regenerating_a_card_gives_the_same_value_and_n(tmp_path):
    fresh = make_run(tmp_path)
    shutil.rmtree(fresh / "03-evidence")
    golden = json.loads((GOLDEN / "03-evidence" / "EV-002.json").read_text())
    enrich = run(
        "scripts/enrich.py", "run", fresh, "--provider", "mock_warehouse",
        "--query-id", golden["query_id"], "--params", json.dumps({"segment": golden["segment"]}),
        "--question", "How many messages are exchanged per completed meeting for enterprise accounts?",
        "--claim", golden["claim_template"], "--supports", "PB-1",
        "--registry", MOCK_REGISTRY, "--config", MOCK_CONFIG, "--cache-dir", tmp_path / "cache",
    )
    assert enrich.returncode == 0, enrich.stderr
    card = json.loads(next((fresh / "03-evidence").glob("EV-*.json")).read_text())
    assert card["value"] == golden["value"] and card["n"] == golden["n"]
    assert card["query_hash"] == golden["query_hash"]
