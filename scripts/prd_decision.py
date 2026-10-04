#!/usr/bin/env python3
"""
Decide whether a run gets a PRD or a no-PRD memo.
Usage: python scripts/prd_decision.py <run_dir> [--force-prd "<reason>"]
Prints PRD or MEMO, then the reasons, one per line. Exit 0.
MEMO when the primary problem is UNVALIDATED and no evidence card and no anecdote supports it.
Sets state.json "outcome" (and "forced_prd_reason" when forced).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_prd as vp  # noqa: E402

STATE_SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "state.schema.json"


def _evidence_supporting(run_path: Path, problem_id: str) -> List[str]:
    found = []
    evidence_dir = run_path / "03-evidence"
    if not evidence_dir.is_dir():
        return found
    for card_file in sorted(evidence_dir.glob("EV-*.json")):
        try:
            card = json.loads(card_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(card, dict) and card.get("supports_problem") == problem_id:
            found.append(str(card.get("id") or card_file.stem))
    return found


def _anecdotes_supporting(run_path: Path, problem_id: str) -> List[str]:
    anecdote_file = run_path / "04-anecdotes.json"
    if not anecdote_file.is_file():
        return []
    try:
        data = json.loads(anecdote_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("anecdotes", [])
    if not isinstance(data, list):
        return []
    return [str(a.get("id")) for a in data if isinstance(a, dict) and a.get("linked_problem") == problem_id]


def decide(run_dir) -> Tuple[str, List[str]]:
    """Return ("PRD" | "MEMO", reasons). Raises FileNotFoundError or ValueError on a bad problem file."""
    run_path = Path(run_dir)
    front = vp.parse_problem_md_front_matter(run_path / "02-problem.md")
    primary = front.get("primary_problem")
    if not isinstance(primary, str) or not primary:
        raise ValueError("02-problem.md has no primary_problem")
    status = None
    for problem in front.get("problems") or []:
        if isinstance(problem, dict) and problem.get("id") == primary:
            status = problem.get("validation_status")
    if status is None:
        raise ValueError(f"primary problem {primary} not found in 02-problem.md")

    if status != "UNVALIDATED":
        return "PRD", [f"The primary problem {primary} is {status}, so a PRD is justified."]
    evidence = _evidence_supporting(run_path, primary)
    anecdotes = _anecdotes_supporting(run_path, primary)
    if evidence or anecdotes:
        support = ", ".join(evidence + anecdotes)
        return "PRD", [f"The primary problem {primary} is UNVALIDATED, but it is supported by {support}."]
    return "MEMO", [
        f"The primary problem {primary} is UNVALIDATED.",
        f"No evidence card supports {primary}.",
        f"No customer anecdote supports {primary}.",
    ]


def _update_state(run_path: Path, outcome: str, forced_reason: str = None) -> bool:
    """Set outcome in state.json after schema validation. False when nothing was written."""
    state_path = run_path / "state.json"
    if not state_path.is_file():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        schema = json.loads(STATE_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("Warning: state.json could not be read; not updated", file=sys.stderr)
        return False
    if not isinstance(state, dict):
        return False
    state["outcome"] = outcome
    if forced_reason is not None:
        state["forced_prd_reason"] = forced_reason
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(state))
    if errors:
        print(f"Warning: state.json would be invalid ({errors[0].message}); not updated", file=sys.stderr)
        return False
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Decide PRD or no-PRD memo for a run.")
    parser.add_argument("run_dir")
    parser.add_argument("--force-prd", default=None, metavar="REASON")
    args = parser.parse_args(argv)

    run_path = Path(args.run_dir)
    if args.force_prd is not None and not args.force_prd.strip():
        print("Error: --force-prd needs a non-empty reason", file=sys.stderr)
        return 1
    try:
        decision, reasons = decide(run_path)
    except (OSError, ValueError) as e:
        print(f"Error: cannot decide: {e}", file=sys.stderr)
        return 1

    if args.force_prd is not None:
        reason = args.force_prd.strip()
        _update_state(run_path, "prd", reason)
        print("PRD")
        print(f"Forced by a human: {reason}")
        return 0

    _update_state(run_path, "no_prd_memo" if decision == "MEMO" else "prd")
    print(decision)
    for line in reasons:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
