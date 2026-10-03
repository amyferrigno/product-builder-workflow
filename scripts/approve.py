#!/usr/bin/env python3
"""
Approve a PRD artifact after audit.
Usage: python scripts/approve.py <run_dir> prd [--override "reason"] [--decisions-file decisions.md]
"""

import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("Error: Missing required module: jsonschema", file=sys.stderr)
    sys.exit(1)


def hash_file(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, IOError):
        raise ValueError(f"Cannot read {file_path}")


def load_state(run_dir: str) -> dict:
    """Load state.json from run_dir."""
    state_path = Path(run_dir) / "state.json"
    try:
        with open(state_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"state.json not found in {run_dir}")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in state.json")


def load_schema(schema_name: str, repo_root: Path) -> dict:
    """Load a schema file."""
    schema_path = repo_root / "schemas" / f"{schema_name}.schema.json"
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Schema not found: {schema_path}")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid schema {schema_path}")


def find_repo_root(run_dir: str) -> Path:
    """Find the repo root by looking for schemas directory."""
    run_path = Path(run_dir)
    if (run_path.parent.parent / "schemas").exists():
        return run_path.parent.parent
    if (Path.cwd() / "schemas").exists():
        return Path.cwd()
    if (Path(__file__).parent.parent / "schemas").exists():
        return Path(__file__).parent.parent
    raise ValueError("Cannot find repo root")


def approve_prd(
    run_dir: str,
    artifact: str,
    override_reason: str = None,
    decisions_file: str = None
) -> None:
    """
    Approve a PRD artifact.

    Raises ValueError if approval is not possible.
    """

    # Only 'prd' is supported in this milestone
    if artifact != "prd":
        raise ValueError(f"Artifact '{artifact}' not available until a later milestone")

    run_path = Path(run_dir)

    # Check that prd.md exists
    prd_path = run_path / "prd.md"
    if not prd_path.exists():
        raise ValueError("prd.md not found")

    # Load state
    state = load_state(run_dir)

    # Check verdict
    verdict = state.get("verdicts", {}).get("prd")

    if verdict not in ("PASS", "PASS_WITH_RISK"):
        if override_reason is None or override_reason == "":
            raise ValueError(f"PRD verdict is {verdict}; use --override with a reason to approve")
        # Empty override reason is not allowed
        if not override_reason or not override_reason.strip():
            raise ValueError("--override reason cannot be empty")

    # An approval always needs an audit, even with --override
    if not (state.get("artifact_hashes") or {}).get("prd"):
        raise ValueError("PRD has not been audited; run the audit first")

    # Compute current hash of prd.md
    current_hash = hash_file(str(prd_path))

    # Check if artifact hash exists and differs (means PRD changed since audit)
    artifact_hash = state.get("artifact_hashes", {}).get("prd")
    if artifact_hash is not None and artifact_hash != current_hash:
        raise ValueError("PRD changed since it was audited; run the audit again")

    # Find repo root for schema validation
    repo_root = find_repo_root(run_dir)

    # Create approval object
    approval = {
        "artifact": artifact,
        "sha256": current_hash,
        "verdict": verdict,
        "override_reason": override_reason,
        "approved_at": datetime.utcnow().isoformat() + "Z"
    }

    # Build and validate the updated state first
    try:
        state["approval_hashes"]["prd"] = current_hash
    except (KeyError, TypeError):
        raise ValueError("state.json is malformed: missing approval_hashes")
    state["status"] = "approved"
    state["updated_at"] = datetime.utcnow().isoformat() + "Z"

    schema = load_schema("state", repo_root)
    validator = Draft202012Validator(schema)
    if list(validator.iter_errors(state)):
        raise ValueError("State validation failed: state.json would be invalid after update")

    # Write state, then the approval file last
    state_path = run_path / "state.json"
    try:
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
    except IOError:
        raise ValueError("Cannot write state.json")

    approvals_dir = run_path / "approvals"
    approval_path = approvals_dir / f"{artifact}.approved"
    try:
        approvals_dir.mkdir(parents=True, exist_ok=True)
        with open(approval_path, 'w') as f:
            json.dump(approval, f, indent=2)
    except IOError:
        raise ValueError("Cannot write approval file")

    # Append to decisions file
    if decisions_file is None:
        # Find repo root to locate decisions.md
        decisions_path = repo_root / "decisions.md"
    else:
        decisions_path = Path(decisions_file)

    # Create decisions entry
    run_id = state.get("run_id", "unknown")
    entry_lines = [
        "",
        f"## {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} - PRD Approval",
        "",
        f"**Decided by**: Product Owner",
        f"",
        f"**Run**: {run_id}",
        f"",
        f"**Verdict**: {verdict}",
    ]

    if override_reason:
        if verdict == "PASS_WITH_RISK":
            entry_lines.append(f"**Decision**: Risk accepted with override: {override_reason}")
        else:
            entry_lines.append(f"**Override reason**: {override_reason}")
    elif verdict == "PASS_WITH_RISK":
        entry_lines.append(f"**Decision**: Risk accepted.")

    entry_lines.append("")

    entry_text = "\n".join(entry_lines)

    # Append to decisions file
    try:
        with open(decisions_path, 'a') as f:
            f.write(entry_text)
    except IOError:
        raise ValueError("Cannot write decisions file")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Approve a PRD artifact after audit."
    )
    parser.add_argument("run_dir", help="Run directory")
    parser.add_argument("artifact", help="Artifact name (currently only 'prd')")
    parser.add_argument(
        "--override",
        default=None,
        help="Override reason if verdict is not PASS or PASS_WITH_RISK"
    )
    parser.add_argument(
        "--decisions-file",
        default=None,
        help="Path to decisions file (default: decisions.md in repo root)"
    )

    args = parser.parse_args()

    try:
        approve_prd(
            args.run_dir,
            args.artifact,
            override_reason=args.override,
            decisions_file=args.decisions_file
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except (KeyError, TypeError, AttributeError) as e:
        print(f"state.json is malformed: {e!r}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
