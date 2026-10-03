"""Test the validate_schema.py CLI script."""

import subprocess
from pathlib import Path


def get_venv_python():
    """Get the path to the Python executable in .venv."""
    repo_root = Path(__file__).parent.parent
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    # Fallback to system python3 if venv doesn't exist
    return "python3"


def run_validator(schema_path, data_path):
    """Run the validator script and return (exit_code, stdout, stderr)."""
    repo_root = Path(__file__).parent.parent
    script_path = repo_root / "scripts" / "validate_schema.py"

    result = subprocess.run(
        [get_venv_python(), str(script_path), schema_path, data_path],
        capture_output=True,
        text=True
    )

    return result.returncode, result.stdout, result.stderr


def test_valid_sample_exits_0():
    """Check that validator exits 0 on valid sample."""
    repo_root = Path(__file__).parent.parent
    schema_path = str(repo_root / "schemas" / "evidence.schema.json")
    sample_path = str(repo_root / "tests" / "samples" / "valid" / "evidence.json")

    exit_code, stdout, stderr = run_validator(schema_path, sample_path)
    assert exit_code == 0, f"Valid sample should exit 0, got {exit_code}\nstdout: {stdout}\nstderr: {stderr}"


def test_invalid_sample_exits_1():
    """Check that validator exits 1 on invalid sample."""
    repo_root = Path(__file__).parent.parent
    schema_path = str(repo_root / "schemas" / "evidence.schema.json")
    sample_path = str(repo_root / "tests" / "samples" / "invalid" / "evidence-bad-id.json")

    exit_code, stdout, stderr = run_validator(schema_path, sample_path)
    assert exit_code == 1, f"Invalid sample should exit 1, got {exit_code}"


def test_missing_data_file_exits_1():
    """Check that validator exits 1 and prints error on missing data file."""
    repo_root = Path(__file__).parent.parent
    schema_path = str(repo_root / "schemas" / "evidence.schema.json")
    sample_path = str(repo_root / "tests" / "samples" / "invalid" / "nonexistent.json")

    exit_code, stdout, stderr = run_validator(schema_path, sample_path)
    assert exit_code == 1, f"Missing file should exit 1, got {exit_code}"
    assert "File not found" in stdout


def test_missing_schema_file_exits_1():
    """Check that validator exits 1 and prints error on missing schema file."""
    repo_root = Path(__file__).parent.parent
    schema_path = str(repo_root / "schemas" / "nonexistent.schema.json")
    sample_path = str(repo_root / "tests" / "samples" / "valid" / "evidence.json")

    exit_code, stdout, stderr = run_validator(schema_path, sample_path)
    assert exit_code == 1, f"Missing schema should exit 1, got {exit_code}"
    assert "Schema file not found" in stdout


def test_error_message_names_bad_field():
    """Check that error message includes the field name."""
    repo_root = Path(__file__).parent.parent
    schema_path = str(repo_root / "schemas" / "evidence.schema.json")
    sample_path = str(repo_root / "tests" / "samples" / "invalid" / "evidence-bad-id.json")

    exit_code, stdout, stderr = run_validator(schema_path, sample_path)
    assert exit_code == 1
    assert "Error at id:" in stdout


def test_unparseable_json_exits_1(tmp_path):
    """Check that validator exits 1 on malformed JSON."""
    repo_root = Path(__file__).parent.parent
    schema_path = str(repo_root / "schemas" / "evidence.schema.json")
    # Create a file with malformed JSON
    bad_json_file = tmp_path / "bad.json"
    bad_json_file.write_text('{"a": [1, 2')

    exit_code, stdout, stderr = run_validator(schema_path, str(bad_json_file))
    assert exit_code == 1, f"Unparseable file should exit 1, got {exit_code}"
    assert "Cannot parse" in stdout
