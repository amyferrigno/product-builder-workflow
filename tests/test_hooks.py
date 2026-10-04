"""Test hook scripts."""

import json
import tempfile
import subprocess
import sys
from pathlib import Path


def run_hook_script(hook_script: str, tool_call_data: dict = None) -> tuple:
    """Run a hook script with JSON on stdin and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, hook_script]

    stdin_data = None
    if tool_call_data:
        stdin_data = json.dumps(tool_call_data)

    result = subprocess.run(
        cmd,
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    return result.returncode, result.stdout, result.stderr


def test_guard_approvals_blocks_absolute_approval_path():
    """Test that guard_approvals blocks absolute paths under runs/*/approvals/."""
    hook_script = ".claude/hooks/guard_approvals.py"

    tool_call = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/path/to/runs/2026-10-03-test/approvals/prd.approved"
        }
    }

    code, stdout, stderr = run_hook_script(hook_script, tool_call)

    assert code == 2, f"Should have blocked but got code {code}"
    assert "Blocked" in stderr or "approval" in stderr


def test_guard_approvals_blocks_relative_approval_path():
    """Test that guard_approvals blocks relative paths under runs/*/approvals/."""
    hook_script = ".claude/hooks/guard_approvals.py"

    tool_call = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "runs/2026-10-03-test/approvals/prd.approved"
        }
    }

    code, stdout, stderr = run_hook_script(hook_script, tool_call)

    assert code == 2, f"Should have blocked but got code {code}"
    assert "approval files are written only by" in stderr.lower()


def test_guard_approvals_allows_prd_path():
    """Test that guard_approvals allows runs/*/prd.md."""
    hook_script = ".claude/hooks/guard_approvals.py"

    tool_call = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "runs/2026-10-03-test/prd.md"
        }
    }

    code, stdout, stderr = run_hook_script(hook_script, tool_call)

    assert code == 0, f"Should have allowed but got code {code}"


def test_guard_approvals_empty_stdin():
    """Test that guard_approvals fails open for empty stdin."""
    hook_script = ".claude/hooks/guard_approvals.py"

    result = subprocess.run(
        [sys.executable, hook_script],
        input="",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 0, "Should fail open for empty stdin"
    assert "Traceback" not in result.stderr


def test_guard_approvals_invalid_json():
    """Test that guard_approvals fails open for invalid JSON."""
    hook_script = ".claude/hooks/guard_approvals.py"

    result = subprocess.run(
        [sys.executable, hook_script],
        input="not valid json",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 0, "Should fail open for invalid JSON"
    assert "Traceback" not in result.stderr


def test_guard_approvals_bash_tool_without_filepath():
    """Test that guard_approvals allows Bash tool without file_path."""
    hook_script = ".claude/hooks/guard_approvals.py"

    tool_call = {
        "tool_name": "Bash",
        "tool_input": {
            "command": "ls -la"
        }
    }

    code, stdout, stderr = run_hook_script(hook_script, tool_call)

    assert code == 0, f"Should allow non-file tools"


def test_validate_artifact_exits_0_for_unrelated_file():
    """Test that validate_artifact exits 0 for non-PRD files."""
    hook_script = ".claude/hooks/validate_artifact.py"

    tool_call = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "README.md"
        }
    }

    code, stdout, stderr = run_hook_script(hook_script, tool_call)

    assert code == 0, f"Should allow non-PRD files"


def test_validate_artifact_exits_0_if_no_validate_script():
    """Test that validate_artifact exits 0 if validate_prd.py doesn't exist."""
    hook_script = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_artifact.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a run dir with prd.md but no validate_prd.py
        run_dir = Path(tmpdir) / "runs" / "test"
        run_dir.mkdir(parents=True)
        (run_dir / "prd.md").write_text("# PRD")

        tool_call = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(run_dir / "prd.md")
            }
        }

        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input=json.dumps(tool_call),
            capture_output=True,
            text=True,
            env={"CLAUDE_PROJECT_DIR": tmpdir},
            cwd=Path(__file__).parent.parent
        )

        # Should exit 0 if script doesn't exist
        assert result.returncode == 0, f"Should exit 0 if validate script doesn't exist"


def test_validate_artifact_runs_validation():
    """Test that validate_artifact runs validation when script exists."""
    hook_script = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_artifact.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a temp project dir with scripts/validate_prd.py
        project_dir = Path(tmpdir) / "project"
        project_dir.mkdir()
        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()

        # Create a stub validate_prd.py that exits with 0
        stub_validate = scripts_dir / "validate_prd.py"
        stub_validate.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n")
        stub_validate.chmod(0o755)

        # Create run dir
        run_dir = project_dir / "runs" / "test"
        run_dir.mkdir(parents=True)
        (run_dir / "prd.md").write_text("# PRD")

        tool_call = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(run_dir / "prd.md")
            }
        }

        # Run with CLAUDE_PROJECT_DIR set
        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input=json.dumps(tool_call),
            capture_output=True,
            text=True,
            env={"CLAUDE_PROJECT_DIR": str(project_dir)},
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 0, f"Validation passed, should exit 0"


def test_validate_artifact_blocks_on_validation_failure():
    """Test that validate_artifact exits 2 when validation fails."""
    hook_script = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_artifact.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a temp project dir with scripts/validate_prd.py
        project_dir = Path(tmpdir) / "project"
        project_dir.mkdir()
        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()

        # Create a stub validate_prd.py that exits with 1
        stub_validate = scripts_dir / "validate_prd.py"
        stub_validate.write_text("""#!/usr/bin/env python3
import sys
print("PRD validation failed: missing section", file=sys.stderr)
sys.exit(1)
""")
        stub_validate.chmod(0o755)

        # Create run dir
        run_dir = project_dir / "runs" / "test"
        run_dir.mkdir(parents=True)
        (run_dir / "prd.md").write_text("# PRD")

        tool_call = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(run_dir / "prd.md")
            }
        }

        # Run with CLAUDE_PROJECT_DIR set
        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input=json.dumps(tool_call),
            capture_output=True,
            text=True,
            env={"CLAUDE_PROJECT_DIR": str(project_dir)},
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 2, f"Validation failed, should exit 2, got {result.returncode}"
        assert "PRD validation errors:" in result.stderr


def test_settings_json_is_valid():
    """Test that .claude/settings.json is valid JSON."""
    settings_path = Path(".claude/settings.json")

    with open(settings_path, 'r') as f:
        settings = json.load(f)

    # Should have hooks key
    assert "hooks" in settings
    assert "PreToolUse" in settings["hooks"]
    assert "PostToolUse" in settings["hooks"]


def test_settings_json_references_both_hooks():
    """Test that settings.json references both hook files."""
    settings_path = Path(".claude/settings.json")

    with open(settings_path, 'r') as f:
        content = f.read()

    # Check for both hook file references
    assert "guard_approvals.py" in content
    assert "validate_artifact.py" in content


def test_hook_files_exist():
    """Test that both hook files exist."""
    guard_path = Path(".claude/hooks/guard_approvals.py")
    validate_path = Path(".claude/hooks/validate_artifact.py")

    assert guard_path.exists(), f"guard_approvals.py not found at {guard_path}"
    assert validate_path.exists(), f"validate_artifact.py not found at {validate_path}"


def test_validate_artifact_empty_stdin():
    """Test that validate_artifact fails open for empty stdin."""
    hook_script = ".claude/hooks/validate_artifact.py"

    result = subprocess.run(
        [sys.executable, hook_script],
        input="",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 0, "Should fail open for empty stdin"
    assert "Traceback" not in result.stderr


def test_validate_artifact_invalid_json():
    """Test that validate_artifact fails open for invalid JSON."""
    hook_script = ".claude/hooks/validate_artifact.py"

    result = subprocess.run(
        [sys.executable, hook_script],
        input="not valid json",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 0, "Should fail open for invalid JSON"
    assert "Traceback" not in result.stderr


def _hook_code(file_path: str) -> int:
    tool_call = {"tool_name": "Write", "tool_input": {"file_path": file_path}}
    code, _, _ = run_hook_script(".claude/hooks/guard_approvals.py", tool_call)
    return code


def test_guard_approvals_blocks_dotdot_collapsing_to_approvals():
    """Paths that use .. to reach runs/<id>/approvals/ are blocked."""
    assert _hook_code("runs/x/../x/approvals/prd.approved") == 2
    assert _hook_code("runs/x/foo/../approvals/prd.approved") == 2


def test_guard_approvals_blocks_case_variants():
    """Case-insensitive volume: Approvals and Runs variants are blocked."""
    assert _hook_code("runs/x/Approvals/prd.approved") == 2
    assert _hook_code("Runs/x/approvals/prd.approved") == 2


def test_guard_approvals_allows_non_approval_paths():
    """Ordinary paths still pass."""
    assert _hook_code("runs/x/prd.md") == 0
    assert _hook_code("docs/approvals/notes.md") == 0


def _bash_hook(command: str) -> tuple:
    tool_call = {"tool_name": "Bash", "tool_input": {"command": command}}
    return run_hook_script(".claude/hooks/guard_approvals.py", tool_call)


def test_guard_approvals_asks_for_approve_commands():
    """Any approve.py command gets an ask decision, exit 0."""
    commands = {
        ".venv/bin/python scripts/approve.py runs/r1 prd": ("prd", "runs/r1"),
        'python3 -u scripts/approve.py runs/r1 ux --override "x"': ("ux", "runs/r1"),
        "cd scripts && python approve.py ../runs/r1 tickets": ("tickets", "../runs/r1"),
    }
    for command, (gate, run) in commands.items():
        code, stdout, _ = _bash_hook(command)
        assert code == 0, command
        out = json.loads(stdout)["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse", command
        assert out["permissionDecision"] == "ask", command
        assert gate in out["permissionDecisionReason"], command
        assert run in out["permissionDecisionReason"], command


def test_guard_approvals_asks_with_generic_reason_when_args_missing():
    code, stdout, _ = _bash_hook("python -m approve")
    assert code == 0
    out = json.loads(stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "ask"
    assert "a human must confirm" in out["permissionDecisionReason"]


def test_guard_approvals_blocks_shell_writes_to_approvals():
    commands = [
        "echo x > runs/r1/approvals/prd.approved",
        "cp /tmp/a runs/r1/approvals/ux.approved",
        "mv /tmp/a runs/r1/approvals/ux.approved",
        "rm runs/r1/approvals/prd.approved",
        "tee runs/r1/approvals/prd.approved",
        "touch runs/r1/approvals/prd.approved",
        "python -c \"open('runs/r1/approvals/prd.approved','w')\"",
        "cat a | tee runs/r1/approvals/x",
        "ls runs/r1/approvals/ ; rm -rf x",
    ]
    for command in commands:
        code, _, stderr = _bash_hook(command)
        assert code == 2, command
        assert "Blocked" in stderr, command


def test_guard_approvals_allows_plain_reads_and_other_commands():
    commands = [
        "ls runs/r1/approvals/",
        "cat runs/r1/approvals/prd.approved",
        "ls",
        "make test",
        "./.venv/bin/pytest tests/ -q",
        "cat scripts/approve.py",
    ]
    for command in commands:
        code, stdout, _ = _bash_hook(command)
        assert code == 0, command
        assert stdout == "", command


def test_settings_registers_guard_approvals_under_bash():
    hooks = json.loads(Path(".claude/settings.json").read_text())["hooks"]["PreToolUse"]
    entries = [e for e in hooks if e["matcher"] == "Bash"]
    commands = [h["command"] for e in entries for h in e["hooks"]]
    assert any("guard_approvals.py" in c for c in commands)


def _spec_hook_result(spec_text: str) -> subprocess.CompletedProcess:
    import shutil
    hook_script = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_artifact.py"
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "runs" / "test"
        shutil.copytree(Path(__file__).parent.parent / "fixtures" / "ai-clear-fit" / "golden" / "ux", run_dir / "ux")
        shutil.copy(Path(__file__).parent.parent / "fixtures" / "ai-clear-fit" / "golden" / "prd.md", run_dir / "prd.md")
        (run_dir / "ux" / "spec.md").write_text(spec_text, encoding="utf-8")
        tool_call = {"tool_name": "Write", "tool_input": {"file_path": str(run_dir / "ux" / "spec.md")}}
        return subprocess.run(
            [sys.executable, str(hook_script)],
            input=json.dumps(tool_call),
            capture_output=True,
            text=True,
            env={"CLAUDE_PROJECT_DIR": str(Path(__file__).parent.parent)},
            cwd=Path(__file__).parent.parent,
        )


def test_validate_artifact_accepts_valid_spec():
    golden = Path(__file__).parent.parent / "fixtures" / "ai-clear-fit" / "golden" / "ux" / "spec.md"
    result = _spec_hook_result(golden.read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stderr


def test_validate_artifact_rejects_spec_with_unknown_req():
    golden = Path(__file__).parent.parent / "fixtures" / "ai-clear-fit" / "golden" / "ux" / "spec.md"
    spec = golden.read_text(encoding="utf-8")
    first = next(line for line in spec.splitlines() if line.startswith("**REQs**"))
    bad = spec.replace(first, first + ", REQ-999", 1)
    result = _spec_hook_result(bad)
    assert result.returncode == 2
    assert "REQ-999" in result.stderr
