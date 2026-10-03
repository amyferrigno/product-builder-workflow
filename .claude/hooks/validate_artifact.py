#!/usr/bin/env python3
"""
PostToolUse hook to validate artifacts when edited.
Reads tool call from stdin as JSON and validates runs/*/prd.md.
Runs scripts/validate_prd.py when a PRD is edited.
Exit 0 if no validation needed or validation passes, exit 2 if validation fails.
"""

import sys
import json
import subprocess
import os
from pathlib import Path


def resolve_path(file_path: str, project_dir: str = None) -> Path:
    """Resolve a file path to absolute path."""
    p = Path(file_path)
    if p.is_absolute():
        return p
    else:
        # If relative, resolve from project directory
        if project_dir:
            return Path(project_dir) / p
        else:
            return Path.cwd() / p


def matches_prd_pattern(file_path: str) -> tuple:
    """
    Check if file_path matches runs/<run_id>/prd.md.
    Returns (True, run_dir) if it matches, (False, None) otherwise.
    """
    try:
        p = Path(file_path)
        parts = p.parts

        # Look for "runs" in the path
        for i, part in enumerate(parts):
            if part == "runs" and i + 2 <= len(parts):
                # Check if the file is prd.md at position i+2
                if i + 2 < len(parts):
                    if parts[i + 2] == "prd.md":
                        # Reconstruct the run directory path
                        run_dir_parts = parts[:i + 2]
                        run_dir = Path(*run_dir_parts)
                        return True, str(run_dir)

        return False, None
    except Exception:
        return False, None


def matches_spec_pattern(file_path: str) -> tuple:
    """
    Check if file_path matches runs/<run_id>/ux/spec.md.
    Returns (True, run_dir) if it matches, (False, None) otherwise.
    """
    try:
        parts = Path(os.path.normpath(file_path)).parts
        for i, part in enumerate(parts):
            if part == "runs" and i + 3 < len(parts):
                if parts[i + 2] == "ux" and parts[i + 3] == "spec.md" and i + 4 == len(parts):
                    return True, str(Path(*parts[:i + 2]))
        return False, None
    except Exception:
        return False, None


def find_validate_script(repo_root: str) -> str:
    """Find the validate_prd.py script."""
    validate_path = Path(repo_root) / "scripts" / "validate_prd.py"
    if validate_path.exists():
        return str(validate_path)
    return None


def get_python_executable(repo_root: str) -> str:
    """Get the Python executable to use."""
    venv_python = Path(repo_root) / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)

    return sys.executable


def main():
    """Main entry point."""
    try:
        # Read JSON from stdin
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, EOFError):
        # Malformed or empty stdin: fail open (exit 0)
        sys.exit(0)
    except Exception:
        # Any other error: fail open
        sys.exit(0)

    # Check for tool_input.file_path
    try:
        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path")

        if not file_path:
            # No file_path in tool_input: allow
            sys.exit(0)

        # Get project directory from environment
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if not project_dir:
            # Derive from this script's location
            project_dir = str(Path(__file__).parent.parent.parent)

        # Resolve the file path
        resolved_path = resolve_path(file_path, project_dir)

        # Check if this is a prd.md file
        is_prd, run_dir = matches_prd_pattern(str(resolved_path))

        is_spec, spec_run_dir = matches_spec_pattern(str(resolved_path))

        if is_spec:
            spec_script = Path(project_dir) / "scripts" / "validate_ux.py"
            if not spec_script.exists():
                sys.exit(0)
            try:
                result = subprocess.run(
                    [get_python_executable(project_dir), str(spec_script), spec_run_dir, "--spec-only"],
                    capture_output=True, text=True, cwd=project_dir, timeout=30
                )
                if result.returncode != 0:
                    print(f"UX spec validation errors:\n{result.stdout + result.stderr}", file=sys.stderr)
                    sys.exit(2)
                sys.exit(0)
            except subprocess.TimeoutExpired:
                sys.exit(0)
            except SystemExit:
                raise
            except Exception:
                sys.exit(0)

        if not is_prd:
            # Not a PRD file: allow
            sys.exit(0)

        # Find the validate_prd.py script
        validate_script = find_validate_script(project_dir)
        if not validate_script:
            # Script doesn't exist yet: allow
            sys.exit(0)

        # Get Python executable
        python_exe = get_python_executable(project_dir)

        # Run the validation script
        try:
            result = subprocess.run(
                [python_exe, validate_script, run_dir],
                capture_output=True,
                text=True,
                cwd=project_dir,
                timeout=30
            )

            if result.returncode != 0:
                # Validation failed: block the edit
                output = result.stdout + result.stderr
                print(f"PRD validation errors:\n{output}", file=sys.stderr)
                sys.exit(2)

            # Validation passed: allow
            sys.exit(0)

        except subprocess.TimeoutExpired:
            # Timeout: fail open
            sys.exit(0)
        except Exception:
            # Any other error: fail open
            sys.exit(0)

    except Exception:
        # Any error: fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
