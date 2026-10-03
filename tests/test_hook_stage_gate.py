"""Test the guard_stage_gate hook: UX needs a PRD approval, tickets need a UX approval."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ux_gate_helpers import approve_prd_file, make_gate_run, sha, ux_hash  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "guard_stage_gate.py"


def make_project(tmp_path: Path, prd_approved: bool = True) -> Path:
    """tmp_path is the project dir (with a copy of scripts/); returns the run dir tmp_path/runs/run."""
    shutil.copytree(REPO_ROOT / "scripts", tmp_path / "scripts")
    (tmp_path / "runs").mkdir()
    return make_gate_run(tmp_path / "runs", prd_approved=prd_approved)


def approve_ux_file(run: Path) -> None:
    approval = {"artifact": "ux", "sha256": ux_hash(run), "prd_sha256": sha(run / "prd.md"),
                "verdict": "PASS", "override_reason": None, "approved_at": "2026-10-03T00:00:00Z"}
    (run / "approvals" / "ux.approved").write_text(json.dumps(approval), encoding="utf-8")


def run_hook(project: Path, file_path: str) -> subprocess.CompletedProcess:
    payload = {"tool_name": "Write", "tool_input": {"file_path": file_path}}
    return subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
        env={"CLAUDE_PROJECT_DIR": str(project)}, cwd=REPO_ROOT,
    )


def test_blocks_ux_write_without_prd_approval(tmp_path):
    run = make_project(tmp_path, prd_approved=False)
    result = run_hook(tmp_path, str(run / "ux" / "spec.md"))
    assert result.returncode == 2
    assert "/pm-approve prd run" in result.stderr
    assert "missing" in result.stderr


def test_blocks_ux_write_when_prd_approval_is_stale(tmp_path):
    run = make_project(tmp_path)
    (run / "prd.md").write_text((run / "prd.md").read_text() + "\nedited\n", encoding="utf-8")
    result = run_hook(tmp_path, str(run / "ux" / "screens" / "SCR-001-x.html"))
    assert result.returncode == 2
    assert "stale" in result.stderr
    assert "/pm-approve prd run" in result.stderr


def test_allows_ux_write_with_valid_prd_approval(tmp_path):
    run = make_project(tmp_path)
    assert run_hook(tmp_path, str(run / "ux" / "spec.md")).returncode == 0
    assert run_hook(tmp_path, str(run / "ux" / "screens" / "new.html")).returncode == 0


def test_blocks_tickets_without_ux_approval(tmp_path):
    run = make_project(tmp_path)
    result = run_hook(tmp_path, str(run / "tickets.manifest.json"))
    assert result.returncode == 2
    assert "/pm-approve ux run" in result.stderr


def test_blocks_tickets_when_ux_approval_is_stale(tmp_path):
    run = make_project(tmp_path)
    approve_ux_file(run)
    screen = next((run / "ux" / "screens").glob("*.html"))
    screen.write_text(screen.read_text() + "<!-- changed -->", encoding="utf-8")
    result = run_hook(tmp_path, str(run / "tickets.manifest.json"))
    assert result.returncode == 2
    assert "stale" in result.stderr


def test_allows_tickets_with_valid_ux_approval(tmp_path):
    run = make_project(tmp_path)
    approve_ux_file(run)
    assert run_hook(tmp_path, str(run / "tickets.manifest.json")).returncode == 0


def test_dotdot_path_into_ux_is_still_blocked(tmp_path):
    run = make_project(tmp_path, prd_approved=False)
    tricky = str(run / "notes" / ".." / "ux" / "spec.md")
    assert run_hook(tmp_path, tricky).returncode == 2


def test_relative_path_is_blocked(tmp_path):
    make_project(tmp_path, prd_approved=False)
    assert run_hook(tmp_path, "runs/run/ux/spec.md").returncode == 2
    assert run_hook(tmp_path, "runs/run/tickets.manifest.json").returncode == 2


def test_symlink_into_ux_is_blocked(tmp_path):
    run = make_project(tmp_path, prd_approved=False)
    link = tmp_path / "shortcut"
    link.symlink_to(run / "ux")
    assert run_hook(tmp_path, str(link / "spec.md")).returncode == 2


def test_non_run_paths_are_allowed(tmp_path):
    make_project(tmp_path, prd_approved=False)
    assert run_hook(tmp_path, "fixtures/ai-clear-fit/golden/ux/spec.md").returncode == 0
    assert run_hook(tmp_path, "README.md").returncode == 0
    assert run_hook(tmp_path, "docs/tickets.md").returncode == 0


def test_prd_and_other_run_files_are_allowed(tmp_path):
    run = make_project(tmp_path, prd_approved=False)
    assert run_hook(tmp_path, str(run / "prd.md")).returncode == 0
    assert run_hook(tmp_path, str(run / "ticketsfoo.md")).returncode == 0
    assert run_hook(tmp_path, str(run / "sub" / "tickets.json")).returncode == 0


def test_malformed_input_does_not_crash():
    for text in ("", "not valid json", "[]", '{"tool_input": "x"}'):
        result = subprocess.run(
            [sys.executable, str(HOOK)], input=text, capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, text
        assert "Traceback" not in result.stderr


def test_settings_json_registers_hook():
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    entries = [e for e in settings["hooks"]["PreToolUse"] if e["matcher"] == "Write|Edit"]
    commands = [h["command"] for e in entries for h in e["hooks"]]
    assert 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_stage_gate.py"' in commands
    assert any("guard_approvals.py" in c for c in commands)
