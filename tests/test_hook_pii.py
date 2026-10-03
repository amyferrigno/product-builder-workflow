"""Test the pii_scan PostToolUse hook."""

import json
import subprocess
import sys
from pathlib import Path

HOOK = ".claude/hooks/pii_scan.py"
REPO = Path(__file__).parent.parent


def run_hook(stdin_text):
    result = subprocess.run([sys.executable, HOOK], input=stdin_text, capture_output=True, text=True, cwd=REPO)
    return result.returncode, result.stdout, result.stderr


def call(path, tool="Write"):
    return run_hook(json.dumps({"tool_name": tool, "tool_input": {"file_path": str(path)}}))


def make(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_anecdotes_with_email_blocked(tmp_path):
    p = make(tmp_path, "runs/x/04-anecdotes.json", '[{"quote": "mail me at a.b@example.invalid"}]\n')
    code, out, err = call(p)
    assert code == 2
    assert err.startswith("PII found:")
    assert f"{p}:1: email: a.b@example.invalid" in err
    assert "Traceback" not in err


def test_candidates_file_with_email_blocked(tmp_path):
    p = make(tmp_path, "runs/x/04-anecdotes.candidates.json", "mail a.b@example.invalid\n")
    code, _, err = call(p, tool="Edit")
    assert code == 2 and "PII found:" in err and "a.b@example.invalid" in err


def test_clean_anecdotes_allowed(tmp_path):
    p = make(tmp_path, "runs/x/04-anecdotes.json", '[{"quote": "Scheduling takes too long on 2026-09-12 (EV-003)."}]\n')
    code, out, err = call(p)
    assert code == 0 and err == "" and out == ""


def test_prd_with_phone_blocked(tmp_path):
    p = make(tmp_path, "runs/x/prd.md", "# PRD\n\nCall +00 000 555 0101 for details.\n")
    code, _, err = call(p)
    assert code == 2
    assert "PII found:" in err
    assert f"{p}:3: phone: +00 000 555 0101" in err


def test_unrelated_path_allowed_even_with_pii(tmp_path):
    p = make(tmp_path, "runs/x/notes.md", "a@example.invalid\n")
    code, _, err = call(p)
    assert code == 0 and err == ""


def test_watched_name_outside_runs_allowed(tmp_path):
    p = make(tmp_path, "docs/prd.md", "a@example.invalid\n")
    assert call(p)[0] == 0


def test_nested_file_under_run_not_scanned(tmp_path):
    p = make(tmp_path, "runs/x/sub/prd.md", "a@example.invalid\n")
    assert call(p)[0] == 0


def test_missing_file_allowed(tmp_path):
    code, _, err = call(tmp_path / "runs" / "x" / "prd.md")
    assert code == 0 and "Traceback" not in err


def test_malformed_stdin_allowed():
    for text in ("not json", "", "[1, 2]", '{"tool_input": "x"}', "{}"):
        code, _, err = run_hook(text)
        assert code == 0, text
        assert "Traceback" not in err


def test_mixed_case_and_dotdot_path_still_scanned(tmp_path):
    make(tmp_path, "Runs/x/prd.md", "reach a@example.invalid\n")
    code, _, err = call(f"{tmp_path}/Runs/x/../x/prd.md")
    assert code == 2 and "a@example.invalid" in err


def test_relative_path_resolved_from_project_dir():
    # Relative path to a file that does not exist in the repo: allowed, no traceback.
    code, _, err = run_hook(json.dumps({"tool_input": {"file_path": "runs/none/prd.md"}}))
    assert code == 0 and "Traceback" not in err


def test_all_findings_listed_one_per_line(tmp_path):
    p = make(tmp_path, "runs/x/prd.md", "a@example.invalid\nb@example.invalid\n")
    code, _, err = call(p)
    assert code == 2
    assert err.splitlines()[0] == "PII found:"
    assert len(err.strip().splitlines()) == 3
