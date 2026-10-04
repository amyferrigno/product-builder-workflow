#!/usr/bin/env python3
"""
Compute PRD audit verdict based on audit JSON and rubric.
Usage: python scripts/audit_verdict.py <run_dir>
"""

import re
import sys
import json
import hashlib
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(2)


def load_rubric(repo_root: Path) -> dict:
    """Load the audit rubric from templates/audit-prd.rubric.yaml."""
    rubric_path = repo_root / "templates" / "audit-prd.rubric.yaml"
    try:
        with open(rubric_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Rubric not found: {rubric_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in rubric: {e}")


def load_schema(schema_name: str, repo_root: Path) -> dict:
    """Load a JSON schema."""
    schema_path = repo_root / "schemas" / f"{schema_name}.schema.json"
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid schema JSON: {e}")


def hash_file(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            sha256.update(f.read())
    except IOError as e:
        raise IOError(f"Cannot read file: {e}")
    return sha256.hexdigest()


def prd_has_ai_addendum(prd_text: str) -> bool:
    """True when the PRD text contains any AI addendum heading ('## A<N>. ').

    Whitespace-tolerant on purpose: it must accept every heading form that
    validate_prd.py accepts, or the AI dimensions could be skipped.
    """
    return re.search(r'^\s*#{1,6}\s*A\d+\.\s', prd_text, re.MULTILINE) is not None


def compute_verdict(audit: dict, rubric: dict, current_prd_hash: str, prd_has_ai_addendum: bool):
    """
    Compute verdict and reasons from audit.

    Returns (verdict, reasons_list) where:
    - verdict is one of: "PASS", "PASS_WITH_RISK", "FAIL"
    - reasons_list is a list of human-readable strings explaining the verdict

    prd_has_ai_addendum is derived from the PRD text by the caller and must
    agree with audit["ai_feature"].
    """
    reasons = []

    # The auditor's ai_feature flag must match what the PRD text shows
    ai_flag = bool(audit.get("ai_feature", False))
    if ai_flag != bool(prd_has_ai_addendum):
        has_word = "has an" if prd_has_ai_addendum else "has no"
        reasons.append(
            f"ai_feature mismatch: audit says {str(ai_flag).lower()} but the PRD {has_word} AI addendum"
        )
        return "FAIL", reasons

    # Get required dimensions from rubric
    blocking_dims = {}
    ai_only_dims = {}
    all_dims = {}

    for dim in rubric.get("dimensions", []):
        dim_id = dim.get("id")
        all_dims[dim_id] = dim
        if dim.get("ai_only"):
            ai_only_dims[dim_id] = dim
        if dim.get("blocking"):
            blocking_dims[dim_id] = dim

    # Determine required dimensions
    ai_feature = audit.get("ai_feature", False)
    required_dims = set()
    for dim_id in all_dims.keys():
        if all_dims[dim_id].get("ai_only"):
            if ai_feature:
                required_dims.add(dim_id)
        else:
            required_dims.add(dim_id)

    # Parse audit dimensions
    audit_dims = {}
    for dim in audit.get("dimensions", []):
        dim_id = dim.get("id")
        if dim_id in audit_dims:
            reasons.append(f"Duplicate dimension: {dim_id}")
            return "FAIL", reasons
        audit_dims[dim_id] = dim

    # Check for missing required dimensions
    for required_dim in required_dims:
        if required_dim not in audit_dims:
            reasons.append(f"Missing required dimension: {required_dim}")

    if reasons:
        return "FAIL", reasons

    # Check prd_hash
    if audit.get("prd_hash") != current_prd_hash:
        reasons.append(f"PRD hash mismatch: audit has '{audit.get('prd_hash')}', current is '{current_prd_hash}'")
        return "FAIL", reasons

    # Check hallucination lists
    hallucination = audit.get("hallucination_check", {})
    if hallucination.get("unsupported_numbers"):
        reasons.append(f"Hallucination: unsupported numbers: {', '.join(hallucination['unsupported_numbers'])}")
    if hallucination.get("unsupported_quotes"):
        reasons.append(f"Hallucination: unsupported quotes: {', '.join(hallucination['unsupported_quotes'])}")
    if hallucination.get("unsupported_decisions"):
        reasons.append(f"Hallucination: unsupported decisions: {', '.join(hallucination['unsupported_decisions'])}")

    if reasons:
        return "FAIL", reasons

    # Check dimensions
    has_risk = False
    for dim_id, dim_data in audit_dims.items():
        # Skip dimensions not in required set (e.g., AI dimensions when ai_feature=false)
        if dim_id not in required_dims:
            continue

        score = dim_data.get("score")

        # Check for score 1
        if score == 1:
            reasons.append(f"Dimension {dim_id} scores 1 (missing/wrong)")

        # Check for blocking dimensions below 3
        if dim_id in blocking_dims and score < 3:
            reasons.append(f"Blocking dimension {dim_id} scores {score} (minimum 3 required)")

        # Track risk score
        if score == 2:
            has_risk = True

    if reasons:
        return "FAIL", reasons

    # Determine PASS vs PASS_WITH_RISK
    if has_risk:
        return "PASS_WITH_RISK", reasons

    return "PASS", reasons


def find_repo_root(start_path: Path) -> Path:
    """Find the repository root by looking for schemas directory."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / "schemas").exists():
            return current
        current = current.parent
    # Fallback to current working directory
    return Path.cwd()


def verdict_for_run(run_dir: Path, repo_root: Path):
    """Recompute the PRD verdict from prd.audit.json and the current prd.md.

    Returns (verdict, reasons). Raises ValueError if the audit is missing,
    unreadable or fails its schema.
    """
    run_dir = Path(run_dir)
    audit_path = run_dir / "prd.audit.json"
    prd_path = run_dir / "prd.md"
    if not audit_path.exists():
        raise ValueError("PRD audit file (prd.audit.json) not found; run the audit first")
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        prd_text = prd_path.read_text(encoding="utf-8")
        current_hash = hash_file(prd_path)
        errors = list(Draft202012Validator(load_schema("prd-audit", repo_root)).iter_errors(audit))
        rubric = load_rubric(repo_root)
    except (OSError, ValueError, FileNotFoundError) as e:
        raise ValueError(f"Cannot read PRD audit ({e}); run the audit first")
    if errors:
        raise ValueError(
            f"PRD audit is invalid ({'; '.join(e.message for e in errors)}); run the audit first"
        )
    return compute_verdict(audit, rubric, current_hash, prd_has_ai_addendum(prd_text))


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python scripts/audit_verdict.py <run_dir>", file=sys.stderr)
        sys.exit(2)

    run_dir = Path(sys.argv[1])

    # Check run directory exists
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(2)

    # Find repo root
    try:
        repo_root = find_repo_root(run_dir)
    except Exception as e:
        print(f"Error: Cannot find repository root: {e}", file=sys.stderr)
        sys.exit(2)

    # Load files
    audit_path = run_dir / "prd.audit.json"
    prd_path = run_dir / "prd.md"

    # Check files exist
    if not audit_path.exists():
        print(f"Error: Audit file not found: {audit_path}", file=sys.stderr)
        sys.exit(2)

    if not prd_path.exists():
        print(f"Error: PRD file not found: {prd_path}", file=sys.stderr)
        sys.exit(2)

    # Load and validate audit JSON
    try:
        with open(audit_path, 'r') as f:
            audit = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid audit JSON: {e}", file=sys.stderr)
        sys.exit(2)

    # Validate audit against schema
    try:
        audit_schema = load_schema("prd-audit", repo_root)
        validator = Draft202012Validator(audit_schema)
        errors = list(validator.iter_errors(audit))
        if errors:
            error_msgs = [e.message for e in errors]
            print(f"Error: Audit JSON validation failed: {'; '.join(error_msgs)}", file=sys.stderr)
            sys.exit(2)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # Load rubric
    try:
        rubric = load_rubric(repo_root)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # Compute PRD hash
    try:
        current_prd_hash = hash_file(prd_path)
    except IOError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # Compute verdict
    try:
        with open(prd_path, 'r') as f:
            has_ai = prd_has_ai_addendum(f.read())
        verdict, reasons = compute_verdict(audit, rubric, current_prd_hash, has_ai)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # Output
    print(verdict)
    for reason in reasons:
        print(reason)

    # Exit code
    if verdict in ("PASS", "PASS_WITH_RISK"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
