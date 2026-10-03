#!/usr/bin/env python3
"""
Check if an artifact is approved and hash matches.
Usage: python scripts/check_approval.py <run_dir> prd
Exit 0 and print 'approved' if approval exists and hash is current, else exit 1.
"""

import sys
import json
import hashlib
from pathlib import Path


def hash_file(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, IOError):
        raise ValueError(f"Cannot read {file_path}")


def check_approval(run_dir: str, artifact: str) -> None:
    """
    Check if an artifact approval is valid.

    Exits with code 0 and prints 'approved' if approval exists and hash matches.
    Exits with code 1 and prints 'missing', 'stale', or 'invalid' otherwise.
    """

    run_path = Path(run_dir)
    artifact_path = run_path / f"{artifact}.md"
    approval_path = run_path / "approvals" / f"{artifact}.approved"

    # Check if artifact file exists
    if not artifact_path.exists():
        print(f"missing: {artifact}.md not found")
        sys.exit(1)

    # Check if approval file exists
    if not approval_path.exists():
        print(f"missing: approval file not found")
        sys.exit(1)

    # Try to load and parse approval file
    try:
        with open(approval_path, 'r') as f:
            approval = json.load(f)
    except (json.JSONDecodeError, IOError, ValueError):
        print(f"invalid: cannot parse approval file")
        sys.exit(1)

    # Check if approval has sha256
    if "sha256" not in approval:
        print(f"invalid: sha256 missing from approval file")
        sys.exit(1)

    # Compute current hash
    try:
        current_hash = hash_file(str(artifact_path))
    except ValueError as e:
        print(f"invalid: {str(e)}")
        sys.exit(1)

    # Compare hashes
    approval_hash = approval.get("sha256")
    if approval_hash != current_hash:
        print(f"stale: {artifact}.md has changed since approval")
        sys.exit(1)

    # Approval is valid
    print("approved")
    sys.exit(0)


def main():
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: python scripts/check_approval.py <run_dir> prd", file=sys.stderr)
        sys.exit(1)

    run_dir = sys.argv[1]
    artifact = sys.argv[2]

    try:
        check_approval(run_dir, artifact)
    except Exception:
        print(f"invalid: unexpected error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
