"""Test the guard_jira_write hook: no Jira MCP writes in dry-run, no unapproved jira_publish.py."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tickets_helpers import make_tickets_run, write_manifest  # noqa: E402
from ux_gate_helpers import write_state  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "guard_jira_write.py"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"

CONFIG = "project: demo\njira:\n  mode: dry_run\n  site: x\n"


def make_project(tmp_path: Path, config: bool = True) -> Path:
    """tmp_path is the project dir (copy of scripts/ and a pm.config.yaml)."""
    shutil.copytree(REPO_ROOT / "scripts", tmp_path / "scripts")
    if config:
        (tmp_path / "pm.config.yaml").write_text(CONFIG, encoding="utf-8")
    return tmp_path


def run_hook_raw(project: Path, stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True,
        env={"CLAUDE_PROJECT_DIR": str(project)}, cwd=REPO_ROOT,
    )


def run_mcp(project: Path, tool: str) -> subprocess.CompletedProcess:
    return run_hook_raw(project, json.dumps({"tool_name": tool, "tool_input": {}}))


def run_bash(project: Path, command: str) -> subprocess.CompletedProcess:
    return run_hook_raw(project, json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}))


def approved_run(project: Path) -> Path:
    """Run dir project/run with a valid tickets approval (temp decisions file)."""
    run = make_tickets_run(project)
    write_state(run)
    decisions = project / "decisions.test.md"
    decisions.write_text("# Decisions\n\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/approve.py", str(run), "tickets", "--decisions-file", str(decisions)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return run


def test_blocks_jira_mcp_writes(tmp_path):
    project = make_project(tmp_path)
    for tool in ("mcp__atlassian__createJiraIssue", "mcp__jira__update_issue",
                 "mcp__atlassian__addCommentToJiraIssue", "mcp__atlassian__transitionJiraIssue"):
        result = run_mcp(project, tool)
        assert result.returncode == 2, tool
        assert "only scripts/jira_publish.py may write to Jira" in result.stderr


def test_blocks_mcp_writes_when_mode_is_publish(tmp_path):
    project = make_project(tmp_path)
    (project / "pm.config.yaml").write_text(CONFIG.replace("dry_run", "publish"), encoding="utf-8")
    for tool in ("mcp__atlassian__createJiraIssue", "mcp__jira__update_issue"):
        result = run_mcp(project, tool)
        assert result.returncode == 2, tool
        assert "only scripts/jira_publish.py may write to Jira" in result.stderr
    for tool in ("mcp__atlassian__getJiraIssue", "mcp__atlassian__searchJiraIssuesUsingJql"):
        assert run_mcp(project, tool).returncode == 0, tool


def test_allows_read_only_and_non_jira_mcp(tmp_path):
    project = make_project(tmp_path)
    for tool in ("mcp__atlassian__getJiraIssue", "mcp__atlassian__searchJiraIssuesUsingJql",
                 "mcp__warehouse__query"):
        assert run_mcp(project, tool).returncode == 0, tool


def test_allows_read_tools_with_write_words_in_name(tmp_path):
    project = make_project(tmp_path)
    for tool in ("mcp__atlassian__getTransitionsForJiraIssue", "mcp__atlassian__getJiraIssueRemoteIssueLinks"):
        assert run_mcp(project, tool).returncode == 0, tool


def test_blocks_set_and_patch_writes(tmp_path):
    project = make_project(tmp_path)
    for tool in ("mcp__atlassian__setJiraIssueField", "mcp__jira__patch_issue"):
        assert run_mcp(project, tool).returncode == 2, tool


def test_blocks_read_prefixed_names_that_write(tmp_path):
    project = make_project(tmp_path)
    for tool in ("mcp__atlassian__getOrCreateJiraIssue", "mcp__jira__fetchAndUpdateIssue",
                 "mcp__jira__list_and_delete", "mcp__jira__bulk_upsert", "mcp__jira__removeLabel"):
        assert run_mcp(project, tool).returncode == 2, tool


def test_allows_allowlisted_and_plain_read_tools(tmp_path):
    project = make_project(tmp_path)
    for tool in ("mcp__atlassian__getJiraIssue", "mcp__atlassian__getTransitionsForJiraIssue",
                 "mcp__atlassian__getJiraIssueRemoteIssueLinks", "mcp__atlassian__searchJiraIssuesUsingJql"):
        assert run_mcp(project, tool).returncode == 0, tool


def test_blocks_jira_tools_that_are_not_reads(tmp_path):
    project = make_project(tmp_path)
    for tool in ("mcp__jira__writeIssue", "mcp__jira__bulk_import",
                 "mcp__jira__mergeIssues", "mcp__jira__do_stuff"):
        assert run_mcp(project, tool).returncode == 2, tool


def test_allows_atlassian_user_info(tmp_path):
    project = make_project(tmp_path)
    assert run_mcp(project, "mcp__atlassian__atlassianUserInfo").returncode == 0


def test_blocks_mcp_write_when_config_missing(tmp_path):
    project = make_project(tmp_path, config=False)
    assert run_mcp(project, "mcp__atlassian__createJiraIssue").returncode == 2


def test_blocks_curl_to_atlassian(tmp_path):
    project = make_project(tmp_path)
    result = run_bash(project, "curl -X POST https://acme.atlassian.net/rest/api/3/issue -d @x.json")
    assert result.returncode == 2
    assert "atlassian.net" in result.stderr


def test_allows_unrelated_curl_and_bash(tmp_path):
    project = make_project(tmp_path)
    for command in ("curl https://example.com/data.json", "ls", "make test", "cat scripts/jira_publish.py"):
        assert run_bash(project, command).returncode == 0, command


def test_blocks_publish_without_approval(tmp_path):
    project = make_project(tmp_path)
    run = make_tickets_run(project)
    result = run_bash(project, f"python3 scripts/jira_publish.py {run.relative_to(project)}")
    assert result.returncode == 2
    assert "/pm-approve tickets run" in result.stderr


def test_blocks_publish_with_stale_approval(tmp_path):
    project = make_project(tmp_path)
    run = approved_run(project)
    manifest = json.loads((run / "tickets.manifest.json").read_text())
    manifest["epics"][0]["summary"] = "[Scheduling] Deliver something else"
    write_manifest(run, manifest)
    result = run_bash(project, f"python3 scripts/jira_publish.py {run}")
    assert result.returncode == 2
    assert "stale" in result.stderr
    assert "/pm-approve tickets run" in result.stderr


def test_blocks_publish_without_run_dir(tmp_path):
    project = make_project(tmp_path)
    assert run_bash(project, "python3 scripts/jira_publish.py").returncode == 2
    assert run_bash(project, "python3 scripts/jira_publish.py --config pm.config.yaml").returncode == 2


def test_allows_publish_with_valid_approval(tmp_path):
    project = make_project(tmp_path)
    run = approved_run(project)
    assert run_bash(project, f"python3 scripts/jira_publish.py {run}").returncode == 0
    relative = run.relative_to(project)
    assert run_bash(project, f"python3 scripts/jira_publish.py {relative} --config pm.config.yaml").returncode == 0


def test_live_publish_with_valid_approval_asks_a_human(tmp_path):
    project = make_project(tmp_path)
    run = approved_run(project)
    for command in (f"python3 scripts/jira_publish.py {run} --publish",
                    f"python3 scripts/jira_publish.py --publish {run.relative_to(project)}"):
        result = run_bash(project, command)
        assert result.returncode == 0, command
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        assert decision["hookEventName"] == "PreToolUse"
        assert decision["permissionDecision"] == "ask"
        assert decision["permissionDecisionReason"] == "Live Jira publish for run: a human must confirm"


def test_live_publish_without_approval_is_blocked(tmp_path):
    project = make_project(tmp_path)
    run = make_tickets_run(project)
    result = run_bash(project, f"python3 scripts/jira_publish.py {run} --publish")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "/pm-approve tickets run" in result.stderr


def test_dry_run_with_valid_approval_stays_silent(tmp_path):
    project = make_project(tmp_path)
    run = approved_run(project)
    result = run_bash(project, f"python3 scripts/jira_publish.py {run}")
    assert result.returncode == 0
    assert result.stdout == ""


def test_malformed_input_does_not_crash(tmp_path):
    project = make_project(tmp_path)
    for stdin in ("", "not json", "[]", '{"tool_name": 5, "tool_input": "x"}', '{"tool_name": "Bash"}'):
        result = run_hook_raw(project, stdin)
        assert result.returncode == 0, stdin
        assert "Traceback" not in result.stderr


def test_settings_registers_hook_under_both_matchers():
    hooks = json.loads(SETTINGS.read_text())["hooks"]["PreToolUse"]
    for matcher in ("Bash", "mcp__.*"):
        entries = [e for e in hooks if e["matcher"] == matcher]
        assert entries, matcher
        commands = [h["command"] for e in entries for h in e["hooks"]]
        assert any("guard_jira_write.py" in c for c in commands), matcher
