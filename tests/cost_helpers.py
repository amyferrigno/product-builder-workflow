"""Helpers for the cost meter tests: a temp project with copies of scripts/, schemas/ and the config."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TRANSCRIPTS = REPO_ROOT / "tests" / "samples" / "transcripts"


def make_project(tmp_path: Path, config_text: str = None) -> Path:
    shutil.copytree(REPO_ROOT / "scripts", tmp_path / "scripts")
    shutil.copytree(REPO_ROOT / "schemas", tmp_path / "schemas")
    if config_text is None:
        shutil.copy(REPO_ROOT / "pm.config.yaml", tmp_path / "pm.config.yaml")
    else:
        (tmp_path / "pm.config.yaml").write_text(config_text, encoding="utf-8")
    (tmp_path / "runs").mkdir()
    return tmp_path


def make_run(project: Path, stage: str = "stage1", name: str = "2026-10-04-demo") -> Path:
    run = project / "runs" / name
    run.mkdir(parents=True)
    state = {"run_id": name, "stage": stage, "status": "in_progress"}
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return run


def write_log(run: Path, entries: list) -> None:
    (run / "cost.log.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def read_log(run: Path) -> list:
    path = run / "cost.log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_meter(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(project / "scripts" / "cost_meter.py"), *args],
        capture_output=True, text=True, cwd=project,
    )
