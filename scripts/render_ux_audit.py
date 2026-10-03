#!/usr/bin/env python3
"""
Render the UX audit markdown from the audit JSON.
Runs the UX validator and the verdict, writes ux.audit.md, updates state.
Usage: python scripts/render_ux_audit.py <run_dir>
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_verdict import prd_has_ai_addendum  # noqa: E402
from ux_hash import ux_hash  # noqa: E402
from ux_verdict import REPO_ROOT, compute_ux_verdict, load_ux_audit_schema, load_ux_rubric  # noqa: E402
from validate_ux import validate_ux  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(2)


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/render_ux_audit.py <run_dir>", file=sys.stderr)
        sys.exit(2)
    run_dir = Path(sys.argv[1])
    if not run_dir.exists():
        fail(f"Run directory not found: {run_dir}")

    audit_path = run_dir / "ux.audit.json"
    prd_path = run_dir / "prd.md"
    state_path = run_dir / "state.json"
    for label, path in (("Audit file", audit_path), ("PRD file", prd_path), ("State file", state_path)):
        if not path.exists():
            fail(f"{label} not found: {path}")

    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"Invalid audit JSON: {e}")
    try:
        schema_errors = list(Draft202012Validator(load_ux_audit_schema()).iter_errors(audit))
        rubric = load_ux_rubric()
    except (FileNotFoundError, ValueError) as e:
        fail(str(e))
    if schema_errors:
        fail(f"Audit JSON validation failed: {'; '.join(e.message for e in schema_errors)}")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"Invalid state JSON: {e}")

    try:
        current_hash = ux_hash(run_dir)
        has_ai = prd_has_ai_addendum(prd_path.read_text(encoding="utf-8"))
        validator_errors = validate_ux(run_dir, REPO_ROOT)
        verdict, reasons = compute_ux_verdict(audit, rubric, current_hash, has_ai, validator_errors)
    except (OSError, ValueError) as e:
        fail(str(e))

    lines = [f"# UX Audit: {verdict}", ""]
    if validator_errors:
        lines += ["## Script checks", ""]
        lines += [f"- {e}" for e in validator_errors]
        lines.append("")
    if reasons and not validator_errors:
        lines += ["## Reasons", ""]
        lines += [f"- {r}" for r in reasons]
        lines.append("")

    lines += [
        "## Scores", "",
        "| Dimension | Blocking | Score | Justification |",
        "|-----------|----------|-------|---------------|",
    ]
    dim_by_id = {d.get("id"): d for d in rubric.get("dimensions", [])}
    for dim in audit.get("dimensions", []):
        blocking = "Yes" if dim_by_id.get(dim.get("id"), {}).get("blocking") else "No"
        lines.append(f"| {dim.get('id')} | {blocking} | {dim.get('score')} | {dim.get('justification', '')} |")
    lines.append("")

    fixes = []
    flagged = set()
    for dim in audit.get("dimensions", []):
        score = dim.get("score")
        if score and score < 3 and dim.get("fix"):
            screens = dim.get("screens") or []
            suffix = f" (screens: {', '.join(screens)})" if screens else ""
            fixes.append(f"- **{dim.get('id')}**: {dim['fix']}{suffix}")
            flagged.update(screens)
    if fixes:
        lines += ["## Fixes needed", ""] + fixes + [""]
    if flagged:
        lines += ["## Flagged screens", ""] + [f"- {s}" for s in sorted(flagged)] + [""]

    try:
        (run_dir / "ux.audit.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError as e:
        fail(f"Cannot write audit markdown: {e}")

    try:
        state.setdefault("artifact_hashes", {})["ux"] = current_hash
        state.setdefault("verdicts", {})["ux"] = verdict
        loops = state.setdefault("audit_loops", {})
        loops["ux"] = int(loops.get("ux", 0)) + 1
        state["stage"] = "stage2"
        state["status"] = "awaiting_approval" if verdict in ("PASS", "PASS_WITH_RISK") else "failed"
        state["updated_at"] = datetime.utcnow().isoformat() + "Z"

        state_schema = json.loads((REPO_ROOT / "schemas" / "state.schema.json").read_text(encoding="utf-8"))
        state_errors = list(Draft202012Validator(state_schema).iter_errors(state))
        if state_errors:
            fail(f"Updated state validation failed: {'; '.join(e.message for e in state_errors)}")
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except (OSError, ValueError, TypeError, AttributeError) as e:
        fail(f"Cannot update state: {e}")

    print(verdict)
    sys.exit(0 if verdict in ("PASS", "PASS_WITH_RISK") else 1)


if __name__ == "__main__":
    main()
