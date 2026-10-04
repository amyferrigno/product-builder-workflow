#!/usr/bin/env python3
"""
Decide whether a run gets a PRD or a no-PRD memo.
Usage: python scripts/prd_decision.py <run_dir> [--force-prd "<reason>" | --clear-force]
Prints PRD or MEMO, then the reasons, one per line. Exit 0.
MEMO when the primary problem is UNVALIDATED and no evidence card and no anecdote supports it.
Only evidence cards and anecdotes that pass their JSON schema count; invalid ones are named and ignored.
Sets state.json "outcome" (and "forced_prd_reason" when forced). A forced run stays PRD until --clear-force.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_prd as vp  # noqa: E402

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
STATE_SCHEMA = SCHEMAS / "state.schema.json"


def _validator(name: str) -> "jsonschema.Draft202012Validator":
    schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def _evidence_supporting(run_path: Path, problem_id: str) -> Tuple[List[str], List[str]]:
    """Return (ids of valid cards supporting the problem, ids of invalid cards)."""
    found: List[str] = []
    ignored: List[str] = []
    evidence_dir = run_path / "03-evidence"
    if not evidence_dir.is_dir():
        return found, ignored
    validator = _validator("evidence.schema.json")
    for card_file in sorted(evidence_dir.glob("EV-*.json")):
        try:
            card = json.loads(card_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ignored.append(card_file.stem)
            continue
        card_id = str(card.get("id") or card_file.stem) if isinstance(card, dict) else card_file.stem
        if not isinstance(card, dict) or not validator.is_valid(card):
            ignored.append(card_id)
        elif card.get("supports_problem") == problem_id:
            found.append(card_id)
    return found, ignored


def _anecdotes_supporting(run_path: Path, problem_id: str) -> Tuple[List[str], List[str]]:
    """Return (ids of valid anecdotes linked to the problem, labels of invalid records)."""
    anecdote_file = run_path / "04-anecdotes.json"
    if not anecdote_file.is_file():
        return [], []
    try:
        data = json.loads(anecdote_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], []
    if isinstance(data, dict):
        data = data.get("anecdotes", [])
    if not isinstance(data, list):
        return [], []
    validator = _validator("anecdote.schema.json")
    found: List[str] = []
    ignored: List[str] = []
    for position, record in enumerate(data, start=1):
        label = str(record.get("id")) if isinstance(record, dict) and record.get("id") else f"#{position}"
        if not isinstance(record, dict) or not validator.is_valid(record):
            ignored.append(label)
        elif record.get("linked_problem") == problem_id:
            found.append(label)
    return found, ignored


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
    evidence, bad_cards = _evidence_supporting(run_path, primary)
    anecdotes, bad_anecdotes = _anecdotes_supporting(run_path, primary)
    notes = [f"Ignored invalid evidence card {c}." for c in bad_cards]
    notes += [f"Ignored invalid anecdote {a}." for a in bad_anecdotes]
    if evidence or anecdotes:
        support = ", ".join(evidence + anecdotes)
        return "PRD", [f"The primary problem {primary} is UNVALIDATED, but it is supported by {support}."] + notes
    return "MEMO", [
        f"The primary problem {primary} is UNVALIDATED.",
        f"No evidence card supports {primary}.",
        f"No customer anecdote supports {primary}.",
    ] + notes


def _forced_reason(run_path: Path) -> Optional[str]:
    """The forced_prd_reason recorded in state.json, or None."""
    try:
        state = json.loads((run_path / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    reason = state.get("forced_prd_reason") if isinstance(state, dict) else None
    return reason if isinstance(reason, str) and reason.strip() else None


def _update_state(run_path: Path, outcome: str, forced_reason: str = None, clear_force: bool = False) -> bool:
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
    if clear_force:
        state.pop("forced_prd_reason", None)
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
    parser.add_argument("--clear-force", action="store_true",
                        help="remove an earlier forced PRD decision, then decide normally")
    args = parser.parse_args(argv)

    run_path = Path(args.run_dir)
    if args.force_prd is not None and not args.force_prd.strip():
        print("Error: --force-prd needs a non-empty reason", file=sys.stderr)
        return 1
    if args.force_prd is not None and args.clear_force:
        print("Error: use either --force-prd or --clear-force, not both", file=sys.stderr)
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

    earlier = None if args.clear_force else _forced_reason(run_path)
    if earlier is not None:  # a human decision stays until a human clears it
        _update_state(run_path, "prd")
        print("PRD")
        print(f"PRD was forced earlier: {earlier}")
        return 0

    _update_state(run_path, "no_prd_memo" if decision == "MEMO" else "prd", clear_force=args.clear_force)
    print(decision)
    for line in reasons:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
