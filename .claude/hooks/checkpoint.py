#!/usr/bin/env python3
"""
PreCompact hook: write runs/<id>/checkpoint.md (timestamp plus status text).
No active run means do nothing. Always exits 0. Standard library only.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

def project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parent.parent.parent)


def active_run(project: str):
    """Return the active run dir, or None."""
    pointer = Path(project) / "runs" / ".active"
    if not pointer.exists():
        return None
    run_id = pointer.read_text(encoding="utf-8").strip()
    run_dir = Path(project) / "runs" / run_id
    if not run_id or "/" in run_id or not run_dir.is_dir():
        return None
    return run_dir


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
        if not text:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (run_dir / "checkpoint.md").write_text(f"# Checkpoint {stamp}\n\n{text}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
