"""Test validate_problem.py script."""

import json
import tempfile
import subprocess
import sys
from pathlib import Path


def create_test_run(tmpdir: str, extraction: dict, problem_md: str, run_id: str) -> str:
    """Helper to create a test run directory."""
    run_path = Path(tmpdir) / "runs" / run_id
    run_path.mkdir(parents=True)

    notes_dir = run_path / "00-notes"
    notes_dir.mkdir()

    # Create minimal numbered notes
    (notes_dir / "notes.numbered.md").write_text("1: Test notes")

    # Create extraction.json
    (run_path / "01-extraction.json").write_text(json.dumps(extraction, indent=2))

    # Create problem.md
    (run_path / "02-problem.md").write_text(problem_md)

    return str(run_path)


def run_validator(run_dir: str) -> tuple:
    """Run validator and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "scripts/validate_problem.py", run_dir],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    return result.returncode, result.stdout, result.stderr


def test_validate_problem_passes_for_valid():
    """Test that valid problem passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [{"id": "P-1", "text": "Test", "source_lines": [1], "type": "stated"}],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test problem
    validation_status: VALIDATED
    missing_evidence: []
    source_items: [P-1]
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test statement

## Who has it
Everyone

## Exact scenario
Test scenario

## Current workaround
No workaround

## Why now
It's urgent

## Strategic fit
It fits

## Validation status
VALIDATED

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0, f"Validation failed: {stdout}{stderr}"


def test_validate_problem_fails_missing_heading():
    """Test that missing required heading fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [{"id": "P-1", "text": "Test", "source_lines": [1], "type": "stated"}],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Missing required heading" in stdout


def test_validate_problem_fails_unknown_extraction_id():
    """Test that unknown extraction ID fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [{"id": "P-1", "text": "Test", "source_lines": [1], "type": "stated"}],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: [P-999]
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "P-999" in stdout and "unknown ID" in stdout


def test_validate_problem_fails_unvalidated_without_evidence():
    """Test that UNVALIDATED without missing_evidence fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: UNVALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "UNVALIDATED" in stdout and "missing_evidence" in stdout


def test_validate_problem_fails_reframed_but_validated():
    """Test that reframed_from_solution=true requires UNVALIDATED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: true
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "reframed_from_solution" in stdout


def test_validate_problem_fails_todo_text():
    """Test that TODO text causes failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test TODO: add more details

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "TODO" in stdout


def test_validate_problem_fails_verdict_mismatch():
    """Test that mismatched AI verdict fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: true
  gates:
    "1": {result: pass}
    "2": {result: pass}
    "3": {result: pass}
    "4": {result: pass}
    "5": {result: pass}
  pattern: nlu_nlg
  red_flags: []
  verdict: AI_NOT_JUSTIFIED
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## AI decision
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "verdict mismatch" in stdout


def test_validate_problem_fails_ai_proposed_without_gates():
    """Test that ai.proposed=true without gates fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: true
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## AI decision
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "'gates' is a required property" in stdout


def test_validate_problem_fails_ai_proposed_with_only_four_gates():
    """Test that ai.proposed=true with only four gates fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: true
  gates:
    "1": {result: pass}
    "2": {result: pass}
    "3": {result: pass}
    "4": {result: pass}
  pattern: nlu_nlg
  red_flags: []
  verdict: AI_JUSTIFIED
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## AI decision
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "'5' is a required property" in stdout


def test_validate_problem_fails_missing_extraction_file():
    """Test that missing 01-extraction.json causes clear error and exits 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_path = Path(tmpdir) / "runs" / "2026-01-15-test"
        run_path.mkdir(parents=True)

        notes_dir = run_path / "00-notes"
        notes_dir.mkdir()
        (notes_dir / "notes.numbered.md").write_text("1: Test notes")

        # Create problem.md but NOT extraction.json
        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        (run_path / "02-problem.md").write_text(problem_md)

        code, stdout, stderr = run_validator(str(run_path))
        assert code == 1
        # Should have clear error message
        assert "File not found" in stdout or "01-extraction.json" in stdout
        # Should not have traceback
        assert "Traceback" not in stdout


def test_validate_problem_fails_todo_in_front_matter():
    """Test that TODO in front matter fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: TODO fix this title
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "TODO" in stdout


def test_validate_problem_fails_run_id_mismatch():
    """Test that run_id not matching folder fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [{"id": "P-1", "text": "Test", "source_lines": [1], "type": "stated"}],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-wrong"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "run_id" in stdout


def test_validate_problem_fails_primary_problem_not_in_problems():
    """Test that primary_problem not in problems list fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [{"id": "P-1", "text": "Test", "source_lines": [1], "type": "stated"}],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-999
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "primary_problem" in stdout


def test_validate_problem_fails_duplicate_problem_ids():
    """Test that duplicate problem IDs fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [{"id": "P-1", "text": "Test", "source_lines": [1], "type": "stated"}],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test 1
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
  - id: PB-1
    title: Test 2
    validation_status: VALIDATED
    missing_evidence: []
    source_items: []
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Duplicate" in stdout or "duplicate" in stdout


def test_validate_problem_fails_unknown_source_items_id_with_empty_extraction():
    """Test that unknown source_items ID when extraction has zero items fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        problem_md = """---
run_id: "2026-01-15-test"
problems:
  - id: PB-1
    title: Test
    validation_status: VALIDATED
    missing_evidence: []
    source_items: [P-999]
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement
Test

## Who has it
Test

## Exact scenario
Test

## Current workaround
Test

## Why now
Test

## Strategic fit
Test

## Validation status
Test

## Other topics parked
None
"""

        run_dir = create_test_run(tmpdir, extraction, problem_md, "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "P-999" in stdout or "unknown ID" in stdout


def test_validate_problem_fails_front_matter_is_list():
    """Test that front matter parsing to a list raises ValueError with clear message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        # Create problem.md with front matter that parses to a list
        problem_md = """---
- item1
- item2
---

## Problem statement
Test
"""

        run_path = Path(tmpdir) / "runs" / "2026-01-15-test"
        run_path.mkdir(parents=True)
        (run_path / "00-notes").mkdir()
        (run_path / "00-notes" / "notes.numbered.md").write_text("1: Test")
        (run_path / "01-extraction.json").write_text(json.dumps(extraction, indent=2))
        (run_path / "02-problem.md").write_text(problem_md)

        code, stdout, stderr = run_validator(str(run_path))
        assert code == 1
        assert "front matter must be a mapping" in stdout
        assert "Traceback" not in stdout


def test_validate_problem_fails_front_matter_is_scalar():
    """Test that front matter parsing to a scalar raises ValueError with clear message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        # Create problem.md with front matter that parses to a scalar
        problem_md = """---
just_a_string
---

## Problem statement
Test
"""

        run_path = Path(tmpdir) / "runs" / "2026-01-15-test"
        run_path.mkdir(parents=True)
        (run_path / "00-notes").mkdir()
        (run_path / "00-notes" / "notes.numbered.md").write_text("1: Test")
        (run_path / "01-extraction.json").write_text(json.dumps(extraction, indent=2))
        (run_path / "02-problem.md").write_text(problem_md)

        code, stdout, stderr = run_validator(str(run_path))
        assert code == 1
        assert "front matter must be a mapping" in stdout
        assert "Traceback" not in stdout
