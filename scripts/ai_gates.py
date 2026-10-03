#!/usr/bin/env python3
"""
Deterministic 5-gate AI decision logic.
Computes verdict based on gate results and red flags.
Usage: python scripts/ai_gates.py < gates.json
"""

import sys
import json
from typing import Dict, List


# Valid gate names
VALID_GATES = {"1", "2", "3", "4", "5"}

# Valid gate results
VALID_RESULTS = {"pass", "fail", "unknown"}

# Valid red flags
VALID_RED_FLAGS = {
    "known_finite_rules",
    "insufficient_data",
    "catastrophic_errors",
    "explainability_required",
    "ux_problem_in_disguise",
    "commodity_tool_rebuild"
}


def compute_verdict(gates: Dict[str, str], red_flags: List[str]) -> str:
    """
    Compute AI verdict based on gate results and red flags.

    Gates: dict with keys "1".."5", values "pass"|"fail"|"unknown"
    Red flags: list of flag strings from VALID_RED_FLAGS

    Rules:
    - Any red flag or any failed gate gives AI_NOT_JUSTIFIED
    - Otherwise any unknown gate gives NEEDS_DATA
    - All five pass and no red flags gives AI_JUSTIFIED

    Raises ValueError if gates or red_flags are invalid.
    """

    # Validate gates
    if not isinstance(gates, dict):
        raise ValueError("gates must be a dict")

    if set(gates.keys()) != VALID_GATES:
        raise ValueError(f"gates must have exactly keys {VALID_GATES}, got {set(gates.keys())}")

    for gate_name, result in gates.items():
        if not isinstance(result, str):
            raise ValueError(f"gate {gate_name} has invalid result type (must be string), got {type(result).__name__}")
        if result not in VALID_RESULTS:
            raise ValueError(f"gate {gate_name} has invalid result '{result}', must be one of {VALID_RESULTS}")

    # Validate red flags
    if not isinstance(red_flags, list):
        raise ValueError("red_flags must be a list")

    for flag in red_flags:
        if not isinstance(flag, str):
            raise ValueError(f"red_flags must contain only strings, got {type(flag).__name__}")
        if flag not in VALID_RED_FLAGS:
            raise ValueError(f"unknown red flag '{flag}', must be one of {VALID_RED_FLAGS}")

    # Apply rules
    # Any red flag gives AI_NOT_JUSTIFIED
    if red_flags:
        return "AI_NOT_JUSTIFIED"

    # Any failed gate gives AI_NOT_JUSTIFIED
    if any(result == "fail" for result in gates.values()):
        return "AI_NOT_JUSTIFIED"

    # Any unknown gate gives NEEDS_DATA
    if any(result == "unknown" for result in gates.values()):
        return "NEEDS_DATA"

    # All five pass and no red flags gives AI_JUSTIFIED
    return "AI_JUSTIFIED"


def main():
    """Read JSON from stdin and print verdict."""
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("Error: Invalid JSON input", file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Error: Invalid JSON input", file=sys.stderr)
        sys.exit(1)

    # Reject non-object JSON
    if not isinstance(data, dict):
        print("Error: Input must be a JSON object", file=sys.stderr)
        sys.exit(1)

    # Extract gates and red_flags
    gates = data.get("gates")
    red_flags = data.get("red_flags", [])

    # Validate gate values are strings or objects
    if isinstance(gates, dict):
        for gate_num, gate_val in gates.items():
            if not isinstance(gate_val, (str, dict)):
                print("Error: Gate values must be strings or objects", file=sys.stderr)
                sys.exit(1)

    try:
        verdict = compute_verdict(gates, red_flags)
        print(json.dumps({"verdict": verdict}, indent=2))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
