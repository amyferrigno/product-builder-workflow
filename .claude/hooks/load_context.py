#!/usr/bin/env python3
"""
SessionStart hook: print the active run's status so it is added to the model's context.
No active run means print nothing. Always exits 0. Standard library only.
"""

import os
import subprocess
import sys
from pathlib import Path

def project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parent.parent.parent)


def safe_run_dir(project: str, run_id: str):
    """Return runs/<run_id> when run_id is a plain folder name directly under runs/, else None."""
    run_id = run_id.strip()
    if not run_id or run_id in (".", "..") or run_id.startswith("."):
        return None
    if any(c in run_id for c in ("/", "\\", "\0")):
        return None
    runs = (Path(project) / "runs").resolve()
    run_dir = runs / run_id
    try:
        if run_dir.resolve().parent != runs or not run_dir.is_dir():
            return None
    except (OSError, ValueError):
        return None
    return run_dir


def active_run(project: str):
    """Return the active run dir, or None."""
    pointer = Path(project) / "runs" / ".active"
    if not pointer.exists():
        return None
    return safe_run_dir(project, pointer.read_text(encoding="utf-8"))


def get_python_executable(project: str) -> str:
    venv_python = Path(project) / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def status_text(project: str, run_dir: Path):
    """Run scripts/status.py for the run. Returns the text, or None on any failure."""
    script = Path(project) / "scripts" / "status.py"
    if not script.exists():
        return None
    result = subprocess.run(
        [get_python_executable(project), str(script), str(run_dir)],
        capture_output=True, text=True, cwd=project, timeout=10,
    )
    text = result.stdout.strip()
    return text if result.returncode == 0 and text else None


def main() -> None:
    try:
        project = project_dir()
        run_dir = active_run(project)
        if run_dir is None:
            return
        text = status_text(project, run_dir)
        if text:
            print(text)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
