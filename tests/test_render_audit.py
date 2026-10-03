"""Test render_audit.py script."""

import sys
import json
import subprocess
from pathlib import Path
import tempfile
import hashlib

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_render_audit_writes_markdown_and_updates_state():
    """Test that render_audit writes markdown and updates state."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)

        # Create state.json
        state = {
            "run_id": "test-run",
            "stage": "stage1",
            "status": "in_progress",
            "verdicts": {"prd": None},
            "artifact_hashes": {},
            "approval_hashes": {},
            "jira_keys": {},
            "updated_at": "2023-01-01T00:00:00Z"
        }
        state_path = run_dir / "state.json"
        with open(state_path, 'w') as f:
            json.dump(state, f)

        # Create PRD
        prd_content = "# Test PRD\n"
        prd_path = run_dir / "prd.md"
        with open(prd_path, 'w') as f:
            f.write(prd_content)

        prd_hash = hashlib.sha256(prd_content.encode()).hexdigest()

        # Create audit JSON
        audit = {
            "run_id": "test-run",
            "prd_hash": prd_hash,
            "ai_feature": False,
            "dimensions": [
                {"id": "problem_clarity", "score": 3, "justification": "Clear"},
                {"id": "evidence_strength", "score": 3, "justification": "Good"},
                {"id": "strategic_fit", "score": 3, "justification": "Aligned"},
                {"id": "success_metrics", "score": 3, "justification": "Defined"},
                {"id": "scope_discipline", "score": 3, "justification": "Tight"},
                {"id": "feasibility", "score": 3, "justification": "Feasible"},
                {"id": "testability", "score": 3, "justification": "Testable"},
                {"id": "risk_coverage", "score": 3, "justification": "Covered"},
                {"id": "traceability", "score": 3, "justification": "Traced"},
            ],
            "hallucination_check": {}
        }

        audit_path = run_dir / "prd.audit.json"
        with open(audit_path, 'w') as f:
            json.dump(audit, f)

        # Run render_audit
        result = subprocess.run(
            [sys.executable, "scripts/render_audit.py", str(run_dir)],
            capture_output=True,
            cwd=repo_root
        )

        assert result.returncode == 0
        assert b"PASS" in result.stdout

        # Check markdown was written
        audit_md_path = run_dir / "prd.audit.md"
        assert audit_md_path.exists()

        markdown_content = audit_md_path.read_text()
        assert "PRD Audit: PASS" in markdown_content
        assert "Scores" in markdown_content

        # Check state was updated
        with open(state_path, 'r') as f:
            updated_state = json.load(f)

        assert updated_state["verdicts"]["prd"] == "PASS"
        assert updated_state["artifact_hashes"]["prd"] == prd_hash
        assert "prd_audit" in updated_state["artifact_hashes"]
        assert updated_state["status"] == "awaiting_approval"


def test_render_audit_with_fail_verdict():
    """Test that render_audit with FAIL verdict stays in_progress."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)

        # Create state.json
        state = {
            "run_id": "test-run",
            "stage": "stage1",
            "status": "in_progress",
            "verdicts": {"prd": None},
            "artifact_hashes": {},
            "approval_hashes": {},
            "jira_keys": {},
            "updated_at": "2023-01-01T00:00:00Z"
        }
        state_path = run_dir / "state.json"
        with open(state_path, 'w') as f:
            json.dump(state, f)

        # Create PRD
        prd_content = "# Test PRD\n"
        prd_path = run_dir / "prd.md"
        with open(prd_path, 'w') as f:
            f.write(prd_content)

        prd_hash = hashlib.sha256(prd_content.encode()).hexdigest()

        # Create audit JSON with a dimension at 2
        audit = {
            "run_id": "test-run",
            "prd_hash": prd_hash,
            "ai_feature": False,
            "dimensions": [
                {"id": "problem_clarity", "score": 1, "justification": "Missing", "fix": "Define", "sections": ["3"]},
                {"id": "evidence_strength", "score": 3, "justification": "Good"},
                {"id": "strategic_fit", "score": 3, "justification": "Aligned"},
                {"id": "success_metrics", "score": 3, "justification": "Defined"},
                {"id": "scope_discipline", "score": 3, "justification": "Tight"},
                {"id": "feasibility", "score": 3, "justification": "Feasible"},
                {"id": "testability", "score": 3, "justification": "Testable"},
                {"id": "risk_coverage", "score": 3, "justification": "Covered"},
                {"id": "traceability", "score": 3, "justification": "Traced"},
            ],
            "hallucination_check": {}
        }

        audit_path = run_dir / "prd.audit.json"
        with open(audit_path, 'w') as f:
            json.dump(audit, f)

        # Run render_audit
        result = subprocess.run(
            [sys.executable, "scripts/render_audit.py", str(run_dir)],
            capture_output=True,
            cwd=repo_root
        )

        assert result.returncode == 1
        assert b"FAIL" in result.stdout

        # Check state
        with open(state_path, 'r') as f:
            updated_state = json.load(f)

        assert updated_state["verdicts"]["prd"] == "FAIL"
        assert updated_state["status"] == "in_progress"


def test_render_audit_with_fixes_section():
    """Test that render_audit writes fixes section for dimensions below 3."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)

        # Create state.json
        state = {
            "run_id": "test-run",
            "stage": "stage1",
            "status": "in_progress",
            "verdicts": {"prd": None},
            "artifact_hashes": {},
            "approval_hashes": {},
            "jira_keys": {},
            "updated_at": "2023-01-01T00:00:00Z"
        }
        state_path = run_dir / "state.json"
        with open(state_path, 'w') as f:
            json.dump(state, f)

        # Create PRD
        prd_content = "# Test PRD\n"
        prd_path = run_dir / "prd.md"
        with open(prd_path, 'w') as f:
            f.write(prd_content)

        prd_hash = hashlib.sha256(prd_content.encode()).hexdigest()

        # Create audit JSON with fixes
        audit = {
            "run_id": "test-run",
            "prd_hash": prd_hash,
            "ai_feature": False,
            "dimensions": [
                {"id": "problem_clarity", "score": 3, "justification": "Clear"},
                {"id": "evidence_strength", "score": 2, "justification": "Weak", "fix": "Add more data", "sections": ["6a"]},
                {"id": "strategic_fit", "score": 3, "justification": "Aligned"},
                {"id": "success_metrics", "score": 3, "justification": "Defined"},
                {"id": "scope_discipline", "score": 3, "justification": "Tight"},
                {"id": "feasibility", "score": 3, "justification": "Feasible"},
                {"id": "testability", "score": 3, "justification": "Testable"},
                {"id": "risk_coverage", "score": 3, "justification": "Covered"},
                {"id": "traceability", "score": 3, "justification": "Traced"},
            ],
            "hallucination_check": {}
        }

        audit_path = run_dir / "prd.audit.json"
        with open(audit_path, 'w') as f:
            json.dump(audit, f)

        # Run render_audit
        result = subprocess.run(
            [sys.executable, "scripts/render_audit.py", str(run_dir)],
            capture_output=True,
            cwd=repo_root
        )

        # Check markdown includes fixes
        audit_md_path = run_dir / "prd.audit.md"
        markdown_content = audit_md_path.read_text()

        assert "Fixes needed" in markdown_content
        assert "evidence_strength" in markdown_content
        assert "Add more data" in markdown_content
        assert "Flagged sections" in markdown_content
        assert "6a" in markdown_content


def test_render_audit_with_hallucinations():
    """Test that render_audit includes hallucination findings."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)

        # Create state.json
        state = {
            "run_id": "test-run",
            "stage": "stage1",
            "status": "in_progress",
            "verdicts": {"prd": None},
            "artifact_hashes": {},
            "approval_hashes": {},
            "jira_keys": {},
            "updated_at": "2023-01-01T00:00:00Z"
        }
        state_path = run_dir / "state.json"
        with open(state_path, 'w') as f:
            json.dump(state, f)

        # Create PRD
        prd_content = "# Test PRD\n"
        prd_path = run_dir / "prd.md"
        with open(prd_path, 'w') as f:
            f.write(prd_content)

        prd_hash = hashlib.sha256(prd_content.encode()).hexdigest()

        # Create audit JSON with hallucinations
        audit = {
            "run_id": "test-run",
            "prd_hash": prd_hash,
            "ai_feature": False,
            "dimensions": [
                {"id": "problem_clarity", "score": 3, "justification": "Clear"},
                {"id": "evidence_strength", "score": 3, "justification": "Good"},
                {"id": "strategic_fit", "score": 3, "justification": "Aligned"},
                {"id": "success_metrics", "score": 3, "justification": "Defined"},
                {"id": "scope_discipline", "score": 3, "justification": "Tight"},
                {"id": "feasibility", "score": 3, "justification": "Feasible"},
                {"id": "testability", "score": 3, "justification": "Testable"},
                {"id": "risk_coverage", "score": 3, "justification": "Covered"},
                {"id": "traceability", "score": 3, "justification": "Traced"},
            ],
            "hallucination_check": {
                "unsupported_numbers": ["42% in section 8"],
                "unsupported_quotes": ["'Made up quote' in section 6b"]
            }
        }

        audit_path = run_dir / "prd.audit.json"
        with open(audit_path, 'w') as f:
            json.dump(audit, f)

        # Run render_audit
        result = subprocess.run(
            [sys.executable, "scripts/render_audit.py", str(run_dir)],
            capture_output=True,
            cwd=repo_root
        )

        assert result.returncode == 1
        assert b"FAIL" in result.stdout

        # Check markdown includes hallucinations
        audit_md_path = run_dir / "prd.audit.md"
        markdown_content = audit_md_path.read_text()

        assert "Hallucination check" in markdown_content
        assert "Unsupported numbers" in markdown_content
        assert "42% in section 8" in markdown_content
        assert "Unsupported quotes" in markdown_content
