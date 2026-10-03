#!/usr/bin/env python3
"""
Compute the UX audit verdict from the audit JSON, the rubric and the script checks.
Usage: python scripts/ux_verdict.py <run_dir>

Script facts beat model scores: any validator error gives FAIL.
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_verdict import prd_has_ai_addendum  # noqa: E402
from ux_hash import ux_hash  # noqa: E402
from validate_ux import validate_ux  # noqa: E402

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_ux_rubric(repo_root: Path = REPO_ROOT) -> dict:
    """Load templates/audit-ux.rubric.yaml."""
    path = Path(repo_root) / "templates" / "audit-ux.rubric.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"Rubric not found: {path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in rubric: {e}")


def load_ux_audit_schema(repo_root: Path = REPO_ROOT) -> dict:
    path = Path(repo_root) / "schemas" / "ux-audit.schema.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"Schema not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid schema JSON: {e}")


def compute_ux_verdict(
    audit: dict,
    rubric: dict,
    current_ux_hash: str,
    prd_has_ai_addendum: bool,
    validator_errors: List[str],
) -> Tuple[str, List[str]]:
    """Return (verdict, reasons); verdict is PASS, PASS_WITH_RISK or FAIL."""
    reasons: List[str] = []

    # Script facts beat model scores
    if validator_errors:
        return "FAIL", [f"Script check: {e}" for e in validator_errors]

    ai_flag = bool(audit.get("ai_feature", False))
    if ai_flag != bool(prd_has_ai_addendum):
        has_word = "has an" if prd_has_ai_addendum else "has no"
        reasons.append(
            f"ai_feature mismatch: audit says {str(ai_flag).lower()} but the PRD {has_word} AI addendum"
        )
        return "FAIL", reasons

    blocking_dims = set()
    required_dims = set()
    for dim in rubric.get("dimensions", []):
        dim_id = dim.get("id")
        if dim.get("blocking"):
            blocking_dims.add(dim_id)
        if not dim.get("ai_only") or ai_flag:
            required_dims.add(dim_id)

    audit_dims = {}
    for dim in audit.get("dimensions", []):
        dim_id = dim.get("id")
        if dim_id in audit_dims:
            return "FAIL", [f"Duplicate dimension: {dim_id}"]
        audit_dims[dim_id] = dim

    for required in sorted(required_dims):
        if required not in audit_dims:
            reasons.append(f"Missing required dimension: {required}")
    if reasons:
        return "FAIL", reasons

    if audit.get("ux_hash") != current_ux_hash:
        return "FAIL", [
            f"UX hash mismatch: audit has '{audit.get('ux_hash')}', current is '{current_ux_hash}'"
        ]

    has_risk = False
    for dim_id, dim_data in audit_dims.items():
        if dim_id not in required_dims:
            continue
        score = dim_data.get("score")
        if score == 1:
            reasons.append(f"Dimension {dim_id} scores 1 (missing/wrong)")
        if dim_id in blocking_dims and score < 3:
            reasons.append(f"Blocking dimension {dim_id} scores {score} (minimum 3 required)")
        if score == 2:
            has_risk = True

    if reasons:
        return "FAIL", reasons
    return ("PASS_WITH_RISK" if has_risk else "PASS"), reasons


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/ux_verdict.py <run_dir>", file=sys.stderr)
        sys.exit(2)
    run_dir = Path(sys.argv[1])
    try:
        audit = json.loads((run_dir / "ux.audit.json").read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(load_ux_audit_schema()).iter_errors(audit))
        if errors:
            print(f"Error: Audit JSON validation failed: {'; '.join(e.message for e in errors)}", file=sys.stderr)
            sys.exit(2)
        rubric = load_ux_rubric()
        has_ai = prd_has_ai_addendum((run_dir / "prd.md").read_text(encoding="utf-8"))
        verdict, reasons = compute_ux_verdict(
            audit, rubric, ux_hash(run_dir), has_ai, validate_ux(run_dir, REPO_ROOT)
        )
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    print(verdict)
    for reason in reasons:
        print(reason)
    sys.exit(0 if verdict in ("PASS", "PASS_WITH_RISK") else 1)


if __name__ == "__main__":
    main()
