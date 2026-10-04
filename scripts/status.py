#!/usr/bin/env python3
"""
Run status: where the run is and what to do next.
Usage: python scripts/status.py [<run_dir>] [--next]
Without a run dir the active run (runs/.active) is used. --next prints one step name:
prd, memo_done, approve_prd, ux, approve_ux, tickets, approve_tickets, publish_dry_run, done.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import active_run
import check_approval
import cost_meter
import validate_memo

REPO_ROOT = Path(__file__).resolve().parent.parent

NEXT_LINES = {
    "prd": "/pm-prd {run_id}",
    "approve_prd": "/pm-approve prd {run_id} (human)",
    "ux": "/pm-ux {run_id}",
    "approve_ux": "/pm-approve ux {run_id} (human)",
    "tickets": "/pm-tickets {run_id}",
    "approve_tickets": "/pm-approve tickets {run_id} (human)",
    "publish_dry_run": "/pm-tickets {run_id} (writes the dry run)",
    "memo_done": "No PRD justified; see no-prd-memo.md",
    "done": "Run complete",
}


def _read_state(run_path: Path) -> Dict[str, Any]:
    try:
        data = json.loads((run_path / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _approved(run_path: Path, artifact: str) -> bool:
    try:
        return bool(check_approval.approval_status(str(run_path), artifact)[0])
    except Exception:
        return False


def _memo_valid(run_path: Path) -> bool:
    if not (run_path / "no-prd-memo.md").is_file():
        return False
    try:
        return not validate_memo.validate_memo(str(run_path))
    except Exception:
        return False


def next_step(run_dir) -> str:
    run_path = Path(run_dir)
    if _memo_valid(run_path):
        return "memo_done"
    if not (run_path / "prd.md").is_file():
        return "prd"
    if not _approved(run_path, "prd"):
        return "approve_prd" if (run_path / "prd.audit.json").is_file() else "prd"
    if not (run_path / "ux").is_dir():
        return "ux"
    if not _approved(run_path, "ux"):
        return "approve_ux" if (run_path / "ux.audit.json").is_file() else "ux"
    if not (run_path / "tickets.manifest.json").is_file():
        return "tickets"
    if not _approved(run_path, "tickets"):
        return "approve_tickets"
    if not (run_path / "tickets.dryrun.json").is_file():
        return "publish_dry_run"
    return "done"


def _cost_lines(run_path: Path) -> List[str]:
    if not (run_path / cost_meter.COST_LOG).is_file():
        return ["  no cost data"]
    try:
        summary = cost_meter.summarise(run_path, cost_meter.load_config())
    except Exception:
        return ["  no cost data"]
    lines = []
    for stage, info in summary.items():
        pct = "n/a" if info["percent"] is None else f"{info['percent']:.1f}%"
        line = (
            f"  {stage}: spent {cost_meter._fmt_money(info['spent_usd'])} "
            f"of {cost_meter._fmt_money(info['budget_usd'])} ({pct})"
        )
        if info["unparsed"]:
            line += f", {info['unparsed']} unparsed"
        lines.append(line)
    return lines


def status_text(run_dir) -> str:
    run_path = Path(run_dir)
    state = _read_state(run_path)
    verdicts = state.get("verdicts") if isinstance(state.get("verdicts"), dict) else {}
    run_id = state.get("run_id") if isinstance(state.get("run_id"), str) else run_path.name

    lines = [
        f"Run: {run_id}",
        f"Stage: {state.get('stage', 'not started')}",
        f"Status: {state.get('status', 'not started')}",
        f"Outcome: {state.get('outcome', 'not decided')}",
        "Verdicts:",
        f"  PRD: {verdicts.get('prd') or 'not started'}",
        f"  UX: {verdicts.get('ux') or 'not started'}",
        "Approvals:",
    ]
    for artifact in ("prd", "ux", "tickets"):
        try:
            ok, message = check_approval.approval_status(str(run_path), artifact)
        except Exception:
            ok, message = False, "not started"
        if not ok and message.startswith("missing"):
            message = "not started" if not _artifact_exists(run_path, artifact) else "not approved yet"
        lines.append(f"  {artifact}: {message}")
    lines.append("Cost (estimate):")
    lines.extend(_cost_lines(run_path))
    step = next_step(run_path)
    lines.append(f"Next: {NEXT_LINES[step].format(run_id=run_id)}")
    return "\n".join(lines)


def _artifact_exists(run_path: Path, artifact: str) -> bool:
    if artifact == "prd":
        return (run_path / "prd.md").is_file()
    if artifact == "ux":
        return (run_path / "ux").is_dir()
    return (run_path / "tickets.manifest.json").is_file()


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    want_next = "--next" in args
    positional = [a for a in args if a != "--next"]
    if len(positional) > 1:
        print("Usage: status.py [<run_dir>] [--next]", file=sys.stderr)
        return 1
    if positional:
        run_path = Path(positional[0])
    else:
        run_path = active_run.get_active(REPO_ROOT)
        if run_path is None:
            print("Error: no active run; pass a run directory", file=sys.stderr)
            return 1
    if not run_path.is_dir():
        print(f"Error: run directory not found: {run_path}", file=sys.stderr)
        return 1
    try:
        print(next_step(run_path) if want_next else status_text(run_path))
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
