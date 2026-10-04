"""Test the cost_meter_hook SubagentStop hook."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cost_helpers import REPO_ROOT, TRANSCRIPTS, make_project, make_run, read_log, write_log  # noqa: E402

HOOK = REPO_ROOT / ".claude" / "hooks" / "cost_meter_hook.py"


def run_hook(project: Path, payload=None, raw: str = None) -> subprocess.CompletedProcess:
    text = raw if raw is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=text, capture_output=True, text=True,
        env={"CLAUDE_PROJECT_DIR": str(project)}, cwd=REPO_ROOT,
    )


def activate(project: Path, run: Path) -> None:
    (project / "runs" / ".active").write_text(run.name + "\n", encoding="utf-8")


def payload(transcript: Path, agent_id: str = "a-1") -> dict:
    return {"hook_event_name": "SubagentStop", "agent_transcript_path": str(transcript),
            "agent_type": "prd-writer", "agent_id": agent_id}


def test_no_active_run_does_nothing(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    result = run_hook(project, payload(TRANSCRIPTS / "normal.jsonl"))
    assert result.returncode == 0
    assert result.stdout == ""
    assert read_log(run) == []


def test_active_pointer_to_missing_run_does_nothing(tmp_path):
    project = make_project(tmp_path)
    (project / "runs" / ".active").write_text("2026-01-01-gone\n", encoding="utf-8")
    result = run_hook(project, payload(TRANSCRIPTS / "normal.jsonl"))
    assert result.returncode == 0
    assert result.stdout == ""


def test_malformed_and_empty_stdin_exit_0(tmp_path):
    project = make_project(tmp_path)
    activate(project, make_run(project))
    for raw in ("not json", "", "[1, 2]", "null"):
        result = run_hook(project, raw=raw)
        assert result.returncode == 0
        assert result.stdout == ""
        assert "Traceback" not in result.stderr


def test_missing_transcript_path_field_exits_0_without_logging(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    activate(project, run)
    result = run_hook(project, {"agent_type": "x", "agent_id": "a"})
    assert result.returncode == 0
    assert result.stdout == ""
    assert read_log(run) == []


def test_nonexistent_transcript_file_logs_unparsed_and_exits_0(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    activate(project, run)
    result = run_hook(project, payload(tmp_path / "nope.jsonl"))
    assert result.returncode == 0
    assert result.stdout == ""
    assert read_log(run)[0]["source"] == "unparsed"


def test_logs_entry_and_prints_nothing_under_warn_level(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    activate(project, run)
    result = run_hook(project, payload(TRANSCRIPTS / "normal.jsonl"))
    assert result.returncode == 0
    assert result.stdout == ""
    entries = read_log(run)
    assert len(entries) == 1 and entries[0]["agent_id"] == "a-1"


def test_same_agent_id_is_logged_once(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    activate(project, run)
    run_hook(project, payload(TRANSCRIPTS / "normal.jsonl"))
    run_hook(project, payload(TRANSCRIPTS / "normal.jsonl"))
    assert len(read_log(run)) == 1


def test_warn_message_is_json_system_message(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    activate(project, run)
    entry = {"stage": "stage1", "agent_id": "earlier", "estimated_usd": 2.40, "tokens": None, "source": "transcript"}
    write_log(run, [entry])
    result = run_hook(project, payload(TRANSCRIPTS / "normal.jsonl"))
    assert result.returncode == 0
    message = json.loads(result.stdout)
    assert set(message) == {"systemMessage"}
    assert message["systemMessage"].startswith("WARN: stage1 at 80%")


def test_stop_message_is_json_and_exit_is_still_0(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    activate(project, run)
    result = run_hook(project, payload(TRANSCRIPTS / "opus.jsonl"))
    assert result.returncode == 0
    message = json.loads(result.stdout)
    assert message["systemMessage"].startswith("STOP: stage1 budget exceeded")
