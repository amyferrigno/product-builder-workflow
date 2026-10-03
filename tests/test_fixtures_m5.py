"""Golden UX for the ai-clear-fit fixture (M5)."""
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
from validate_ux import validate_ux  # noqa: E402

GOLDEN = REPO / "fixtures" / "ai-clear-fit" / "golden"
STATES = [
    "default", "loading", "empty", "error", "success",
    "low-confidence", "user-edit", "regenerate", "explanation", "escalation",
]
DIMENSIONS = {
    "req_coverage", "required_states", "ai_trust_control_recovery",
    "accessibility", "token_consistency", "copy_clarity",
}


def make_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    shutil.copy(GOLDEN / "prd.md", run / "prd.md")
    shutil.copytree(GOLDEN / "ux", run / "ux")
    return run


def test_golden_ux_validates(tmp_path):
    assert validate_ux(make_run(tmp_path), repo_root=REPO) == []


def test_audit_hash_matches_golden_ux(tmp_path):
    audit = json.loads((GOLDEN / "ux.audit.json").read_text())
    assert audit["ux_hash"] == ux_hash(make_run(tmp_path))


def test_every_screen_has_all_ten_states():
    screens = sorted((GOLDEN / "ux" / "screens").glob("SCR-*.html"))
    assert 2 <= len(screens) <= 4
    for screen in screens:
        text = screen.read_text()
        for state in STATES:
            assert f'id="state-{state}" data-state="{state}"' in text, (screen.name, state)


def test_every_must_requirement_is_in_the_spec():
    prd = (GOLDEN / "prd.md").read_text()
    spec = (GOLDEN / "ux" / "spec.md").read_text()
    musts = [req for req, priority in parse_requirements(prd) if priority == "Must"]
    assert musts
    for req in musts:
        assert req in spec, req


def test_golden_audit_shape():
    audit = json.loads((GOLDEN / "ux.audit.json").read_text())
    ids = [d["id"] for d in audit["dimensions"]]
    assert sorted(ids) == sorted(DIMENSIONS)
    assert audit["ai_feature"] is True
    for dim in audit["dimensions"]:
        if dim["score"] < 3:
            assert dim.get("fix") and dim.get("screens")


def run_script(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=REPO)


def test_golden_ux_audit_matches_schema():
    schema = json.loads((REPO / "schemas" / "ux-audit.schema.json").read_text())
    audit = json.loads((GOLDEN / "ux.audit.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(audit)) == []


def test_offline_end_to_end_ai_clear_fit(tmp_path):
    fixture = REPO / "fixtures" / "ai-clear-fit"
    decisions = tmp_path / "decisions.test.md"
    decisions.write_text("# Decisions\n\n")

    intake = run_script(
        "scripts/intake.py", fixture / "notes.md", "--date", "2026-01-15",
        "--slug", "ai-clear-fit", "--runs-dir", tmp_path,
    )
    assert intake.returncode == 0, intake.stderr
    run = Path(json.loads(intake.stdout)["run_dir"])
    for src, dest in (("01-extraction.json", "01-extraction.json"), ("02-problem.md", "02-problem.md"),
                      ("prd.md", "prd.md"), ("prd.audit.json", "prd.audit.json")):
        shutil.copy(GOLDEN / src, run / dest)

    assert run_script("scripts/render_audit.py", run).returncode == 0
    approve_prd = run_script("scripts/approve.py", run, "prd", "--decisions-file", decisions)
    assert approve_prd.returncode == 0, approve_prd.stdout + approve_prd.stderr

    shutil.copytree(GOLDEN / "ux", run / "ux")
    shutil.copy(GOLDEN / "ux.audit.json", run / "ux.audit.json")
    validate = run_script("scripts/validate_ux.py", run)
    assert validate.returncode == 0, validate.stdout + validate.stderr
    render = run_script("scripts/render_ux_audit.py", run)
    assert render.returncode == 0, render.stdout + render.stderr
    state = json.loads((run / "state.json").read_text())
    assert state["verdicts"]["ux"] in ("PASS", "PASS_WITH_RISK")
    summary = run_script("scripts/gate_summary.py", run, "ux")
    assert summary.returncode == 0, summary.stdout + summary.stderr

    prd_before = (run / "prd.md").read_bytes()
    approve_ux = run_script("scripts/approve.py", run, "ux", "--decisions-file", decisions)
    assert approve_ux.returncode == 0, approve_ux.stdout + approve_ux.stderr
    assert (run / "prd.md").read_bytes() == prd_before

    check = run_script("scripts/check_approval.py", run, "ux")
    assert check.returncode == 0 and check.stdout.strip() == "approved"

    trace = (run / "traceability.md").read_text()
    prd_reqs = [req for req, _ in parse_requirements(prd_before.decode("utf-8"))]
    assert prd_reqs
    for req in prd_reqs:
        assert req in trace, req

    screen = sorted((run / "ux" / "screens").glob("SCR-*.html"))[0]
    screen.write_text(screen.read_text() + "\n<!-- edited -->\n")
    stale = run_script("scripts/check_approval.py", run, "ux")
    assert stale.returncode != 0
    assert stale.stdout.strip().startswith("stale")
