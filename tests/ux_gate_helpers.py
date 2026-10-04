"""Helpers for Gate B tests: build a UX run with state, PRD approval and an audit."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from ux_hash import ux_hash
from ux_helpers import make_ux_run

BASE_DIMS = ["req_coverage", "required_states", "accessibility", "token_consistency", "copy_clarity"]
AI_DIMS = ["ai_trust_control_recovery"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit(run: Path, ai: bool, scores: Optional[Dict[str, int]] = None, **overrides) -> dict:
    """A valid audit for the run's current UX; every dimension scores 4 unless overridden."""
    scores = scores or {}
    dim_ids = BASE_DIMS + (AI_DIMS if ai else [])
    dims = []
    for dim_id in dim_ids:
        score = scores.get(dim_id, 4)
        dim = {"id": dim_id, "score": score, "justification": f"{dim_id} looks fine."}
        if score < 3:
            dim["fix"] = f"Improve {dim_id}."
            dim["screens"] = ["SCR-001"]
        dims.append(dim)
    audit = {"run_id": "run-1", "ux_hash": ux_hash(run), "ai_feature": ai, "dimensions": dims}
    audit.update(overrides)
    return audit


def write_state(run: Path) -> None:
    state = {
        "run_id": "run-1",
        "stage": "stage2",
        "status": "in_progress",
        "verdicts": {"prd": "PASS", "ux": None},
        "artifact_hashes": {"prd": sha(run / "prd.md")},
        "approval_hashes": {"prd": None, "ux": None, "tickets": None},
        "jira_keys": {},
        "updated_at": "2026-10-03T00:00:00Z",
    }
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")


def approve_prd_file(run: Path) -> None:
    """Write a valid PRD approval file for the current prd.md."""
    (run / "approvals").mkdir(exist_ok=True)
    approval = {"artifact": "prd", "sha256": sha(run / "prd.md"), "verdict": "PASS",
                "override_reason": None, "approved_at": "2026-10-03T00:00:00Z"}
    (run / "approvals" / "prd.approved").write_text(json.dumps(approval), encoding="utf-8")


def make_gate_run(tmp_path: Path, ai: bool = False, prd_approved: bool = True) -> Path:
    run = make_ux_run(tmp_path, ai=ai)
    write_state(run)
    if prd_approved:
        approve_prd_file(run)
    return run


def render(run: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/render_ux_audit.py", str(run)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def write_audit(run: Path, audit: dict) -> None:
    (run / "ux.audit.json").write_text(json.dumps(audit), encoding="utf-8")


def audited_run(tmp_path: Path, ai: bool = False, scores: Optional[Dict[str, int]] = None,
                prd_approved: bool = True) -> Path:
    """A gate run that has been audited and rendered (verdict in state.json)."""
    run = make_gate_run(tmp_path, ai=ai, prd_approved=prd_approved)
    write_audit(run, build_audit(run, ai, scores))
    render(run)
    return run
