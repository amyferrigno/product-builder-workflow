"""Test approve.py script."""

import hashlib
import json
import tempfile
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ux_gate_helpers import approve_prd_file, audited_run, build_audit, make_gate_run, render, sha, ux_hash, write_audit  # noqa: E402


def run_approve(
    run_dir: str,
    artifact: str = "prd",
    override_reason: str = None,
    decisions_file: str = None
) -> tuple:
    """Run approve script and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, "scripts/approve.py", run_dir, artifact]

    if override_reason is not None:
        cmd.extend(["--override", override_reason])

    # Never let a test append to the repo's real decisions.md
    if decisions_file is None:
        decisions_file = str(Path(run_dir) / "decisions.test.md")
    cmd.extend(["--decisions-file", decisions_file])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    return result.returncode, result.stdout, result.stderr


def run_check_approval(run_dir: str, artifact: str = "prd") -> tuple:
    """Run check_approval script and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, "scripts/check_approval.py", run_dir, artifact]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    return result.returncode, result.stdout, result.stderr


PRD_DIMS = ["problem_clarity", "evidence_strength", "strategic_fit", "success_metrics", "scope_discipline",
            "feasibility", "testability", "risk_coverage", "traceability"]


def write_prd_audit(run_dir, verdict: str) -> None:
    """Write a real prd.audit.json that computes to the given verdict (None counts as FAIL)."""
    run_dir = Path(run_dir)
    scores = {d: 4 for d in PRD_DIMS}
    if verdict == "PASS_WITH_RISK":
        scores["evidence_strength"] = 2
    elif verdict != "PASS":
        scores["problem_clarity"] = 1
    dims = []
    for dim_id, score in scores.items():
        dim = {"id": dim_id, "score": score, "justification": f"{dim_id} note."}
        if score < 3:
            dim["fix"] = f"Improve {dim_id}."
            dim["sections"] = ["1"]
        dims.append(dim)
    audit = {
        "run_id": "2026-10-03-test",
        "prd_hash": hashlib.sha256((run_dir / "prd.md").read_bytes()).hexdigest(),
        "ai_feature": False,
        "dimensions": dims,
        "hallucination_check": {"unsupported_numbers": [], "unsupported_quotes": [], "unsupported_decisions": []},
    }
    (run_dir / "prd.audit.json").write_text(json.dumps(audit), encoding="utf-8")


def create_test_run(tmpdir: str, verdict: str = "PASS", audited: bool = True) -> str:
    """Create a test run directory with state.json and prd.md."""
    run_dir = Path(tmpdir) / "2026-10-03-test"
    run_dir.mkdir(parents=True)
    (run_dir / "approvals").mkdir()

    # Create state.json
    state = {
        "run_id": "2026-10-03-test",
        "stage": "stage2",
        "status": "in_progress",
        "verdicts": {
            "prd": verdict,
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

    # Create prd.md
    prd_content = "# PRD\n\nThis is a test PRD.\n"
    prd_path = run_dir / "prd.md"
    prd_path.write_text(prd_content)

    # An audited run records the PRD hash in state
    if audited:
        state["artifact_hashes"]["prd"] = hashlib.sha256(prd_content.encode()).hexdigest()
        with open(state_path, 'w') as f:
            json.dump(state, f)
        write_prd_audit(run_dir, verdict)

    return str(run_dir)


def test_approve_pass():
    """Test that PASS verdict approves successfully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")
        decisions_file = Path(tmpdir) / "decisions.md"
        decisions_file.write_text("# Decisions\n\n")

        code, stdout, stderr = run_approve(run_dir, decisions_file=str(decisions_file))

        assert code == 0, f"Failed: {stderr}"

        # Check approval file was created
        approval_path = Path(run_dir) / "approvals" / "prd.approved"
        assert approval_path.exists(), "Approval file not created"

        # Check approval file content
        with open(approval_path, 'r') as f:
            approval = json.load(f)

        assert approval["artifact"] == "prd"
        assert approval["verdict"] == "PASS"
        assert approval["override_reason"] is None
        assert "sha256" in approval
        assert "approved_at" in approval


def test_approve_pass_with_risk():
    """Test that PASS_WITH_RISK verdict approves successfully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS_WITH_RISK")
        decisions_file = Path(tmpdir) / "decisions.md"
        decisions_file.write_text("# Decisions\n\n")

        code, stdout, stderr = run_approve(run_dir, decisions_file=str(decisions_file))

        assert code == 0, f"Failed: {stderr}"

        # Check approval file was created
        approval_path = Path(run_dir) / "approvals" / "prd.approved"
        assert approval_path.exists(), "Approval file not created"


def test_approve_pass_with_risk_entry_mentions_risk():
    """Test that approval entry mentions risk acceptance for PASS_WITH_RISK."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS_WITH_RISK")
        decisions_file = Path(tmpdir) / "decisions.md"
        decisions_file.write_text("# Decisions\n\n")

        code, stdout, stderr = run_approve(run_dir, decisions_file=str(decisions_file))

        assert code == 0

        # Check decisions entry
        entry = decisions_file.read_text()
        assert "Risk accepted" in entry or "risk" in entry.lower()


def test_approve_fail_refuses():
    """Test that FAIL verdict refuses without override."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")

        code, stdout, stderr = run_approve(run_dir)

        assert code == 1, f"Should have failed but didn't"
        assert "Traceback" not in stderr, f"Traceback in stderr: {stderr}"


def test_approve_null_verdict_refuses():
    """Test that null verdict refuses without override."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict=None)

        code, stdout, stderr = run_approve(run_dir)

        assert code == 1, f"Should have failed but didn't"
        assert "Traceback" not in stderr


def test_approve_fail_with_override():
    """Test that FAIL with override reason approves."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")
        decisions_file = Path(tmpdir) / "decisions.md"
        decisions_file.write_text("# Decisions\n\n")

        code, stdout, stderr = run_approve(
            run_dir,
            override_reason="Data is sufficient despite test failure",
            decisions_file=str(decisions_file)
        )

        assert code == 0, f"Failed: {stderr}"

        # Check approval file
        approval_path = Path(run_dir) / "approvals" / "prd.approved"
        with open(approval_path, 'r') as f:
            approval = json.load(f)

        assert approval["override_reason"] == "Data is sufficient despite test failure"


def test_approve_empty_override_reason_refuses():
    """Test that empty override reason is not allowed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")

        code, stdout, stderr = run_approve(
            run_dir,
            override_reason=""
        )

        assert code == 1, f"Should have failed but didn't"
        assert "Traceback" not in stderr


def test_approve_updates_state():
    """Test that approval updates state.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        code, stdout, stderr = run_approve(run_dir)
        assert code == 0

        # Check updated state
        state_path = Path(run_dir) / "state.json"
        with open(state_path, 'r') as f:
            state = json.load(f)

        assert state["status"] == "approved"
        assert state["approval_hashes"]["prd"] is not None
        assert "updated_at" in state


def test_approve_state_validates():
    """Test that updated state validates against schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        code, stdout, stderr = run_approve(run_dir)
        assert code == 0

        # Validate state against schema
        state_path = Path(run_dir) / "state.json"
        code = subprocess.run(
            [sys.executable, "scripts/validate_schema.py",
             "schemas/state.schema.json", str(state_path)],
            capture_output=True,
            cwd=Path(__file__).parent.parent
        ).returncode
        assert code == 0, "state.json failed schema validation"


def test_approve_appends_to_decisions():
    """Test that approval appends entry to decisions file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")
        decisions_file = Path(tmpdir) / "decisions.md"
        decisions_file.write_text("# Decisions\n\nExisting entry.\n")

        code, stdout, stderr = run_approve(run_dir, decisions_file=str(decisions_file))
        assert code == 0

        # Check decisions file
        content = decisions_file.read_text()
        assert "Existing entry" in content
        assert "PRD Approval" in content or "approval" in content.lower()
        assert "Product Owner" in content


def test_approve_prd_changed_after_audit():
    """Test that approval refuses if PRD hash differs from audit hash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        # Set artifact_hashes.prd to a different hash
        state_path = Path(run_dir) / "state.json"
        with open(state_path, 'r') as f:
            state = json.load(f)

        state["artifact_hashes"]["prd"] = "differenthash123"

        with open(state_path, 'w') as f:
            json.dump(state, f)

        code, stdout, stderr = run_approve(run_dir)

        assert code == 1, "Should have failed"
        assert "changed since" in stderr or "audit" in stderr.lower()
        assert "Traceback" not in stderr


def test_approve_prd_changed_refuses_even_with_override():
    """Test that PRD changed hash refuses approval even with override."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        # Set artifact_hashes.prd to a different hash
        state_path = Path(run_dir) / "state.json"
        with open(state_path, 'r') as f:
            state = json.load(f)

        state["artifact_hashes"]["prd"] = "differenthash123"

        with open(state_path, 'w') as f:
            json.dump(state, f)

        code, stdout, stderr = run_approve(
            run_dir,
            override_reason="I know what I'm doing"
        )

        assert code == 1, "Should have failed even with override"
        assert "Traceback" not in stderr


def test_approve_missing_prd():
    """Test that missing prd.md is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")
        (Path(run_dir) / "prd.md").unlink()

        code, stdout, stderr = run_approve(run_dir)

        assert code == 1, "Should have failed"
        assert "Traceback" not in stderr


def test_approve_unsupported_artifact():
    """Test that an unsupported artifact is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        code, stdout, stderr = run_approve(run_dir, artifact="bogus")

        assert code == 1, "Should have failed"
        assert "unknown artifact" in stderr
        assert "Traceback" not in stderr


def test_check_approval_after_approval():
    """Test that check_approval succeeds after approval."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        # Approve
        code, stdout, stderr = run_approve(run_dir)
        assert code == 0

        # Check approval
        code, stdout, stderr = run_check_approval(run_dir)

        assert code == 0, f"Failed: {stderr}"
        assert "approved" in stdout.lower()


def test_check_approval_missing():
    """Test that check_approval reports missing before approval."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        # Check without approval
        code, stdout, stderr = run_check_approval(run_dir)

        assert code == 1
        assert "missing" in stdout.lower()


def test_check_approval_stale():
    """Test that check_approval reports stale after PRD edit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        # Approve
        code, stdout, stderr = run_approve(run_dir)
        assert code == 0

        # Edit PRD
        prd_path = Path(run_dir) / "prd.md"
        prd_path.write_text("# PRD\n\nUpdated content.\n")

        # Check approval
        code, stdout, stderr = run_check_approval(run_dir)

        assert code == 1
        assert "stale" in stdout.lower()


def test_check_approval_invalid():
    """Test that check_approval reports invalid for corrupt file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        # Create a corrupt approval file
        approval_path = Path(run_dir) / "approvals" / "prd.approved"
        approval_path.write_text("not valid json")

        # Check approval
        code, stdout, stderr = run_check_approval(run_dir)

        assert code == 1
        assert "invalid" in stdout.lower()


def test_approve_state_missing_approval_hashes_leaves_no_approval_file():
    """Malformed state: one-line error, exit 1, no traceback, no approval file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")
        state_path = Path(run_dir) / "state.json"
        state = json.loads(state_path.read_text())
        del state["approval_hashes"]
        state_path.write_text(json.dumps(state))

        code, stdout, stderr = run_approve(run_dir)

        assert code == 1
        assert "Traceback" not in stderr
        assert not (Path(run_dir) / "approvals" / "prd.approved").exists()
        assert run_check_approval(run_dir)[0] != 0


def test_approve_unaudited_run_refuses():
    """No artifact_hashes.prd: refuse even with a PASS verdict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS", audited=False)

        code, stdout, stderr = run_approve(run_dir)

        assert code == 1
        assert "PRD has not been audited; run the audit first" in stderr
        assert not (Path(run_dir) / "approvals" / "prd.approved").exists()


def test_approve_unaudited_run_refuses_even_with_override():
    """Null verdict and no audit hash: override cannot bypass the audit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict=None, audited=False)

        code, stdout, stderr = run_approve(run_dir, override_reason="skip it")

        assert code == 1
        assert "PRD has not been audited; run the audit first" in stderr
        assert "Traceback" not in stderr
        assert not (Path(run_dir) / "approvals" / "prd.approved").exists()


def test_approve_audited_fail_can_still_be_overridden():
    """Override stays possible for an audited FAIL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL", audited=True)

        code, stdout, stderr = run_approve(run_dir, override_reason="Accepted by owner")

        assert code == 0, stderr
        assert (Path(run_dir) / "approvals" / "prd.approved").exists()


def _set_state_verdict(run_dir, key: str, value: str) -> None:
    path = Path(run_dir) / "state.json"
    state = json.loads(path.read_text())
    state["verdicts"][key] = value
    path.write_text(json.dumps(state))


def test_approve_prd_ignores_hand_edited_state_verdict():
    """Audit says FAIL, state.json edited to PASS: still refused without override."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")
        _set_state_verdict(run_dir, "prd", "PASS")

        code, stdout, stderr = run_approve(run_dir)

        assert code == 1
        assert "PRD verdict is FAIL" in stderr
        assert not (Path(run_dir) / "approvals" / "prd.approved").exists()


def test_approve_prd_fail_override_records_recomputed_verdict():
    """The approval file and decisions entry carry the recomputed verdict, not the state value."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")
        _set_state_verdict(run_dir, "prd", "PASS")
        decisions_file = Path(tmpdir) / "decisions.md"
        decisions_file.write_text("# Decisions\n\n")

        code, stdout, stderr = run_approve(run_dir, override_reason="Owner accepts", decisions_file=str(decisions_file))

        assert code == 0, stderr
        approval = json.loads((Path(run_dir) / "approvals" / "prd.approved").read_text())
        assert approval["verdict"] == "FAIL"
        assert approval["override_reason"] == "Owner accepts"
        assert "**Verdict**: FAIL" in decisions_file.read_text()


def test_approve_prd_missing_audit_file_refuses_even_with_override():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")
        (Path(run_dir) / "prd.audit.json").unlink()

        code, stdout, stderr = run_approve(run_dir, override_reason="ship it")

        assert code == 1
        assert "run the audit first" in stderr
        assert not (Path(run_dir) / "approvals" / "prd.approved").exists()


def test_approve_prd_stale_audit_refused_even_with_override():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")
        (Path(run_dir) / "prd.md").write_text("# PRD\n\nChanged.\n")

        code, stdout, stderr = run_approve(run_dir, override_reason="ship it")

        assert code == 1
        assert "PRD changed since it was audited" in stderr


def test_approve_ux_ignores_hand_edited_state_verdict(tmp_path):
    run = audited_run(tmp_path, scores={"req_coverage": 1})
    _set_state_verdict(run, "ux", "PASS")
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 1
    assert "UX verdict is FAIL" in stderr
    assert not (run / "approvals" / "ux.approved").exists()


def test_approve_ux_validator_errors_refuse_despite_perfect_scores(tmp_path):
    run = make_gate_run(tmp_path)
    (run / "ux" / "screens" / "SCR-002-details.html").unlink()  # invalid before the audit, so hashes match
    write_audit(run, build_audit(run, False))
    render(run)
    _set_state_verdict(run, "ux", "PASS")
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 1
    assert "UX verdict is FAIL" in stderr
    assert not (run / "approvals" / "ux.approved").exists()


def test_approve_ux_fail_override_records_recomputed_verdict(tmp_path):
    run = audited_run(tmp_path, scores={"req_coverage": 1})
    _set_state_verdict(run, "ux", "PASS")
    code, _, stderr = run_approve(str(run), "ux", override_reason="Demo only")
    assert code == 0, stderr
    approval = json.loads((run / "approvals" / "ux.approved").read_text())
    assert approval["verdict"] == "FAIL"
    assert "**Verdict**: FAIL" in decisions_of(run)


def test_approve_ux_missing_audit_file_refuses_even_with_override(tmp_path):
    run = audited_run(tmp_path)
    (run / "ux.audit.json").unlink()
    code, _, stderr = run_approve(str(run), "ux", override_reason="ship it")
    assert code == 1
    assert "run the audit first" in stderr
    assert not (run / "approvals" / "ux.approved").exists()


# --- Gate B: approve ux ------------------------------------------------------

def ux_state(run):
    return json.loads((run / "state.json").read_text())


def decisions_of(run):
    return (run / "decisions.test.md").read_text()


def test_approve_ux_refuses_without_prd_approval(tmp_path):
    run = audited_run(tmp_path, prd_approved=False)
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 1
    assert "PRD approval is not valid" in stderr
    assert not (run / "approvals" / "ux.approved").exists()


def test_approve_ux_refuses_when_prd_changed_after_prd_approval(tmp_path):
    run = audited_run(tmp_path)
    (run / "prd.md").write_text((run / "prd.md").read_text() + "\nextra\n")
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 1
    assert "PRD approval is not valid" in stderr


def test_approve_ux_refuses_without_audit(tmp_path):
    run = make_gate_run(tmp_path)
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 1
    assert "not been audited" in stderr


def test_approve_ux_refuses_without_audit_even_with_override(tmp_path):
    run = make_gate_run(tmp_path)
    code, _, stderr = run_approve(str(run), "ux", override_reason="ship it")
    assert code == 1
    assert "not been audited" in stderr


def test_approve_ux_refuses_when_ux_changed_since_audit(tmp_path):
    run = audited_run(tmp_path)
    flows = run / "ux" / "flows.md"
    flows.write_text(flows.read_text() + "\n")
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 1
    assert "UX changed since it was audited" in stderr
    assert not (run / "approvals" / "ux.approved").exists()


def test_approve_ux_fail_refuses_without_override(tmp_path):
    run = audited_run(tmp_path, scores={"req_coverage": 1})
    assert ux_state(run)["verdicts"]["ux"] == "FAIL"
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 1
    assert "use --override" in stderr
    assert not (run / "approvals" / "ux.approved").exists()


def test_approve_ux_fail_empty_override_refuses(tmp_path):
    run = audited_run(tmp_path, scores={"req_coverage": 1})
    code, _, stderr = run_approve(str(run), "ux", override_reason="  ")
    assert code == 1
    assert "use --override" in stderr


def test_approve_ux_fail_succeeds_with_override_reason(tmp_path):
    run = audited_run(tmp_path, scores={"req_coverage": 1})
    code, _, stderr = run_approve(str(run), "ux", override_reason="Demo only")
    assert code == 0, stderr
    approval = json.loads((run / "approvals" / "ux.approved").read_text())
    assert approval["verdict"] == "FAIL"
    assert approval["override_reason"] == "Demo only"
    assert "Override reason**: Demo only" in decisions_of(run)


def test_approve_ux_success_writes_everything(tmp_path):
    run = audited_run(tmp_path)
    prd_before = (run / "prd.md").read_bytes()
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 0, stderr

    approval = json.loads((run / "approvals" / "ux.approved").read_text())
    assert approval["artifact"] == "ux"
    assert approval["sha256"] == ux_hash(run)
    assert approval["prd_sha256"] == sha(run / "prd.md")
    assert approval["verdict"] == "PASS"
    assert approval["override_reason"] is None
    assert approval["approved_at"].endswith("Z")

    state = ux_state(run)
    assert state["approval_hashes"]["ux"] == ux_hash(run)
    assert state["approval_hashes"]["prd"] is None  # Gate B does not touch the PRD entry
    assert state["status"] == "approved"

    trace = (run / "traceability.md").read_text()
    assert "| REQ | Priority | Screens | Jira |" in trace
    assert "SCR-001" in trace
    assert "not yet created (Stage 3)" in trace

    decisions = decisions_of(run)
    assert "UX Approval" in decisions
    assert "**Run**: run-1" in decisions
    assert "**Verdict**: PASS" in decisions

    assert (run / "prd.md").read_bytes() == prd_before


def test_approve_ux_pass_with_risk_notes_risk(tmp_path):
    run = audited_run(tmp_path, scores={"copy_clarity": 2})
    code, _, stderr = run_approve(str(run), "ux")
    assert code == 0, stderr
    assert "Risk accepted." in decisions_of(run)


def test_approve_ux_does_not_touch_real_decisions_file(tmp_path):
    run = audited_run(tmp_path)
    repo_decisions = Path(__file__).parent.parent / "decisions.md"
    before = repo_decisions.read_bytes() if repo_decisions.exists() else None
    run_approve(str(run), "ux")
    after = repo_decisions.read_bytes() if repo_decisions.exists() else None
    assert before == after


def test_approve_unknown_artifact_unavailable(tmp_path):
    run = audited_run(tmp_path)
    code, _, stderr = run_approve(str(run), "bogus")
    assert code == 1
    assert "unknown artifact 'bogus': use prd, ux or tickets" in stderr


def test_check_approval_ux_approved(tmp_path):
    run = audited_run(tmp_path)
    run_approve(str(run), "ux")
    code, stdout, _ = run_check_approval(str(run), "ux")
    assert (code, stdout.strip()) == (0, "approved")


def test_check_approval_ux_missing(tmp_path):
    run = audited_run(tmp_path)
    code, stdout, _ = run_check_approval(str(run), "ux")
    assert code == 1
    assert stdout.startswith("missing")


def test_check_approval_ux_stale_after_screen_edit(tmp_path):
    run = audited_run(tmp_path)
    run_approve(str(run), "ux")
    screen = run / "ux" / "screens" / "SCR-002-details.html"
    screen.write_text(screen.read_text() + "\n<!-- edit -->\n")
    code, stdout, _ = run_check_approval(str(run), "ux")
    assert code == 1
    assert stdout.startswith("stale")


def test_check_approval_ux_stale_after_prd_edit(tmp_path):
    run = audited_run(tmp_path)
    run_approve(str(run), "ux")
    (run / "prd.md").write_text((run / "prd.md").read_text() + "\nedit\n")
    code, stdout, _ = run_check_approval(str(run), "ux")
    assert code == 1
    assert stdout.startswith("stale")


def test_check_approval_ux_invalid_on_corrupt_file(tmp_path):
    run = audited_run(tmp_path)
    run_approve(str(run), "ux")
    (run / "approvals" / "ux.approved").write_text("{not json")
    code, stdout, _ = run_check_approval(str(run), "ux")
    assert code == 1
    assert stdout.startswith("invalid")


def test_check_approval_ux_invalid_without_prd_sha256(tmp_path):
    run = audited_run(tmp_path)
    run_approve(str(run), "ux")
    path = run / "approvals" / "ux.approved"
    approval = json.loads(path.read_text())
    del approval["prd_sha256"]
    path.write_text(json.dumps(approval))
    code, stdout, _ = run_check_approval(str(run), "ux")
    assert code == 1
    assert stdout.startswith("invalid")


def test_check_approval_unknown_artifact_is_invalid(tmp_path):
    run = audited_run(tmp_path)
    code, stdout, _ = run_check_approval(str(run), "bogus")
    assert code == 1
    assert stdout.startswith("invalid")


def test_approval_status_function_matches_cli(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from check_approval import approval_status
    run = audited_run(tmp_path)
    assert approval_status(str(run), "ux")[0] is False
    approve_prd_file(run)
    run_approve(str(run), "ux")
    assert approval_status(str(run), "ux") == (True, "approved")
    assert approval_status(str(run), "prd") == (True, "approved")


# --- Gate C: approve tickets -------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))
from tickets_helpers import approve_ux_file, make_tickets_run, valid_manifest, write_manifest  # noqa: E402
from ux_gate_helpers import write_state  # noqa: E402


def tickets_run(tmp_path, ai=False):
    run = make_tickets_run(tmp_path, ai=ai)
    write_state(run)
    return run


def test_approve_tickets_refuses_without_ux_approval(tmp_path):
    run = tickets_run(tmp_path)
    (run / "approvals" / "ux.approved").unlink()
    code, _, stderr = run_approve(str(run), "tickets")
    assert code == 1
    assert "UX approval is not valid" in stderr
    assert not (run / "approvals" / "tickets.approved").exists()


def test_approve_tickets_refuses_with_stale_ux(tmp_path):
    run = tickets_run(tmp_path)
    screen = run / "ux" / "screens" / "SCR-002-details.html"
    screen.write_text(screen.read_text() + "\n<!-- edit -->\n")
    code, _, stderr = run_approve(str(run), "tickets")
    assert code == 1
    assert "UX approval is not valid" in stderr
    assert "stale" in stderr
    assert not (run / "approvals" / "tickets.approved").exists()


def test_approve_tickets_refuses_with_validator_errors(tmp_path):
    run = tickets_run(tmp_path)
    m = valid_manifest(run, False)
    m["epics"][0]["children"][0]["acceptance_criteria"].pop()
    write_manifest(run, m)
    code, _, stderr = run_approve(str(run), "tickets")
    assert code == 1
    assert "Definition of Ready" in stderr
    assert "T-001" in stderr
    assert not (run / "approvals" / "tickets.approved").exists()


def test_approve_tickets_refuses_override(tmp_path):
    run = tickets_run(tmp_path)
    code, _, stderr = run_approve(str(run), "tickets", override_reason="ship it")
    assert code == 1
    assert "--override is not allowed for tickets" in stderr
    assert not (run / "approvals" / "tickets.approved").exists()


def test_approve_tickets_success_writes_everything(tmp_path):
    from tickets_hash import tickets_hash
    run = tickets_run(tmp_path)
    prd_before = (run / "prd.md").read_bytes()
    ux_before = {p: p.read_bytes() for p in sorted((run / "ux").rglob("*")) if p.is_file()}
    code, _, stderr = run_approve(str(run), "tickets")
    assert code == 0, stderr
    approval = json.loads((run / "approvals" / "tickets.approved").read_text())
    manifest = json.loads((run / "tickets.manifest.json").read_text())
    count = sum(1 + len(e["children"]) for e in manifest["epics"])
    assert approval["artifact"] == "tickets"
    assert approval["sha256"] == tickets_hash(run)
    assert approval["prd_sha256"] == sha(run / "prd.md")
    assert approval["ux_sha256"] == ux_hash(run)
    assert approval["ticket_count"] == count
    assert "approved_at" in approval
    state = ux_state(run)
    assert state["approval_hashes"]["tickets"] == tickets_hash(run)
    assert state["stage"] == "stage3"
    assert state["status"] == "approved"
    assert "(not yet published)" in (run / "traceability.md").read_text()
    assert "Tickets Approval" in decisions_of(run)
    assert (run / "prd.md").read_bytes() == prd_before
    assert {p: p.read_bytes() for p in sorted((run / "ux").rglob("*")) if p.is_file()} == ux_before


def test_approve_tickets_does_not_touch_real_decisions_file(tmp_path):
    run = tickets_run(tmp_path)
    repo_decisions = Path(__file__).parent.parent / "decisions.md"
    before = repo_decisions.read_bytes() if repo_decisions.exists() else None
    run_approve(str(run), "tickets")
    after = repo_decisions.read_bytes() if repo_decisions.exists() else None
    assert before == after


def _approved_tickets(tmp_path):
    run = tickets_run(tmp_path)
    code, _, stderr = run_approve(str(run), "tickets")
    assert code == 0, stderr
    return run


def test_check_approval_tickets_approved(tmp_path):
    run = _approved_tickets(tmp_path)
    code, stdout, _ = run_check_approval(str(run), "tickets")
    assert (code, stdout.strip()) == (0, "approved")


def test_check_approval_tickets_missing(tmp_path):
    run = tickets_run(tmp_path)
    code, stdout, _ = run_check_approval(str(run), "tickets")
    assert code == 1
    assert stdout.startswith("missing")


def test_check_approval_tickets_stale_after_manifest_edit(tmp_path):
    run = _approved_tickets(tmp_path)
    m = json.loads((run / "tickets.manifest.json").read_text())
    m["epics"][0]["children"][0]["priority"] = "Low"
    write_manifest(run, m)
    code, stdout, _ = run_check_approval(str(run), "tickets")
    assert code == 1
    assert stdout.startswith("stale")


def test_check_approval_tickets_stale_after_screen_edit(tmp_path):
    run = _approved_tickets(tmp_path)
    screen = run / "ux" / "screens" / "SCR-002-details.html"
    screen.write_text(screen.read_text() + "\n<!-- edit -->\n")
    code, stdout, _ = run_check_approval(str(run), "tickets")
    assert code == 1
    assert stdout.startswith("stale")


def test_check_approval_tickets_stale_after_prd_edit(tmp_path):
    run = _approved_tickets(tmp_path)
    (run / "prd.md").write_text((run / "prd.md").read_text() + "\nedit\n")
    code, stdout, _ = run_check_approval(str(run), "tickets")
    assert code == 1
    assert stdout.startswith("stale")


def test_check_approval_tickets_not_stale_after_jira_key_change(tmp_path):
    run = _approved_tickets(tmp_path)
    m = json.loads((run / "tickets.manifest.json").read_text())
    m["epics"][0]["jira_key"] = "PROJ-1"
    m["epics"][0]["children"][0]["jira_key"] = "PROJ-2"
    write_manifest(run, m)
    code, stdout, _ = run_check_approval(str(run), "tickets")
    assert (code, stdout.strip()) == (0, "approved")


def test_check_approval_tickets_invalid_on_corrupt_file(tmp_path):
    run = _approved_tickets(tmp_path)
    (run / "approvals" / "tickets.approved").write_text("{not json")
    code, stdout, _ = run_check_approval(str(run), "tickets")
    assert code == 1
    assert stdout.startswith("invalid")


# --- The audit file's own hash decides staleness ------------------------------

def _set_state_artifact_hash(run_dir, key: str, value: str) -> None:
    path = Path(run_dir) / "state.json"
    state = json.loads(path.read_text())
    state["artifact_hashes"][key] = value
    path.write_text(json.dumps(state))


def test_approve_prd_stale_audit_refused_when_state_hash_hand_set():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")
        prd = Path(run_dir) / "prd.md"
        prd.write_text("# PRD\n\nChanged after audit.\n")
        _set_state_artifact_hash(run_dir, "prd", hashlib.sha256(prd.read_bytes()).hexdigest())

        code, _, stderr = run_approve(run_dir, override_reason="ship it")

        assert code == 1
        assert "PRD changed since it was audited; run the audit again" in stderr
        assert not (Path(run_dir) / "approvals" / "prd.approved").exists()


def test_approve_prd_audit_file_hash_altered_refused_with_override():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")
        audit_path = Path(run_dir) / "prd.audit.json"
        audit = json.loads(audit_path.read_text())
        audit["prd_hash"] = "0" * 64
        audit_path.write_text(json.dumps(audit))

        code, _, stderr = run_approve(run_dir, override_reason="ship it")

        assert code == 1
        assert "PRD changed since it was audited; run the audit again" in stderr
        assert not (Path(run_dir) / "approvals" / "prd.approved").exists()


def test_approve_prd_legit_fail_with_override_still_approves():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="FAIL")

        code, _, stderr = run_approve(run_dir, override_reason="Owner accepts")

        assert code == 0, stderr
        assert (Path(run_dir) / "approvals" / "prd.approved").exists()


def test_approve_ux_stale_audit_refused_when_state_hash_hand_set(tmp_path):
    run = audited_run(tmp_path, scores={"req_coverage": 1})
    flows = run / "ux" / "flows.md"
    flows.write_text(flows.read_text() + "\nedited after audit\n")
    _set_state_artifact_hash(run, "ux", ux_hash(run))
    code, _, stderr = run_approve(str(run), "ux", override_reason="ship it")
    assert code == 1
    assert "UX changed since it was audited; run the audit again" in stderr
    assert not (run / "approvals" / "ux.approved").exists()


def test_approve_ux_audit_file_hash_altered_refused_with_override(tmp_path):
    run = audited_run(tmp_path, scores={"req_coverage": 1})
    audit = json.loads((run / "ux.audit.json").read_text())
    audit["ux_hash"] = "0" * 64
    (run / "ux.audit.json").write_text(json.dumps(audit))
    code, _, stderr = run_approve(str(run), "ux", override_reason="ship it")
    assert code == 1
    assert "UX changed since it was audited; run the audit again" in stderr
    assert not (run / "approvals" / "ux.approved").exists()


def test_approve_ux_legit_fail_with_override_still_approves(tmp_path):
    run = audited_run(tmp_path, scores={"req_coverage": 1})
    code, _, stderr = run_approve(str(run), "ux", override_reason="Demo only")
    assert code == 0, stderr
    assert (run / "approvals" / "ux.approved").exists()
