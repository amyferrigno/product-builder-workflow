"""Golden ticket manifest for the ai-clear-fit fixture."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from ux_hash import ux_hash  # noqa: E402
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


def run_script(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=REPO)


def test_offline_end_to_end_gate_c_to_dry_run(tmp_path):
    decisions = tmp_path / "decisions.test.md"
    decisions.write_text("# Decisions\n\n")
    intake = run_script(
        "scripts/intake.py", REPO / "fixtures" / "ai-clear-fit" / "notes.md", "--date", "2026-01-15",
        "--slug", "ai-clear-fit", "--runs-dir", tmp_path,
    )
    assert intake.returncode == 0, intake.stderr
    run = Path(json.loads(intake.stdout)["run_dir"])
    for name in ("01-extraction.json", "02-problem.md", "prd.md", "prd.audit.json"):
        shutil.copy(GOLDEN / name, run / name)
    assert run_script("scripts/render_audit.py", run).returncode == 0
    approve_prd = run_script("scripts/approve.py", run, "prd", "--decisions-file", decisions)
    assert approve_prd.returncode == 0, approve_prd.stdout + approve_prd.stderr

    shutil.copytree(GOLDEN / "ux", run / "ux")
    shutil.copy(GOLDEN / "ux.audit.json", run / "ux.audit.json")
    assert run_script("scripts/render_ux_audit.py", run).returncode == 0
    approve_ux = run_script("scripts/approve.py", run, "ux", "--decisions-file", decisions)
    assert approve_ux.returncode == 0, approve_ux.stdout + approve_ux.stderr

    # No Jira output without a matching approval
    dryrun = run / "tickets.dryrun.json"
    assert run_script("scripts/check_approval.py", run, "tickets").returncode != 0
    assert run_script("scripts/jira_publish.py", run).returncode == 1
    assert not dryrun.exists()

    shutil.copy(MANIFEST, run / "tickets.manifest.json")
    validate = run_script("scripts/validate_tickets.py", run)
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert run_script("scripts/preview_tickets.py", run).returncode == 0
    assert (run / "tickets.preview.md").exists()
    summary = run_script("scripts/gate_summary.py", run, "tickets")
    assert summary.returncode == 0, summary.stdout + summary.stderr
    assert run_script("scripts/jira_publish.py", run).returncode == 1
    assert not dryrun.exists()

    prd_before = (run / "prd.md").read_bytes()
    ux_before = ux_hash(run)
    approve_tickets = run_script("scripts/approve.py", run, "tickets", "--decisions-file", decisions)
    assert approve_tickets.returncode == 0, approve_tickets.stdout + approve_tickets.stderr
    check = run_script("scripts/check_approval.py", run, "tickets")
    assert check.returncode == 0 and check.stdout.strip() == "approved"

    publish = run_script("scripts/jira_publish.py", run)
    assert publish.returncode == 0, publish.stdout + publish.stderr
    assert "DRY RUN: nothing was sent to Jira" in publish.stdout
    entries = json.loads(dryrun.read_text())
    manifest = load()
    epic_ids = [e["id"] for e in manifest["epics"]]
    assert [e["ticket_id"] for e in entries] == epic_ids + [c["id"] for c in children(manifest)]
    for entry in entries[:len(epic_ids)]:
        assert entry["payload"]["fields"]["issuetype"]["name"] == "Epic"

    trace = (run / "traceability.md").read_text()
    for child in children(manifest):
        if child["type"] == "Story":
            assert child["id"] in trace
    assert (run / "prd.md").read_bytes() == prd_before
    assert ux_hash(run) == ux_before

    edited = load()
    edited["epics"][0]["summary"] = edited["epics"][0]["summary"] + " again"
    (run / "tickets.manifest.json").write_text(json.dumps(edited, indent=2))
    stale = run_script("scripts/check_approval.py", run, "tickets")
    assert stale.returncode != 0
    assert stale.stdout.strip().startswith("stale")
    dryrun.unlink()
    assert run_script("scripts/jira_publish.py", run).returncode == 1
    assert not dryrun.exists()
