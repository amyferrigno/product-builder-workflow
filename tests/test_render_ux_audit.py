"""Test scripts/render_ux_audit.py."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ux_gate_helpers import (  # noqa: E402
    build_audit, make_gate_run, render, sha, ux_hash, write_audit,
)


def state_of(run):
    return json.loads((run / "state.json").read_text())


def test_render_pass_writes_markdown_and_state(tmp_path):
    run = make_gate_run(tmp_path)
    write_audit(run, build_audit(run, False))
    result = render(run)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"
    md = (run / "ux.audit.md").read_text()
    assert md.startswith("# UX Audit: PASS")
    assert "| req_coverage | Yes | 4 |" in md
    assert "| accessibility | No | 4 |" in md
    assert "Script checks" not in md
    state = state_of(run)
    assert state["verdicts"]["ux"] == "PASS"
    assert state["artifact_hashes"]["ux"] == ux_hash(run)
    assert state["audit_loops"]["ux"] == 1
    assert state["stage"] == "stage2"
    assert state["status"] == "awaiting_approval"
    assert state["updated_at"] != "2026-10-03T00:00:00Z"


def test_render_increments_audit_loops(tmp_path):
    run = make_gate_run(tmp_path)
    write_audit(run, build_audit(run, False))
    render(run)
    render(run)
    assert state_of(run)["audit_loops"]["ux"] == 2


def test_render_pass_with_risk(tmp_path):
    run = make_gate_run(tmp_path)
    write_audit(run, build_audit(run, False, {"copy_clarity": 2}))
    result = render(run)
    assert result.returncode == 0
    assert state_of(run)["verdicts"]["ux"] == "PASS_WITH_RISK"
    assert state_of(run)["status"] == "awaiting_approval"


def test_render_fail_lists_fixes_and_sets_failed(tmp_path):
    run = make_gate_run(tmp_path)
    write_audit(run, build_audit(run, False, {"required_states": 2}))
    result = render(run)
    assert result.returncode == 1
    md = (run / "ux.audit.md").read_text()
    assert md.startswith("# UX Audit: FAIL")
    assert "## Fixes needed" in md
    assert "Improve required_states. (screens: SCR-001)" in md
    assert "## Flagged screens" in md
    state = state_of(run)
    assert state["verdicts"]["ux"] == "FAIL"
    assert state["status"] == "failed"


def test_render_validator_errors_force_fail_with_all_fours(tmp_path):
    run = make_gate_run(tmp_path)
    screen = run / "ux" / "screens" / "SCR-001-home.html"
    screen.write_text(screen.read_text().replace('<section id="state-error" data-state="error">', '<section id="state-oops" data-state="oops">'))
    write_audit(run, build_audit(run, False))  # all 4s, hash taken after the edit
    result = render(run)
    assert result.returncode == 1
    md = (run / "ux.audit.md").read_text()
    assert md.startswith("# UX Audit: FAIL")
    assert "## Script checks" in md
    assert "error" in md.split("## Script checks")[1].split("## Scores")[0]
    assert state_of(run)["verdicts"]["ux"] == "FAIL"


def test_render_ai_run_requires_ai_dimension(tmp_path):
    run = make_gate_run(tmp_path, ai=True)
    write_audit(run, build_audit(run, True))
    assert render(run).returncode == 0
    assert state_of(run)["verdicts"]["ux"] == "PASS"


def test_render_stale_hash_fails(tmp_path):
    run = make_gate_run(tmp_path)
    write_audit(run, build_audit(run, False))
    (run / "ux" / "flows.md").write_text((run / "ux" / "flows.md").read_text() + "\n")
    result = render(run)
    assert result.returncode == 1
    assert "UX hash mismatch" in (run / "ux.audit.md").read_text()


def test_render_invalid_audit_json_exits_2(tmp_path):
    run = make_gate_run(tmp_path)
    audit = build_audit(run, False)
    audit["dimensions"][0]["score"] = 9
    write_audit(run, audit)
    result = render(run)
    assert result.returncode == 2
    assert "validation failed" in result.stderr
    assert not (run / "ux.audit.md").exists()


def test_render_missing_audit_exits_2(tmp_path):
    run = make_gate_run(tmp_path)
    result = render(run)
    assert result.returncode == 2
    assert "Audit file not found" in result.stderr


def test_render_leaves_prd_untouched(tmp_path):
    run = make_gate_run(tmp_path)
    before = sha(run / "prd.md")
    write_audit(run, build_audit(run, False))
    render(run)
    assert sha(run / "prd.md") == before
