"""Golden ticket manifest for the ai-clear-fit fixture (M6)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from validate_prd import parse_requirements  # noqa: E402
from validate_tickets import validate_tickets  # noqa: E402

GOLDEN = REPO / "fixtures" / "ai-clear-fit" / "golden"
MANIFEST = GOLDEN / "tickets.manifest.json"
RUN_ID = "2026-01-15-ai-clear-fit"


def make_run(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "intake.py"),
         str(REPO / "fixtures" / "ai-clear-fit" / "notes.md"),
         "--date", "2026-01-15", "--slug", "ai-clear-fit", "--runs-dir", str(runs)],
        check=True, capture_output=True, text=True,
    )
    run = runs / RUN_ID
    shutil.copy(GOLDEN / "02-problem.md", run / "02-problem.md")
    shutil.copy(GOLDEN / "prd.md", run / "prd.md")
    shutil.copytree(GOLDEN / "ux", run / "ux")
    shutil.copy(MANIFEST, run / "tickets.manifest.json")
    return run


def load() -> dict:
    return json.loads(MANIFEST.read_text())


def children(manifest: dict) -> list:
    return [c for e in manifest["epics"] for c in e["children"]]


def test_golden_manifest_passes_definition_of_ready(tmp_path):
    assert validate_tickets(make_run(tmp_path), repo_root=REPO) == []


def test_every_must_requirement_is_covered_by_a_story():
    prd = (GOLDEN / "prd.md").read_text()
    musts = [req for req, priority in parse_requirements(prd) if priority == "Must"]
    assert musts
    covered = {r for c in children(load()) if c["type"] == "Story" for r in c["req_ids"]}
    for req in musts:
        assert req in covered, req


def test_epic_structure():
    epics = load()["epics"]
    assert sum(1 for e in epics if e.get("kind") == "measure_quality") == 1
    for epic in epics:
        if epic.get("kind", "feature") == "feature":
            kinds = [c.get("task_kind") for c in epic["children"] if c["type"] == "Task"]
            assert kinds.count("instrumentation") == 1, epic["id"]


def test_no_jira_keys_or_story_points():
    manifest = load()
    for epic in manifest["epics"]:
        assert epic["jira_key"] is None
    for child in children(manifest):
        assert child["jira_key"] is None
    text = MANIFEST.read_text()
    assert "story_points" not in text
    assert "storyPoints" not in text


def test_manifest_matches_schema():
    schema = json.loads((REPO / "schemas" / "ticket-manifest.schema.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(load())) == []
