#!/usr/bin/env python3
"""
Stop hook: append a status snapshot to runs/<id>/session.log.jsonl when it differs from the last one.
Entry: {ts, stage, status, next}. Prints nothing. Always exits 0. Standard library only.
"""

import json
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


def last_entry(log: Path):
    try:
        lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        entry = json.loads(lines[-1]) if lines else None
    except (OSError, ValueError):
        return None
    return entry if isinstance(entry, dict) else None


def main() -> None:
    try:
        project = project_dir()
        run_dir = active_run(project)
        if run_dir is None:
            return
        try:
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        script = Path(project) / "scripts" / "status.py"
        if not script.exists():
            return
        result = subprocess.run(
            [get_python_executable(project), str(script), str(run_dir), "--next"],
            capture_output=True, text=True, cwd=project, timeout=10,
        )
        next_step = result.stdout.strip()
        if result.returncode != 0 or not next_step:
            return
        entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stage": state.get("stage"),
            "status": state.get("status"),
            "next": next_step,
        }
        log = run_dir / "session.log.jsonl"
        last = last_entry(log)
        if last is not None and all(last.get(k) == entry[k] for k in ("stage", "status", "next")):
            return
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
