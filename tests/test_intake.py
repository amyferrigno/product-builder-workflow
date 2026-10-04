"""Test intake.py script."""

import json
import tempfile
import subprocess
import sys
import zipfile
from pathlib import Path


def run_intake(input_path: str, args: list = None, stdin_content: str = None) -> tuple:
    """Run intake script and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, "scripts/intake.py"]

    if stdin_content is not None:
        cmd.append("-")
    else:
        cmd.append(input_path)

    if args:
        cmd.extend(args)

    result = subprocess.run(
        cmd,
        input=stdin_content.encode() if stdin_content is not None else None,
        capture_output=True,
        text=False,
        cwd=Path(__file__).parent.parent
    )

    return result.returncode, result.stdout.decode('utf-8'), result.stderr.decode('utf-8')


def test_intake_markdown_file():
    """Test intake with a markdown file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test markdown file
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Line 1\nLine 2\nLine 3")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )

        assert code == 0, f"Command failed: {stderr}"

        output = json.loads(stdout)
        assert output["run_id"] == "2026-01-15-test"
        assert output["line_count"] == 3

        # Check that numbered notes exist
        numbered_path = Path(output["numbered_notes_path"])
        assert numbered_path.exists()
        numbered = numbered_path.read_text()
        assert "1: Line 1" in numbered
        assert "2: Line 2" in numbered
        assert "3: Line 3" in numbered

        # Check that state.json exists and is valid
        state_path = Path(output["run_dir"]) / "state.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert state["run_id"] == "2026-01-15-test"
        assert state["stage"] == "stage1"
        assert state["status"] == "in_progress"


def test_intake_preserves_raw_file():
    """Test that intake preserves the raw file exactly (byte-identical)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "original.txt"
        original_content = "Line with spaces  \nAnother line\n\nBlank above"
        notes_path.write_text(original_content)
        original_bytes = notes_path.read_bytes()

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )

        assert code == 0

        output = json.loads(stdout)
        run_dir = Path(output["run_dir"])
        raw_file = run_dir / "00-notes" / "original.txt"
        assert raw_file.exists()
        assert raw_file.read_bytes() == original_bytes


def test_intake_stdin_requires_slug():
    """Test that stdin input requires --slug argument."""
    code, stdout, stderr = run_intake("", stdin_content="Some notes")

    assert code == 1
    assert "--slug is required" in stderr
    assert "Traceback" not in stderr


def test_intake_stdin_with_slug():
    """Test intake with stdin and slug."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code, stdout, stderr = run_intake(
            "",
            args=["--slug", "demo", "--runs-dir", tmpdir, "--date", "2026-01-15"],
            stdin_content="Note 1\nNote 2"
        )

        assert code == 0

        output = json.loads(stdout)
        assert output["run_id"] == "2026-01-15-demo"

        # Check that pasted.txt was created
        raw_file = Path(output["run_dir"]) / "00-notes" / "pasted.txt"
        assert raw_file.exists()

        # Check numbered notes content
        numbered_path = Path(output["numbered_notes_path"])
        numbered = numbered_path.read_text()
        assert "1: Note 1" in numbered
        assert "2: Note 2" in numbered

        # Validate state.json against schema
        import os
        os.chdir(Path(__file__).parent.parent)
        run_dir = Path(output["run_dir"])
        state_path = run_dir / "state.json"
        code = subprocess.run(
            [sys.executable, "scripts/validate_schema.py",
             "schemas/state.schema.json", str(state_path)],
            capture_output=True
        ).returncode
        assert code == 0, "state.json failed schema validation"


def test_intake_unsupported_extension():
    """Test that unsupported file extension fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_file = Path(tmpdir) / "test.xyz"
        bad_file.write_text("content")

        code, stdout, stderr = run_intake(str(bad_file))

        assert code == 1
        assert "Unsupported file type" in stderr
        assert "Traceback" not in stderr


def test_intake_missing_file():
    """Test that missing file fails."""
    code, stdout, stderr = run_intake("/nonexistent/file.md")

    assert code == 1
    assert "File not found" in stderr
    assert "Traceback" not in stderr


def test_intake_empty_input():
    """Test intake with empty input."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "empty.txt"
        notes_path.write_text("")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir]
        )

        assert code == 1
        assert "input is empty" in stderr
        assert "Traceback" not in stderr
        # Verify no run folder was created inside tmpdir (no <date>-<slug> directory)
        run_dirs = list(Path(tmpdir).glob("*-*"))
        assert len(run_dirs) == 0, f"Run directory was created when it should not have been: {run_dirs}"


def test_intake_whitespace_only_file():
    """Test that whitespace-only file input exits 1 with 'input is empty' message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "whitespace.txt"
        notes_path.write_text("   \n\t\n   ")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir]
        )

        assert code == 1
        assert "input is empty" in stderr
        assert "Traceback" not in stderr
        # Verify no run folder was created
        run_dirs = list(Path(tmpdir).glob("*-*"))
        assert len(run_dirs) == 0


def test_intake_empty_stdin():
    """Test that empty stdin input exits 1 with 'input is empty' message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code, stdout, stderr = run_intake(
            "-",
            args=["--slug", "test", "--runs-dir", tmpdir],
            stdin_content=""
        )

        assert code == 1
        assert "input is empty" in stderr
        assert "Traceback" not in stderr
        # Verify no run folder was created
        run_dirs = list(Path(tmpdir).glob("*-*"))
        assert len(run_dirs) == 0


def test_intake_whitespace_only_stdin():
    """Test that whitespace-only stdin input exits 1 with 'input is empty' message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code, stdout, stderr = run_intake(
            "-",
            args=["--slug", "test", "--runs-dir", tmpdir],
            stdin_content="   \n\t\n   "
        )

        assert code == 1
        assert "input is empty" in stderr
        assert "Traceback" not in stderr
        # Verify no run folder was created
        run_dirs = list(Path(tmpdir).glob("*-*"))
        assert len(run_dirs) == 0


def test_intake_refuses_overwrite():
    """Test that intake refuses to overwrite an existing run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Content")

        # First run should succeed
        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )
        assert code == 0

        # Second run with same slug and date should fail
        notes_path.write_text("Different content")
        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )
        assert code == 1
        assert "already exists" in stderr
        assert "Traceback" not in stderr


def test_intake_derives_slug_from_filename():
    """Test that slug is derived from filename when not provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "My_Meeting_Notes.md"
        notes_path.write_text("Content")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--runs-dir", tmpdir, "--date", "2026-01-15"]
        )

        assert code == 0
        output = json.loads(stdout)
        assert output["run_id"] == "2026-01-15-my-meeting-notes"


def test_intake_state_validates_against_schema():
    """Test that state.json validates against the schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Content")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )

        assert code == 0

        output = json.loads(stdout)
        state_path = Path(output["run_dir"]) / "state.json"

        # Validate manually
        import os
        os.chdir(Path(__file__).parent.parent)
        code = subprocess.run(
            [sys.executable, "scripts/validate_schema.py",
             "schemas/state.schema.json", str(state_path)],
            capture_output=True
        ).returncode
        assert code == 0, "state.json failed schema validation"


def test_intake_blank_lines_preserved():
    """Test that blank lines are numbered and preserved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Line 1\n\nLine 3")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir]
        )

        assert code == 0

        output = json.loads(stdout)
        numbered = Path(output["numbered_notes_path"]).read_text()
        assert "1: Line 1" in numbered
        assert "2:" in numbered  # blank line should be numbered
        assert "3: Line 3" in numbered


def test_intake_docx_file():
    """Test intake with a DOCX file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal docx file with zipfile
        docx_path = Path(tmpdir) / "test.docx"

        # Create a minimal word/document.xml
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:p>
        <w:r><w:t>First paragraph</w:t></w:r>
    </w:p>
    <w:p>
        <w:r><w:t>Second paragraph</w:t></w:r>
    </w:p>
    <w:p>
        <w:r><w:t>Third paragraph</w:t></w:r>
    </w:p>
</w:document>'''

        with zipfile.ZipFile(docx_path, 'w') as docx:
            docx.writestr('word/document.xml', xml_content.encode('utf-8'))

        original_bytes = docx_path.read_bytes()

        code, stdout, stderr = run_intake(
            str(docx_path),
            args=["--slug", "test-docx", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )

        assert code == 0, f"Command failed: {stderr}"

        output = json.loads(stdout)
        assert output["run_id"] == "2026-01-15-test-docx"

        # Check numbered notes contain each paragraph
        numbered_path = Path(output["numbered_notes_path"])
        numbered = numbered_path.read_text()
        assert "First paragraph" in numbered
        assert "Second paragraph" in numbered
        assert "Third paragraph" in numbered

        # Check raw copy is byte-identical
        run_dir = Path(output["run_dir"])
        raw_docx = run_dir / "00-notes" / "test.docx"
        assert raw_docx.exists()
        assert raw_docx.read_bytes() == original_bytes

        # Validate state.json against schema
        import os
        os.chdir(Path(__file__).parent.parent)
        state_path = run_dir / "state.json"
        code = subprocess.run(
            [sys.executable, "scripts/validate_schema.py",
             "schemas/state.schema.json", str(state_path)],
            capture_output=True
        ).returncode
        assert code == 0, "state.json failed schema validation"


def test_intake_corrupt_docx():
    """Test that corrupt DOCX exits with clear message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a corrupt docx file (bad zip)
        docx_path = Path(tmpdir) / "corrupt.docx"
        docx_path.write_bytes(b"This is not a zip file")

        code, stdout, stderr = run_intake(
            str(docx_path),
            args=["--slug", "test", "--runs-dir", tmpdir]
        )

        assert code == 1
        assert "Cannot read file" in stderr
        assert "Traceback" not in stderr


def test_intake_crlf_txt():
    """Test that CRLF .txt file is preserved byte-identical."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "crlf.txt"
        # Write with CRLF line endings
        content_with_crlf = "Line 1\r\nLine 2\r\nLine 3"
        notes_path.write_bytes(content_with_crlf.encode('utf-8'))
        original_bytes = notes_path.read_bytes()

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )

        assert code == 0

        output = json.loads(stdout)
        run_dir = Path(output["run_dir"])
        raw_file = run_dir / "00-notes" / "crlf.txt"
        assert raw_file.exists()
        assert raw_file.read_bytes() == original_bytes

        # Validate state.json against schema
        import os
        os.chdir(Path(__file__).parent.parent)
        state_path = run_dir / "state.json"
        code = subprocess.run(
            [sys.executable, "scripts/validate_schema.py",
             "schemas/state.schema.json", str(state_path)],
            capture_output=True
        ).returncode
        assert code == 0, "state.json failed schema validation"


def test_intake_refuses_overwrite_idempotent():
    """Test that refuse-overwrite doesn't modify the first run's files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Original content")

        # First run
        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )
        assert code == 0
        output1 = json.loads(stdout)
        run_dir = Path(output1["run_dir"])

        # Hash all files from first run
        file_hashes_before = {}
        for file_path in run_dir.rglob("*"):
            if file_path.is_file():
                file_hashes_before[file_path.relative_to(run_dir)] = hash(file_path.read_bytes())

        # Attempt second run with same slug and date
        notes_path.write_text("Different content")
        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir, "--date", "2026-01-15"]
        )
        assert code == 1
        assert "already exists" in stderr
        assert "Traceback" not in stderr

        # Verify all files are unchanged
        for file_path in run_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(run_dir)
                assert rel_path in file_hashes_before, f"New file created: {rel_path}"
                assert hash(file_path.read_bytes()) == file_hashes_before[rel_path], f"File changed: {rel_path}"


def test_intake_non_utf8_txt():
    """Test that non-UTF-8 .txt exits 1 with one-line error and no traceback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "bad_encoding.txt"
        # Write with non-UTF-8 encoding
        notes_path.write_bytes(b'\xff\xfe')  # BOM for UTF-16

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "test", "--runs-dir", tmpdir]
        )

        assert code == 1
        # Should have exactly one line of error
        stderr_lines = [ln for ln in stderr.strip().split('\n') if ln]
        assert len(stderr_lines) == 1
        assert "Cannot read file" in stderr
        assert "Traceback" not in stderr


def test_intake_invalid_slug():
    """Test that invalid --slug exits 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Content")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "Bad Slug!", "--runs-dir", tmpdir]
        )

        assert code == 1
        assert "slug must match" in stderr
        assert "Traceback" not in stderr


def test_intake_empty_slug():
    """Test that --slug '' (empty string) is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Content")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "", "--runs-dir", tmpdir]
        )

        assert code == 1
        assert "slug must match" in stderr
        assert "Traceback" not in stderr


def test_intake_slug_with_leading_hyphen():
    """Test that slugs with leading hyphen are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Content")

        # Use --slug=-a to avoid argparse treating -a as a flag
        result = subprocess.run(
            [sys.executable, "scripts/intake.py", str(notes_path),
             "--slug=-a", "--runs-dir", tmpdir],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 1
        assert "slug must match" in result.stderr
        assert "Traceback" not in result.stderr


def test_intake_slug_with_trailing_hyphen():
    """Test that --slug 'a-' (trailing hyphen) is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Content")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "a-", "--runs-dir", tmpdir]
        )

        assert code == 1
        assert "slug must match" in stderr
        assert "Traceback" not in stderr


def test_intake_slug_only_hyphen():
    """Test that --slug '-' (only hyphen) is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_path = Path(tmpdir) / "test.md"
        notes_path.write_text("Content")

        code, stdout, stderr = run_intake(
            str(notes_path),
            args=["--slug", "-", "--runs-dir", tmpdir]
        )

        assert code == 1
        assert "slug must match" in stderr
        assert "Traceback" not in stderr
