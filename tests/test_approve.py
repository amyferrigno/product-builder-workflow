"""Test approve.py script."""

import hashlib
import json
import tempfile
import subprocess
import sys
from pathlib import Path


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
    """Test that unsupported artifact (ux) is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(tmpdir, verdict="PASS")

        code, stdout, stderr = run_approve(run_dir, artifact="ux")

        assert code == 1, "Should have failed"
        assert "milestone" in stderr or "not available" in stderr
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
