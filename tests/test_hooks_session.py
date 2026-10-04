"""Tests for the session hooks: load_context, checkpoint, close_out, and their registration."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from cost_helpers import make_project, make_run  # noqa: E402

HOOKS = REPO_ROOT / ".claude" / "hooks"
NAMES = ["load_context", "checkpoint", "close_out"]


def run_hook(name: str, project: Path, raw: str = "{}") -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    return subprocess.run(
        [sys.executable, str(HOOKS / f"{name}.py")],
        input=raw, capture_output=True, text=True, env=env, cwd=project,
    )


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


@pytest.fixture
def active(project):
    run = make_run(project)
    (project / "runs" / ".active").write_text(run.name + "\n", encoding="utf-8")
    return run


@pytest.mark.parametrize("name", NAMES)
def test_no_active_run_does_nothing(project, name):
    result = run_hook(name, project)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize("name", NAMES)
def test_pointer_to_missing_run_does_nothing(project, name):
    (project / "runs" / ".active").write_text("gone\n", encoding="utf-8")
    result = run_hook(name, project)
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize("name", NAMES)
def test_malformed_stdin_exits_0(active, project, name):
    for raw in ("not json", ""):
        result = run_hook(name, project, raw=raw)
        assert result.returncode == 0
        assert "Traceback" not in result.stderr


def test_load_context_prints_status(active, project):
    result = run_hook("load_context", project)
    assert result.returncode == 0
    assert f"Run: {active.name}" in result.stdout
    assert "Next: /pm-prd" in result.stdout


def test_checkpoint_writes_file(active, project):
    result = run_hook("checkpoint", project)
    assert result.returncode == 0
    assert result.stdout == ""
    text = (active / "checkpoint.md").read_text(encoding="utf-8")
    assert text.startswith("# Checkpoint ")
    assert f"Run: {active.name}" in text


def test_close_out_appends_once_per_change(active, project):
    log = active / "session.log.jsonl"
    assert run_hook("close_out", project).stdout == ""
    assert run_hook("close_out", project).returncode == 0
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert set(entry) == {"ts", "stage", "status", "next"}
    assert (entry["stage"], entry["status"], entry["next"]) == ("stage1", "in_progress", "prd")

    state = json.loads((active / "state.json").read_text(encoding="utf-8"))
    state["stage"] = "stage2"
    (active / "state.json").write_text(json.dumps(state), encoding="utf-8")
    run_hook("close_out", project)
    run_hook("close_out", project)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["stage"] == "stage2"


def test_hooks_ignore_missing_status_script(active, project):
    (project / "scripts" / "status.py").unlink()
    for name in NAMES:
        result = run_hook(name, project)
        assert result.returncode == 0
        assert result.stdout == ""
    assert not (active / "checkpoint.md").exists()
    assert not (active / "session.log.jsonl").exists()


def test_settings_register_all_four_events():
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    expected = {
        "SubagentStop": "cost_meter_hook.py",
        "SessionStart": "load_context.py",
        "PreCompact": "checkpoint.py",
        "Stop": "close_out.py",
    }
    for event, script in expected.items():
        commands = [h["command"] for group in settings["hooks"][event] for h in group["hooks"]]
        assert commands == [f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/{script}"']
        assert (HOOKS / script).is_file()
