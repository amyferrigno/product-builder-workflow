#!/usr/bin/env python3
"""
SubagentStop hook: log the subagent's estimated cost, then check the stage budget.
Reads agent_transcript_path, agent_type, agent_id from stdin JSON.
Always exits 0. On WARN or STOP prints {"systemMessage": "<line>"}; otherwise prints nothing.
Standard library only.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def get_python_executable(repo_root: str) -> str:
    venv_python = Path(repo_root) / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


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


def run_meter(python_exe: str, script: Path, project_dir: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [python_exe, str(script), *args],
        capture_output=True, text=True, cwd=project_dir, timeout=30,
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parent.parent.parent)
        script = Path(project_dir) / "scripts" / "cost_meter.py"
        pointer = Path(project_dir) / "runs" / ".active"
        if not script.exists() or not pointer.exists():
            return
        run_dir = safe_run_dir(project_dir, pointer.read_text(encoding="utf-8"))
        if run_dir is None:
            return
        transcript = data.get("agent_transcript_path")
        agent_type = data.get("agent_type")
        if not isinstance(transcript, str) or not transcript or not isinstance(agent_type, str) or not agent_type:
            return
        python_exe = get_python_executable(project_dir)
        cmd = ["log", str(run_dir), "--transcript", transcript, "--agent-type", agent_type]
        agent_id = data.get("agent_id")
        if isinstance(agent_id, str) and agent_id:
            cmd += ["--agent-id", agent_id]
        run_meter(python_exe, script, project_dir, *cmd)
        result = run_meter(python_exe, script, project_dir, "check", str(run_dir))
        line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if line.startswith(("WARN", "STOP")):
            print(json.dumps({"systemMessage": line}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
