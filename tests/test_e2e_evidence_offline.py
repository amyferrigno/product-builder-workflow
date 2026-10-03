"""Offline end-to-end test: enrichment and anecdotes for the clean-meeting fixture, mock providers only."""

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
MOCK_REGISTRY = str(REPO_ROOT / "fixtures" / "registry.mock.yaml")
MOCK_CONFIG = str(REPO_ROOT / "fixtures" / "pm.config.mock.yaml")
FIXTURE = REPO_ROOT / "fixtures" / "clean-meeting"
SHARE_PARAMS = {"category": "scheduling_conflict", "period_start": "2025-07", "period_end": "2025-12"}


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=REPO_ROOT)


def tree_state(path):
    """Sorted (relative name, sha256) of every file under path; empty when path does not exist."""
    root = Path(path)
    if not root.exists():
        return []
    return [
        (str(f.relative_to(root)), hashlib.sha256(f.read_bytes()).hexdigest())
        for f in sorted(root.rglob("*")) if f.is_file()
    ]


def expected_share_and_total():
    with open(REPO_ROOT / "fixtures" / "mock_warehouse" / "support_tickets.csv", newline="") as f:
        tickets = [t for t in csv.DictReader(f) if "2025-07" <= t["created_month"] <= "2025-12"]
    hits = sum(t["category"] == "scheduling_conflict" for t in tickets)
    return hits / len(tickets), len(tickets)


def test_offline_evidence_pipeline_on_clean_meeting(tmp_path):
    queries_before = tree_state(REPO_ROOT / "connectors" / "queries")
    cache_before = tree_state(REPO_ROOT / ".cache")
    registry_before = (REPO_ROOT / "connectors" / "registry.yaml").read_bytes()

    # Intake and goldens.
    intake = run(
        "scripts/intake.py", FIXTURE / "notes.md", "--slug", "clean-meeting",
        "--runs-dir", tmp_path, "--date", "2026-01-15",
    )
    assert intake.returncode == 0, intake.stderr
    run_dir = Path(json.loads(intake.stdout)["run_dir"])
    for name in ("01-extraction.json", "02-problem.md"):
        shutil.copy(FIXTURE / "golden" / name, run_dir / name)

    # Data enrichment against a temp copy of the query library.
    queries = tmp_path / "queries"
    shutil.copytree(REPO_ROOT / "connectors" / "queries", queries)
    cache = tmp_path / "cache"
    share, total = expected_share_and_total()
    enrich = run(
        "scripts/enrich.py", "run", run_dir,
        "--provider", "mock_warehouse", "--query-id", "ticket_share_by_category",
        "--params", json.dumps(SHARE_PARAMS), "--question", "How common are scheduling conflicts?",
        "--claim", "{value_pct}% of {n} tickets are scheduling conflicts",
        "--supports", "PB-1", "--registry", MOCK_REGISTRY, "--config", MOCK_CONFIG,
        "--queries-dir", queries, "--cache-dir", cache,
    )
    assert enrich.returncode == 0, enrich.stderr
    printed = json.loads(enrich.stdout)
    card_id = printed["id"]
    assert card_id == "EV-001"
    assert printed["n"] == total and printed["confidence"] == "high"
    assert printed["claim"].endswith(f"% of {total} tickets are scheduling conflicts")
    card = json.loads((run_dir / "03-evidence" / f"{card_id}.json").read_text())
    assert abs(card["value"] - share) < 0.005
    assert card["confidence"] == "high"

    evidence = run("scripts/validate_evidence.py", run_dir, "--queries-dir", queries)
    assert evidence.returncode == 0, evidence.stdout + evidence.stderr

    # Anecdotes.
    pulled = run(
        "scripts/anecdotes.py", "pull", run_dir, "--provider", "mock_anecdotes", "--problem", "PB-1",
        "--keywords", "scheduling", "--registry", MOCK_REGISTRY, "--config", MOCK_CONFIG,
        "--cache-dir", cache,
    )
    assert pulled.returncode == 0, pulled.stderr
    candidates_path = run_dir / "04-anecdotes.candidates.json"
    candidates = json.loads(candidates_path.read_text())
    positive = [c for c in candidates if c["sentiment"] > 0]
    negative = [c for c in candidates if c["sentiment"] <= 0]
    assert positive and len(negative) >= 2

    curated = positive[:1] + negative[:3]
    curated[1]["frequency_hint"] = card_id
    (run_dir / "04-anecdotes.json").write_text(json.dumps(curated, indent=2))

    validated = run("scripts/validate_anecdotes.py", run_dir, "--config", MOCK_CONFIG)
    assert validated.returncode == 0, validated.stdout + validated.stderr

    for name in ("04-anecdotes.json", "04-anecdotes.candidates.json"):
        scan = run("scripts/pii.py", "scan", run_dir / name, "--config", MOCK_CONFIG)
        assert scan.returncode == 0, scan.stdout + scan.stderr

    # The real environment is untouched.
    registry = yaml.safe_load((REPO_ROOT / "connectors" / "registry.yaml").read_text())
    assert registry["providers"] and all(p["enabled"] is False for p in registry["providers"])
    assert (REPO_ROOT / "connectors" / "registry.yaml").read_bytes() == registry_before
    assert tree_state(REPO_ROOT / "connectors" / "queries") == queries_before
    assert tree_state(REPO_ROOT / ".cache") == cache_before
