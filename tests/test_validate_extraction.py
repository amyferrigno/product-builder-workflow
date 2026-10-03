"""Test validate_extraction.py script."""

import json
import tempfile
import subprocess
import sys
from pathlib import Path


def create_test_run(tmpdir: str, extraction: dict, notes_content: str, run_id: str) -> str:
    """Helper to create a test run directory with extraction and numbered notes."""
    run_path = Path(tmpdir) / "runs" / run_id
    run_path.mkdir(parents=True)

    notes_dir = run_path / "00-notes"
    notes_dir.mkdir()

    # Create numbered notes
    lines = notes_content.split('\n')
    if notes_content.endswith('\n'):
        lines = lines[:-1]
    numbered = '\n'.join(f"{i}: {line}" for i, line in enumerate(lines, start=1))
    (notes_dir / "notes.numbered.md").write_text(numbered)

    # Create extraction.json
    (run_path / "01-extraction.json").write_text(json.dumps(extraction, indent=2))

    return str(run_path)


def run_validator(run_dir: str) -> tuple:
    """Run validator and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "scripts/validate_extraction.py", run_dir],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    return result.returncode, result.stdout, result.stderr


def test_validate_extraction_passes_for_valid():
    """Test that valid extraction passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM", "Engineer"],
            "problems": [
                {"id": "P-1", "text": "Test problem", "source_lines": [1, 2], "type": "stated"}
            ],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        run_dir = create_test_run(tmpdir, extraction, "Line 1\nLine 2", "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0, f"Validation failed: {stdout}{stderr}"


def test_validate_extraction_fails_for_out_of_range_line():
    """Test that out-of-range source_lines causes failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [
                {"id": "P-1", "text": "Test", "source_lines": [1, 99], "type": "stated"}
            ],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        run_dir = create_test_run(tmpdir, extraction, "Line 1\nLine 2", "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "doesn't exist in notes" in stdout or "which doesn't exist" in stdout, \
            f"Expected 'doesn't exist in notes' error message: {stdout}"


def test_validate_extraction_fails_for_duplicate_id():
    """Test that duplicate IDs cause failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [
                {"id": "P-1", "text": "Problem 1", "source_lines": [1], "type": "stated"},
                {"id": "P-1", "text": "Problem 2", "source_lines": [2], "type": "stated"}
            ],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        run_dir = create_test_run(tmpdir, extraction, "Line 1\nLine 2", "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Duplicate ID" in stdout


def test_validate_extraction_fails_for_wrong_run_id():
    """Test that mismatched run_id causes failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-wrong",  # Mismatch
            "attendee_roles": ["PM"],
            "problems": [
                {"id": "P-1", "text": "Test", "source_lines": [1], "type": "stated"}
            ],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        run_dir = create_test_run(tmpdir, extraction, "Line 1", "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "run_id mismatch" in stdout


def test_validate_extraction_fails_for_schema_error():
    """Test that schema violations are caught."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [
                {"id": "P-1", "text": "Test", "source_lines": [], "type": "stated"}  # Empty source_lines
            ],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        run_dir = create_test_run(tmpdir, extraction, "Line 1", "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Schema error" in stdout or "source_lines" in stdout


def test_validate_extraction_fails_for_blank_line_citation():
    """Test that citing a blank line fails with that reason."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [
                {"id": "P-1", "text": "Test", "source_lines": [2], "type": "stated"}
            ],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        # Create notes with line 2 being blank
        run_dir = create_test_run(tmpdir, extraction, "Line 1\n\nLine 3", "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "cites blank line 2" in stdout


def test_validate_extraction_passes_for_non_blank_next_to_blank():
    """Test that citing a non-blank line next to a blank one passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = {
            "run_id": "2026-01-15-test",
            "attendee_roles": ["PM"],
            "problems": [
                {"id": "P-1", "text": "Test", "source_lines": [1, 3], "type": "stated"}
            ],
            "proposed_solutions": [],
            "user_segments": [],
            "requests": [],
            "decisions": [],
            "disagreements": [],
            "open_questions": [],
            "action_items": [],
            "metrics_mentioned": []
        }

        # Create notes with line 2 being blank
        run_dir = create_test_run(tmpdir, extraction, "Line 1\n\nLine 3", "2026-01-15-test")

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0
