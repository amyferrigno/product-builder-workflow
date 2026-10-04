#!/usr/bin/env python3
"""
Render PRD audit markdown from audit JSON.
Validates audit JSON, computes verdict, writes markdown, updates state.
Usage: python scripts/render_audit.py <run_dir>
"""

import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_verdict import compute_verdict, prd_has_ai_addendum

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(2)


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


def load_rubric(repo_root: Path) -> dict:
    """Load the audit rubric."""
    rubric_path = repo_root / "templates" / "audit-prd.rubric.yaml"
    try:
        with open(rubric_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Rubric not found: {rubric_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in rubric: {e}")


def hash_file(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        sha256.update(f.read())
    return sha256.hexdigest()


def find_repo_root(start_path: Path) -> Path:
    """Find the repository root by looking for schemas directory."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / "schemas").exists():
            return current
        current = current.parent
    return Path.cwd()


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python scripts/render_audit.py <run_dir>", file=sys.stderr)
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
    state_path = run_dir / "state.json"

    # Check files exist
    if not audit_path.exists():
        print(f"Error: Audit file not found: {audit_path}", file=sys.stderr)
        sys.exit(2)

    if not prd_path.exists():
        print(f"Error: PRD file not found: {prd_path}", file=sys.stderr)
        sys.exit(2)

    if not state_path.exists():
        print(f"Error: State file not found: {state_path}", file=sys.stderr)
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

    # Load state
    try:
        with open(state_path, 'r') as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid state JSON: {e}", file=sys.stderr)
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

    # Build audit markdown
    markdown_lines = []
    markdown_lines.append(f"# PRD Audit: {verdict}")
    markdown_lines.append("")

    if reasons:
        markdown_lines.append("## Reasons")
        markdown_lines.append("")
        for reason in reasons:
            markdown_lines.append(f"- {reason}")
        markdown_lines.append("")

    # Build dimensions table
    markdown_lines.append("## Scores")
    markdown_lines.append("")
    markdown_lines.append("| Dimension | Blocking | Score | Justification |")
    markdown_lines.append("|-----------|----------|-------|---------------|")

    dim_by_id = {d.get("id"): d for d in rubric.get("dimensions", [])}

    for dim_data in audit.get("dimensions", []):
        dim_id = dim_data.get("id")
        dim_meta = dim_by_id.get(dim_id, {})
        blocking = "Yes" if dim_meta.get("blocking") else "No"
        score = dim_data.get("score")
        justification = dim_data.get("justification", "")
        markdown_lines.append(f"| {dim_id} | {blocking} | {score} | {justification} |")

    markdown_lines.append("")

    # Build fixes list
    fixes = []
    flagged_sections = set()
    for dim_data in audit.get("dimensions", []):
        score = dim_data.get("score")
        if score and score < 3:
            dim_id = dim_data.get("id")
            fix = dim_data.get("fix")
            sections = dim_data.get("sections", [])
            if fix and sections:
                fixes.append(f"- **{dim_id}**: {fix} (sections: {', '.join(sections)})")
                flagged_sections.update(sections)

    if fixes:
        markdown_lines.append("## Fixes needed")
        markdown_lines.append("")
        for fix in fixes:
            markdown_lines.append(fix)
        markdown_lines.append("")

    # Build flagged sections
    if flagged_sections:
        markdown_lines.append("## Flagged sections")
        markdown_lines.append("")
        for section in sorted(flagged_sections):
            markdown_lines.append(f"- {section}")
        markdown_lines.append("")

    # Build hallucination check
    markdown_lines.append("## Hallucination check")
    markdown_lines.append("")
    hallucination = audit.get("hallucination_check", {})
    has_hallucinations = any([
        hallucination.get("unsupported_numbers"),
        hallucination.get("unsupported_quotes"),
        hallucination.get("unsupported_decisions")
    ])

    if not has_hallucinations:
        markdown_lines.append("None")
    else:
        if hallucination.get("unsupported_numbers"):
            markdown_lines.append("**Unsupported numbers:**")
            for item in hallucination["unsupported_numbers"]:
                markdown_lines.append(f"- {item}")
        if hallucination.get("unsupported_quotes"):
            markdown_lines.append("**Unsupported quotes:**")
            for item in hallucination["unsupported_quotes"]:
                markdown_lines.append(f"- {item}")
        if hallucination.get("unsupported_decisions"):
            markdown_lines.append("**Unsupported decisions:**")
            for item in hallucination["unsupported_decisions"]:
                markdown_lines.append(f"- {item}")

    markdown_lines.append("")

    # Write markdown
    audit_md_path = run_dir / "prd.audit.md"
    try:
        with open(audit_md_path, 'w') as f:
            f.write('\n'.join(markdown_lines))
    except IOError as e:
        print(f"Error: Cannot write audit markdown: {e}", file=sys.stderr)
        sys.exit(2)

    # Update state
    try:
        prd_audit_hash = hash_file(audit_path)

        if "artifact_hashes" not in state:
            state["artifact_hashes"] = {}
        state["artifact_hashes"]["prd"] = current_prd_hash
        state["artifact_hashes"]["prd_audit"] = prd_audit_hash

        if "verdicts" not in state:
            state["verdicts"] = {}
        state["verdicts"]["prd"] = verdict

        state["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

        # Update status
        if verdict in ("PASS", "PASS_WITH_RISK"):
            state["status"] = "awaiting_approval"

        # Validate updated state
        state_schema = load_schema("state", repo_root)
        validator = Draft202012Validator(state_schema)
        errors = list(validator.iter_errors(state))
        if errors:
            error_msgs = [e.message for e in errors]
            print(f"Error: Updated state validation failed: {'; '.join(error_msgs)}", file=sys.stderr)
            sys.exit(2)

        # Write updated state
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error: Cannot update state: {e}", file=sys.stderr)
        sys.exit(2)

    # Output
    print(verdict)

    # Exit code
    if verdict in ("PASS", "PASS_WITH_RISK"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
