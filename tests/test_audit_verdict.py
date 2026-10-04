"""Test audit_verdict.py script and compute_verdict function."""

import sys
import json
import subprocess
from pathlib import Path
import tempfile
import hashlib

# Import the function directly for unit tests
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from audit_verdict import compute_verdict, load_rubric, prd_has_ai_addendum


def load_test_rubric():
    """Load the test rubric."""
    repo_root = Path(__file__).parent.parent
    return load_rubric(repo_root)


def test_all_pass_gives_pass():
    """Test that all dimensions at 3 or 4 with no hallucinations gives PASS."""
    rubric = load_test_rubric()

    audit = {
        "run_id": "test-run",
        "prd_hash": "abc123",
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

    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "PASS"
    assert len(reasons) == 0


def test_non_blocking_at_2_gives_pass_with_risk():
    """Test that a non-blocking dimension at 2 gives PASS_WITH_RISK."""
    rubric = load_test_rubric()

    audit = {
        "run_id": "test-run",
        "prd_hash": "abc123",
        "ai_feature": False,
        "dimensions": [
            {"id": "problem_clarity", "score": 3, "justification": "Clear"},
            {"id": "evidence_strength", "score": 2, "justification": "Weak"},
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

    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "PASS_WITH_RISK"


def test_blocking_at_2_gives_fail():
    """Test that a blocking dimension at 2 gives FAIL."""
    rubric = load_test_rubric()

    audit = {
        "run_id": "test-run",
        "prd_hash": "abc123",
        "ai_feature": False,
        "dimensions": [
            {"id": "problem_clarity", "score": 2, "justification": "Weak", "fix": "Clarify", "sections": ["3"]},
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

    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "FAIL"
    assert any("problem_clarity" in r for r in reasons)


def test_any_dimension_at_1_gives_fail():
    """Test that any dimension at 1 gives FAIL."""
    rubric = load_test_rubric()

    audit = {
        "run_id": "test-run",
        "prd_hash": "abc123",
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

    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "FAIL"
    assert any("scores 1" in r for r in reasons)


def test_unsupported_numbers_hallucination_gives_fail():
    """Test that unsupported numbers hallucination gives FAIL."""
    rubric = load_test_rubric()

    audit = {
        "run_id": "test-run",
        "prd_hash": "abc123",
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
            "unsupported_numbers": ["42% in section 8"]
        }
    }

    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "FAIL"
    assert any("unsupported numbers" in r for r in reasons)


def test_stale_prd_hash_gives_fail():
    """Test that stale PRD hash gives FAIL."""
    rubric = load_test_rubric()

    audit = {
        "run_id": "test-run",
        "prd_hash": "old_hash",
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

    verdict, reasons = compute_verdict(audit, rubric, "new_hash", False)
    assert verdict == "FAIL"
    assert any("hash mismatch" in r for r in reasons)


def test_ai_feature_requires_ai_dimensions():
    """Test that ai_feature=true requires AI dimensions."""
    rubric = load_test_rubric()

    audit = {
        "run_id": "test-run",
        "prd_hash": "abc123",
        "ai_feature": True,
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
            # Missing AI dimensions
        ],
        "hallucination_check": {}
    }

    verdict, reasons = compute_verdict(audit, rubric, "abc123", True)
    assert verdict == "FAIL"
    assert any("Missing required dimension" in r for r in reasons)


def test_ai_feature_false_ignores_ai_dimensions():
    """Test that ai_feature=false ignores AI dimensions."""
    rubric = load_test_rubric()

    audit = {
        "run_id": "test-run",
        "prd_hash": "abc123",
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
            # AI dimensions present but ignored
            {"id": "ai_appropriateness", "score": 1, "justification": "Bad"},
        ],
        "hallucination_check": {}
    }

    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "PASS"
    assert len(reasons) == 0


def test_cli_with_valid_audit_json():
    """Test the CLI with valid audit JSON."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)

        # Create audit JSON
        audit = {
            "run_id": "test-run",
            "prd_hash": "abc123",
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

        # Create PRD with hash abc123
        prd_path = run_dir / "prd.md"
        prd_content = "# Test PRD\n"
        prd_hash = hashlib.sha256(prd_content.encode()).hexdigest()
        audit["prd_hash"] = prd_hash
        with open(audit_path, 'w') as f:
            json.dump(audit, f)
        with open(prd_path, 'w') as f:
            f.write(prd_content)

        result = subprocess.run(
            [sys.executable, "scripts/audit_verdict.py", str(run_dir)],
            capture_output=True,
            cwd=repo_root
        )

        assert result.returncode == 0
        assert b"PASS" in result.stdout


def test_cli_with_missing_audit_file():
    """Test CLI with missing audit file exits 2."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)

        # Create only PRD
        prd_path = run_dir / "prd.md"
        with open(prd_path, 'w') as f:
            f.write("# Test PRD\n")

        result = subprocess.run(
            [sys.executable, "scripts/audit_verdict.py", str(run_dir)],
            capture_output=True,
            cwd=repo_root
        )

        assert result.returncode == 2
        assert b"Error" in result.stderr
        assert b"Traceback" not in result.stderr


def test_cli_with_invalid_json():
    """Test CLI with invalid JSON exits 2 with no traceback."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)

        # Create invalid JSON
        audit_path = run_dir / "prd.audit.json"
        with open(audit_path, 'w') as f:
            f.write("{ invalid json")

        # Create PRD
        prd_path = run_dir / "prd.md"
        with open(prd_path, 'w') as f:
            f.write("# Test PRD\n")

        result = subprocess.run(
            [sys.executable, "scripts/audit_verdict.py", str(run_dir)],
            capture_output=True,
            cwd=repo_root
        )

        assert result.returncode == 2
        assert b"Error" in result.stderr
        assert b"Traceback" not in result.stderr


NON_AI_IDS = [
    "problem_clarity", "evidence_strength", "strategic_fit", "success_metrics",
    "scope_discipline", "feasibility", "testability", "risk_coverage", "traceability",
]
AI_IDS = ["ai_appropriateness", "ai_ux_uncertainty", "ai_eval_plan"]


def make_audit(ids, ai_feature=False, hallucination=None):
    return {
        "run_id": "test-run",
        "prd_hash": "abc123",
        "ai_feature": ai_feature,
        "dimensions": [{"id": i, "score": 3, "justification": "ok"} for i in ids],
        "hallucination_check": hallucination or {},
    }


def test_duplicate_dimension_gives_fail():
    """A repeated dimension id cannot hide a failing score."""
    rubric = load_test_rubric()
    audit = make_audit(NON_AI_IDS)
    audit["dimensions"][0]["score"] = 1
    audit["dimensions"].append({"id": "problem_clarity", "score": 3, "justification": "again"})
    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "FAIL"
    assert "Duplicate dimension: problem_clarity" in reasons


def test_ai_flag_false_but_prd_has_addendum_gives_fail():
    """Auditor says not AI but the PRD has an AI addendum."""
    rubric = load_test_rubric()
    audit = make_audit(NON_AI_IDS, ai_feature=False)
    verdict, reasons = compute_verdict(audit, rubric, "abc123", True)
    assert verdict == "FAIL"
    assert any("ai_feature mismatch: audit says false but the PRD has an AI addendum" in r for r in reasons)


def test_ai_flag_true_but_prd_has_no_addendum_gives_fail():
    """Auditor says AI but the PRD has no AI addendum."""
    rubric = load_test_rubric()
    audit = make_audit(NON_AI_IDS + AI_IDS, ai_feature=True)
    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "FAIL"
    assert any("ai_feature mismatch: audit says true but the PRD has no AI addendum" in r for r in reasons)


def test_ai_flag_true_and_addendum_present_passes():
    rubric = load_test_rubric()
    audit = make_audit(NON_AI_IDS + AI_IDS, ai_feature=True)
    verdict, _ = compute_verdict(audit, rubric, "abc123", True)
    assert verdict == "PASS"


def test_prd_has_ai_addendum_detects_heading():
    assert prd_has_ai_addendum("# PRD\n\n## A1. 5-Gate verdict\n")
    assert not prd_has_ai_addendum("# PRD\n\n## 1. Summary\nSee A1. later\n")


def test_unsupported_quotes_gives_fail_with_reason():
    rubric = load_test_rubric()
    audit = make_audit(NON_AI_IDS, hallucination={"unsupported_quotes": ["we love it"]})
    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "FAIL"
    assert "Hallucination: unsupported quotes: we love it" in reasons


def test_unsupported_decisions_gives_fail_with_reason():
    rubric = load_test_rubric()
    audit = make_audit(NON_AI_IDS, hallucination={"unsupported_decisions": ["ship in May"]})
    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "FAIL"
    assert "Hallucination: unsupported decisions: ship in May" in reasons


def test_missing_non_ai_dimension_gives_fail_with_reason():
    rubric = load_test_rubric()
    audit = make_audit([i for i in NON_AI_IDS if i != "feasibility"])
    verdict, reasons = compute_verdict(audit, rubric, "abc123", False)
    assert verdict == "FAIL"
    assert "Missing required dimension: feasibility" in reasons


def test_prd_has_ai_addendum_tolerates_heading_whitespace():
    """Every heading form the PRD validator accepts must count as an addendum."""
    for heading in ("## A1. x", "##  A1. x", "##\tA3. x", " ## A10. x", "### A2. x"):
        assert prd_has_ai_addendum("intro\n" + heading + "\n") is True, heading
    assert prd_has_ai_addendum("## 1. Header\nSee A1. below\n") is False

