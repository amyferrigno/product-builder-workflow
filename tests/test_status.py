"""Tests for scripts/status.py: next step at each point of a run, and the status text."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

from cost_helpers import make_project, make_run, write_log
from status import next_step, status_text
from tickets_hash import tickets_hash
from tickets_helpers import make_tickets_run
from ux_gate_helpers import sha
from ux_hash import ux_hash

STATUS_SCRIPT = REPO_ROOT / "scripts" / "status.py"


def cli(*args: str, cwd: Path = REPO_ROOT, script: Path = STATUS_SCRIPT):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, cwd=cwd)


def step_of(run: Path) -> str:
    result = cli(str(run), "--next")
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def copy_in(full: Path, run: Path, rel: str) -> None:
    src = full / rel
    dst = run / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy(src, dst)


def make_full_run(tmp_path: Path) -> Path:
    """A run with approved PRD, UX and tickets (the helper leaves the tickets approval out)."""
    run = make_tickets_run(tmp_path)
    record = {"artifact": "tickets", "sha256": tickets_hash(run), "prd_sha256": sha(run / "prd.md"),
              "ux_sha256": ux_hash(run), "verdict": None, "override_reason": None,
              "approved_at": "2026-10-03T00:00:00Z"}
    (run / "approvals" / "tickets.approved").write_text(json.dumps(record), encoding="utf-8")
    return run


def test_walk_whole_chain(tmp_path):
    full = make_full_run(tmp_path / "full")
    run = tmp_path / "walk"
    run.mkdir()
    (run / "state.json").write_text(json.dumps({"run_id": "run-1", "stage": "stage1", "status": "in_progress"}))
    assert step_of(run) == "prd"

    copy_in(full, run, "prd.md")
    assert step_of(run) == "prd"  # no audit yet
    (run / "prd.audit.json").write_text("{}", encoding="utf-8")
    assert step_of(run) == "approve_prd"
    copy_in(full, run, "approvals/prd.approved")
    assert step_of(run) == "ux"

    copy_in(full, run, "ux")
    assert step_of(run) == "ux"  # no UX audit yet
    (run / "ux.audit.json").write_text("{}", encoding="utf-8")
    assert step_of(run) == "approve_ux"
    copy_in(full, run, "approvals/ux.approved")
    assert step_of(run) == "tickets"

    copy_in(full, run, "tickets.manifest.json")
    assert step_of(run) == "approve_tickets"
    copy_in(full, run, "approvals/tickets.approved")
    assert step_of(run) == "publish_dry_run"

    (run / "tickets.dryrun.json").write_text("[]", encoding="utf-8")
    assert step_of(run) == "done"

    with open(run / "prd.md", "a", encoding="utf-8") as f:
        f.write("\nAn edit after approval.\n")
    assert step_of(run) == "approve_prd"


def test_memo_branch(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/intake.py", str(REPO_ROOT / "fixtures" / "solution-first-chatbot" / "notes.md"),
         "--slug", "solution-first-chatbot", "--runs-dir", str(tmp_path), "--date", "2026-01-15"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    run = Path(json.loads(result.stdout)["run_dir"])
    assert next_step(run) == "prd"
    for golden in (REPO_ROOT / "fixtures" / "solution-first-chatbot" / "golden").iterdir():
        if golden.is_file():
            shutil.copy(golden, run / golden.name)
    assert step_of(run) == "memo_done"
    assert "No PRD justified" in status_text(run)


def test_invalid_memo_is_not_memo_done(tmp_path):
    run = make_run(make_project(tmp_path))
    (run / "no-prd-memo.md").write_text("## 1. Decision\nNo PRD.\n", encoding="utf-8")
    assert next_step(run) == "prd"


def test_status_text_on_empty_run_does_not_raise(tmp_path):
    run = tmp_path / "empty"
    run.mkdir()
    text = status_text(run)
    assert "not started" in text
    assert "no cost data" in text
    assert "Next: /pm-prd empty" in text
    assert cli(str(run)).returncode == 0


def test_status_text_shows_cost(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    write_log(run, [{"ts": "t", "stage": "stage1", "agent_type": "x", "agent_id": "a", "model": "m",
                     "tokens": None, "estimated_usd": 1.5, "source": "transcript"}])
    result = cli(str(run), script=project / "scripts" / "status.py", cwd=project)
    assert result.returncode == 0, result.stderr
    assert "stage1: spent $1.50 of $3.00 (50.0%)" in result.stdout
    assert "Next: /pm-prd 2026-10-04-demo" in result.stdout


def test_full_run_text_ends_complete(tmp_path):
    run = make_full_run(tmp_path)
    (run / "prd.audit.json").write_text("{}", encoding="utf-8")
    (run / "ux.audit.json").write_text("{}", encoding="utf-8")
    (run / "tickets.dryrun.json").write_text("[]", encoding="utf-8")
    text = status_text(run)
    assert "prd: approved" in text
    assert text.splitlines()[-1] == "Next: Run complete"


def test_no_active_run_exits_1_with_one_line(tmp_path):
    project = make_project(tmp_path)
    result = cli(cwd=project, script=project / "scripts" / "status.py")
    assert result.returncode == 1
    assert len(result.stderr.strip().splitlines()) == 1
    assert "Traceback" not in result.stderr


def test_active_run_is_used_without_argument(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    (project / "runs" / ".active").write_text(run.name + "\n", encoding="utf-8")
    result = cli("--next", cwd=project, script=project / "scripts" / "status.py")
    assert result.returncode == 0
    assert result.stdout.strip() == "prd"
