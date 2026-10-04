"""Test gate_summary.py script."""

import json
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = ["clean-meeting", "thin-evidence", "ai-clear-fit"]


def run_gate_summary(run_dir: str, artifact: str = "prd") -> tuple:
    """Run gate_summary script and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, "scripts/gate_summary.py", run_dir, artifact]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    return result.returncode, result.stdout, result.stderr


def create_test_run_with_prd(tmpdir: str) -> str:
    """Create a test run with a PRD and state."""
    run_dir = Path(tmpdir) / "2026-10-03-test"
    run_dir.mkdir(parents=True)

    # Create state.json
    state = {
        "run_id": "2026-10-03-test",
        "stage": "stage2",
        "status": "in_progress",
        "verdicts": {
            "prd": "PASS",
            "ux": None
        },
        "artifact_hashes": {
            "notes": "abc123"
        },
        "approval_hashes": {
            "prd": None,
            "ux": None,
            "tickets": None
        },
        "jira_keys": {},
        "updated_at": "2026-10-03T00:00:00Z"
    }

    state_path = run_dir / "state.json"
    with open(state_path, 'w') as f:
        json.dump(state, f)

    # Create PRD with all sections
    prd_content = """# PRD

## 1. Header

This is the header section.

## 2. TL;DR

Executive summary.

## 3. Problem statement

The problem is X.

## 4. Why now and strategic fit

Strategic fit explanation.

## 5. Target users and segments

User segments described here.

## 6. Evidence

### 6a. Data insights

Data insights here.

### 6b. Customer anecdotes

Anecdotes here.

### 6c. Evidence gaps

Evidence gaps here.

## 7. Goals and non-goals

Goals and non-goals.

## 8. Success metrics

- **MET-001** Primary metric: 10% increase in user engagement by end of Q4 2026

## 9. Value tests

Value tests here.

## 10. Solution overview

Solution overview here.

## 11. User flow

User flow here.

## 12. Requirements

Requirements here.

## 13. MVP scope

### In v1

- Feature A
- Feature B
- Feature C
- Feature D
- Feature E

### Out of v1

- Feature F
- Feature G
- Feature H

## 14. Dependencies and assumptions

Dependencies here.

## 15. Risks and mitigations

Risks here.

## 16. Launch and rollout

Launch plan here.

## 17. Open questions

- Question 1?
- Question 2?
- Question 3?
- Question 4?
- Question 5?
- Question 6?

## 18. Alignment

Alignment here.

## 19. Decision log

Decision log here.

## 20. Traceability

Traceability here.
"""

    prd_path = run_dir / "prd.md"
    prd_path.write_text(prd_content)

    # Create 02-problem.md
    problem_content = """---
run_id: "2026-10-03-test"
primary_problem: "PB-1"
problems:
  - id: "PB-1"
    title: "Improve user retention"
    validation_status: "VALIDATED"
---

## Problem statement

Users are dropping off.

## Who has it

All users.

## Exact scenario

User stops using the product.

## Current workaround

Users switch to competitor.

## Why now

Competition is increasing.

## Strategic fit

Improves our retention metrics.

## Validation status

VALIDATED

## Other topics parked

None.
"""

    problem_path = run_dir / "02-problem.md"
    problem_path.write_text(problem_content)

    # Create prd.audit.json (the schema has no verdict field)
    audit = {
        "run_id": "2026-10-03-test",
        "prd_hash": "somehash",
        "dimensions": [
            {"id": "problem_clarity", "score": 4},
            {"id": "evidence_strength", "score": 3},
            {"id": "strategic_fit", "score": 4},
            {"id": "success_metrics", "score": 3},
            {"id": "scope_discipline", "score": 3},
            {"id": "feasibility", "score": 3},
            {"id": "testability", "score": 3},
            {"id": "risk_coverage", "score": 3},
            {"id": "traceability", "score": 3}
        ]
    }

    audit_path = run_dir / "prd.audit.json"
    with open(audit_path, 'w') as f:
        json.dump(audit, f)

    return str(run_dir)


def test_gate_summary_full_output():
    """Test that full inputs produce each labeled part."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0, f"Failed: {stderr}"

        # Check for key parts
        assert "Run ID" in stdout
        assert "2026-10-03-test" in stdout
        assert "Problem:" in stdout
        assert "Primary metric:" in stdout
        assert "MVP Scope" in stdout
        assert "Verdict:" in stdout
        assert "Open Questions" in stdout
        assert "Cost: no cost data" in stdout
        assert "Next step:" in stdout


def test_gate_summary_shows_problem_title():
    """Test that problem title is shown."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "Improve user retention" in stdout


def test_gate_summary_shows_validation_status():
    """Test that validation status is shown in parentheses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "VALIDATED" in stdout


def test_gate_summary_shows_primary_metric():
    """Test that primary metric is shown."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "Primary metric: MET-001 10% increase in user engagement" in stdout
        assert stdout.count("Primary metric:") == 1
        assert "**" not in stdout


def test_gate_summary_shows_scope_in():
    """Test that MVP scope in items are shown."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "Feature A" in stdout
        assert "Feature B" in stdout


def test_gate_summary_shows_scope_out():
    """Test that MVP scope out items are shown."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "MVP Scope (out)" in stdout
        assert "Feature F" in stdout


def test_gate_summary_shows_audit_verdict():
    """Test that audit verdict is shown."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "Audit Verdict: PASS" in stdout


def test_gate_summary_computes_verdict_when_state_has_none():
    """Without a verdict in state.json it is computed from prd.audit.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)
        state_path = Path(run_dir) / "state.json"
        state = json.loads(state_path.read_text())
        state["verdicts"]["prd"] = None
        state_path.write_text(json.dumps(state))

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        # The audit hash is stale, so the computed verdict is FAIL (not "not available")
        assert "Audit Verdict: FAIL" in stdout


def test_gate_summary_scope_overflow_and_subheadings():
    """Scope reads past ### sub-headings and caps each side at 5 with a +N note."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)
        prd_path = Path(run_dir) / "prd.md"
        prd_path.write_text(prd_path.read_text().replace("- Feature E\n", "- Feature E\n- Feature E2\n- Feature E3\n"))

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "Feature E2" not in stdout
        assert "(+2 more)" in stdout


def test_gate_summary_shows_dimension_scores():
    """Test that dimension scores are shown."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "problem_clarity: 4 *" in stdout
        assert "strategic_fit: 4" in stdout
        assert "strategic_fit: 4 *" not in stdout


def test_gate_summary_open_questions_limited_to_5():
    """Test that more than 5 open questions shows 5 and a count."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        # Should show 5 questions and "... and 1 more"
        assert "Question 1?" in stdout
        assert "Question 5?" in stdout
        # Check for "more" indicator
        lines = stdout.split('\n')
        open_q_found = False
        for i, line in enumerate(lines):
            if "Open Questions:" in line:
                open_q_found = True
                # Count how many questions are shown
                q_count = 0
                for j in range(i + 1, min(i + 10, len(lines))):
                    if "Question" in lines[j]:
                        q_count += 1
                # Should have at most 5 + maybe a "more" line
                break

        assert open_q_found


def test_gate_summary_missing_audit_shows_not_available():
    """Test that missing audit JSON shows 'not available'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        # Remove the audit file and the state verdict
        (Path(run_dir) / "prd.audit.json").unlink()
        state_path = Path(run_dir) / "state.json"
        state = json.loads(state_path.read_text())
        state["verdicts"]["prd"] = None
        state_path.write_text(json.dumps(state))

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "Audit Verdict: not available" in stdout


def test_gate_summary_missing_prd():
    """Test that missing prd.md exits 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "2026-10-03-test"
        run_dir.mkdir(parents=True)

        code, stdout, stderr = run_gate_summary(str(run_dir))

        assert code == 1
        assert "Traceback" not in stderr


def test_cost_line_known_figure(tmp_path):
    """A small cost log gives a known figure."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import gate_summary
    (tmp_path / "state.json").write_text(json.dumps({"stage": "stage1"}))
    (tmp_path / "cost.log.jsonl").write_text(json.dumps({"stage": "stage1", "estimated_usd": 1.5}) + "\n")
    config = {"budgets": {"stage1": 3.0}, "pricing": {"medium": {}}}
    assert gate_summary.cost_line(tmp_path, config) == "Cost: 1.50 of 3.00 USD estimated for stage 1 (50.0%)"


def test_cost_line_no_cost_data(tmp_path):
    """No log, or no price table, gives 'no cost data' and never raises."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import gate_summary
    config = {"budgets": {"stage1": 3.0}, "pricing": {"medium": {}}}
    assert gate_summary.cost_line(tmp_path, config) == "Cost: no cost data"
    (tmp_path / "cost.log.jsonl").write_text(json.dumps({"stage": "stage1", "estimated_usd": 1.5}) + "\n")
    assert gate_summary.cost_line(tmp_path, {"budgets": {"stage1": 3.0}}) == "Cost: no cost data"


def test_gate_summary_cost_line():
    """Test that cost line is present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "Cost: no cost data" in stdout


def test_gate_summary_next_step_line():
    """Test that next step line is present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "Next step: Approve with /pm-approve prd 2026-10-03-test" in stdout


def _build_golden_run(name: str, tmp_path: Path) -> Path:
    """Run intake for a fixture, copy goldens in, and render the audit (writes state verdict)."""
    expected = yaml.safe_load((REPO_ROOT / "fixtures" / name / "expected.yaml").read_text())
    intake = subprocess.run(
        [
            sys.executable, "scripts/intake.py",
            str(REPO_ROOT / "fixtures" / name / "notes.md"),
            "--slug", name,
            "--runs-dir", str(tmp_path),
            "--date", expected["run_id"][:10],
        ],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert intake.returncode == 0, intake.stderr
    run_dir = Path(json.loads(intake.stdout)["run_dir"])
    for golden in (REPO_ROOT / "fixtures" / name / "golden").iterdir():
        if golden.is_file():
            shutil.copy(golden, run_dir / golden.name)
    subprocess.run(
        [sys.executable, "scripts/render_audit.py", str(run_dir)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return run_dir


def _md_section(prd: str, heading: str) -> str:
    start = prd.index(heading)
    end = prd.find("\n## ", start + 1)
    return prd[start:end if end != -1 else len(prd)]


@pytest.mark.parametrize("name", FIXTURES)
def test_gate_summary_on_golden_fixture(name: str, tmp_path: Path):
    decisions = REPO_ROOT / "decisions.md"
    decisions_before = decisions.read_bytes() if decisions.exists() else None

    run_dir = _build_golden_run(name, tmp_path)
    expected = yaml.safe_load((REPO_ROOT / "fixtures" / name / "expected.yaml").read_text())
    golden = REPO_ROOT / "fixtures" / name / "golden"
    prd = (golden / "prd.md").read_text()
    problem_fm = yaml.safe_load((golden / "02-problem.md").read_text().split("---")[1])
    primary = next(p for p in problem_fm["problems"] if p["id"] == problem_fm["primary_problem"])

    code, stdout, stderr = run_gate_summary(str(run_dir))
    assert code == 0, stderr
    lines = stdout.splitlines()

    # Problem
    assert primary["title"] in stdout
    assert primary["validation_status"] in stdout

    # Verdict
    assert f"Audit Verdict: {expected['prd']['verdict']}" in stdout

    # Scope: first in-v1 item and first out-of-v1 item appear verbatim
    scope = _md_section(prd, "## 13. MVP scope")
    in_part, out_part = scope.split("### Out of v1")
    first_in = next(l[2:].strip() for l in in_part.splitlines() if l.startswith("- "))
    first_out = next(l[2:].strip() for l in out_part.splitlines() if l.startswith("- "))
    assert first_in in stdout
    assert first_out in stdout

    # Primary metric: ID present, no markdown bold
    metric_line = next(l for l in lines if l.startswith("Primary metric:"))
    assert "MET-001" in metric_line
    assert "**" not in metric_line
    assert "not available" not in metric_line

    # Fixed lines and size
    assert "Cost: no cost data" in lines
    next_line = next(l for l in lines if l.startswith("Next step:"))
    if expected["prd"]["verdict"] in ("PASS", "PASS_WITH_RISK"):
        assert "/pm-approve prd " in next_line
        assert "<run-id>" not in next_line
    else:
        assert "verdict is FAIL" in next_line
    assert len(lines) < 45

    # No "not available" for problem, verdict, scope or metric
    for l in lines:
        if l.startswith(("Problem:", "Audit Verdict:", "Primary metric:")):
            assert "not available" not in l
    assert "  not available" not in lines[lines.index("MVP Scope (in):") + 1]
    assert "  not available" not in lines[lines.index("MVP Scope (out):") + 1]

    # Tests must never write to the real decisions file
    assert (decisions.read_bytes() if decisions.exists() else None) == decisions_before


def test_gate_summary_open_questions_from_table():
    """Open questions written as a table are listed with their owner, capped at 5."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)
        prd_path = Path(run_dir) / "prd.md"
        prd = prd_path.read_text()
        start = prd.index("## 17. Open questions")
        end = prd.index("## 18.", start)
        rows = "".join(f"| Table question {i}? | PM |\n" for i in range(1, 8))
        table = "## 17. Open questions\n\n| Question | Owner role |\n|---|---|\n" + rows + "\n"
        prd_path.write_text(prd[:start] + table + prd[end:])

        code, stdout, stderr = run_gate_summary(run_dir)

        assert code == 0
        assert "  - Table question 1? (PM)" in stdout
        assert "  - Table question 5? (PM)" in stdout
        assert "Table question 6?" not in stdout
        assert "(+2 more)" in stdout
        assert "Owner role" not in stdout



def _next_step_line(stdout: str) -> str:
    return next(l for l in stdout.splitlines() if l.startswith("Next step:"))


def _set_verdict(run_dir: str, verdict) -> None:
    state_path = Path(run_dir) / "state.json"
    state = json.loads(state_path.read_text())
    state["verdicts"]["prd"] = verdict
    state_path.write_text(json.dumps(state))


@pytest.mark.parametrize("verdict", ["PASS", "PASS_WITH_RISK"])
def test_gate_summary_next_step_pass_has_real_run_id(verdict):
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)
        _set_verdict(run_dir, verdict)
        code, stdout, stderr = run_gate_summary(run_dir)
        assert code == 0, stderr
        assert _next_step_line(stdout) == (
            "Next step: Approve with /pm-approve prd 2026-10-03-test or send change requests"
        )
        assert "<run-id>" not in stdout


def test_gate_summary_next_step_fail_does_not_offer_plain_approval():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)
        _set_verdict(run_dir, "FAIL")
        code, stdout, stderr = run_gate_summary(run_dir)
        assert code == 0, stderr
        assert _next_step_line(stdout) == (
            "Next step: verdict is FAIL; revise the flagged sections, or approve with an explicit override reason"
        )


def test_gate_summary_next_step_no_verdict_says_audit_first():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run_with_prd(tmpdir)
        _set_verdict(run_dir, None)
        (Path(run_dir) / "prd.audit.json").unlink()
        code, stdout, stderr = run_gate_summary(run_dir)
        assert code == 0, stderr
        assert _next_step_line(stdout) == "Next step: run the audit first"


# --- Gate B: gate_summary ux --------------------------------------------------

def _ux_summary(tmp_path, ai=False, scores=None):
    sys.path.insert(0, str(Path(__file__).parent))
    from ux_gate_helpers import audited_run
    run = audited_run(tmp_path, ai=ai, scores=scores)
    return run, run_gate_summary(str(run), "ux")


def test_gate_summary_ux_pass(tmp_path):
    run, (code, stdout, stderr) = _ux_summary(tmp_path)
    assert code == 0, stderr
    assert "UX Gate Summary" in stdout
    assert "Audit Verdict: PASS" in stdout
    assert "req_coverage: 4 *" in stdout
    assert "accessibility: 4\n" in stdout
    assert "Screens: 2" in stdout
    assert "Script check errors: none" in stdout
    assert "Fixes for scores below 3" not in stdout
    assert "Next step: Approve with /pm-approve ux run-1" in stdout


def test_gate_summary_ux_must_coverage_counts(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from validate_prd import parse_requirements
    run, (code, stdout, _) = _ux_summary(tmp_path)
    must = [r for r, p in parse_requirements((run / "prd.md").read_text()) if p == "Must"]
    assert f"Must requirements covered: {len(must)} of {len(must)}" in stdout


def test_gate_summary_ux_shows_fixes_for_low_scores(tmp_path):
    run, (code, stdout, _) = _ux_summary(tmp_path, scores={"copy_clarity": 2, "req_coverage": 1})
    assert code == 0
    assert "Audit Verdict: FAIL" in stdout
    assert "Fixes for scores below 3:" in stdout
    assert "copy_clarity: Improve copy_clarity. (screens: SCR-001)" in stdout
    assert "verdict is FAIL" in stdout
    assert "/pm-approve ux run-1" in stdout


def test_gate_summary_ux_lists_script_errors(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from ux_gate_helpers import audited_run
    run = audited_run(tmp_path)
    (run / "ux" / "index.html").unlink()
    code, stdout, _ = run_gate_summary(str(run), "ux")
    assert code == 0
    assert "Script check errors (" in stdout
    assert "index.html" in stdout


def test_gate_summary_ux_without_audit_says_audit_first(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from ux_gate_helpers import make_gate_run
    run = make_gate_run(tmp_path)
    code, stdout, _ = run_gate_summary(str(run), "ux")
    assert code == 0
    assert "Audit Verdict: not available" in stdout
    assert "Next step: run the audit first" in stdout


def test_gate_summary_ux_missing_folder_errors(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from ux_gate_helpers import make_gate_run
    import shutil as _shutil
    run = make_gate_run(tmp_path)
    _shutil.rmtree(run / "ux")
    code, _, stderr = run_gate_summary(str(run), "ux")
    assert code == 1
    assert "ux folder not found" in stderr


# --- Gate C: gate_summary tickets ---------------------------------------------

def _tickets_summary(tmp_path, mutate=None):
    sys.path.insert(0, str(Path(__file__).parent))
    from tickets_helpers import make_tickets_run, valid_manifest, write_manifest
    run = make_tickets_run(tmp_path)
    if mutate:
        m = valid_manifest(run, False)
        mutate(m)
        write_manifest(run, m)
    return run, run_gate_summary(str(run), "tickets")


def test_gate_summary_tickets_clean(tmp_path):
    run, (code, stdout, stderr) = _tickets_summary(tmp_path)
    assert code == 0, stderr
    manifest = json.loads((run / "tickets.manifest.json").read_text())
    stories = [c for e in manifest["epics"] for c in e["children"] if c["type"] == "Story"]
    assert "Tickets Gate Summary" in stdout
    assert "Epics: 2" in stdout
    assert f"Stories: {len(stories)}" in stdout
    assert "Spikes: 1" in stdout
    assert f"Must requirements covered: {len(stories)} of {len(stories)}" in stdout
    assert "Definition of Ready errors: none" in stdout
    assert "tickets.preview.md" in stdout
    assert "/pm-approve tickets run-1" in stdout


def test_gate_summary_tickets_lists_errors(tmp_path):
    def mutate(m):
        m["epics"][0]["children"][0]["acceptance_criteria"].pop()
    _, (code, stdout, _) = _tickets_summary(tmp_path, mutate)
    assert code == 0
    assert "Definition of Ready errors (" in stdout
    assert "T-001" in stdout
    assert "/pm-approve tickets" not in stdout


def test_gate_summary_tickets_missing_manifest_errors(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from tickets_helpers import make_tickets_run
    run = make_tickets_run(tmp_path)
    (run / "tickets.manifest.json").unlink()
    code, _, stderr = run_gate_summary(str(run), "tickets")
    assert code == 1
    assert "tickets.manifest.json" in stderr
