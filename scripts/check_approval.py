#!/usr/bin/env python3
"""
Check if an artifact is approved and hash matches.
Usage: python scripts/check_approval.py <run_dir> prd|ux|tickets
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


def approval_status(run_dir: str, artifact: str) -> tuple:
    """
    Return (ok, message) for an artifact approval.

    Messages start with 'approved', 'missing', 'stale' or 'invalid'.
    'ux' is approved only when its approval matches the current UX hash, the
    PRD approval is itself valid and its prd_sha256 matches the current prd.md.
    """

    if artifact == "ux":
        return _ux_status(run_dir)
    if artifact == "tickets":
        return _tickets_status(run_dir)
    if artifact != "prd":
        return False, f"invalid: unknown artifact {artifact}"

    run_path = Path(run_dir)
    artifact_path = run_path / f"{artifact}.md"
    approval_path = run_path / "approvals" / f"{artifact}.approved"

    # Check if artifact file exists
    if not artifact_path.exists():
        return False, f"missing: {artifact}.md not found"

    # Check if approval file exists
    if not approval_path.exists():
        return False, "missing: approval file not found"

    # Try to load and parse approval file
    try:
        with open(approval_path, 'r') as f:
            approval = json.load(f)
    except (json.JSONDecodeError, IOError, ValueError):
        return False, "invalid: cannot parse approval file"

    # Check if approval has sha256
    if not isinstance(approval, dict) or "sha256" not in approval:
        return False, "invalid: sha256 missing from approval file"

    # Compute current hash
    try:
        current_hash = hash_file(str(artifact_path))
    except ValueError as e:
        return False, f"invalid: {str(e)}"

    # Compare hashes
    if approval.get("sha256") != current_hash:
        return False, f"stale: {artifact}.md has changed since approval"

    return True, "approved"


def _ux_hash(run_dir: str) -> str:
    """UX hash from scripts/ux_hash.py, imported by path so this file works from any cwd."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ux_hash import ux_hash
    return ux_hash(run_dir)


def _ux_status(run_dir: str) -> tuple:
    run_path = Path(run_dir)
    approval_path = run_path / "approvals" / "ux.approved"

    if not (run_path / "ux").is_dir():
        return False, "missing: ux folder not found"
    if not approval_path.exists():
        return False, "missing: approval file not found"

    try:
        with open(approval_path, 'r') as f:
            approval = json.load(f)
    except (json.JSONDecodeError, IOError, ValueError):
        return False, "invalid: cannot parse approval file"
    if not isinstance(approval, dict) or "sha256" not in approval:
        return False, "invalid: sha256 missing from approval file"
    if "prd_sha256" not in approval:
        return False, "invalid: prd_sha256 missing from approval file"

    try:
        current_ux = _ux_hash(run_dir)
    except (ValueError, OSError) as e:
        return False, f"invalid: {str(e)}"
    if approval.get("sha256") != current_ux:
        return False, "stale: ux has changed since approval"

    prd_ok, prd_message = approval_status(run_dir, "prd")
    if not prd_ok:
        return False, f"{prd_message.split(':')[0]}: PRD approval is not valid ({prd_message})"
    try:
        current_prd = hash_file(str(run_path / "prd.md"))
    except ValueError as e:
        return False, f"invalid: {str(e)}"
    if approval.get("prd_sha256") != current_prd:
        return False, "stale: prd.md has changed since the UX was approved"

    return True, "approved"


def _tickets_hash(run_dir: str) -> str:
    """Tickets hash from scripts/tickets_hash.py, imported by path so this file works from any cwd."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tickets_hash import tickets_hash
    return tickets_hash(run_dir)


def _tickets_status(run_dir: str) -> tuple:
    run_path = Path(run_dir)
    approval_path = run_path / "approvals" / "tickets.approved"

    if not (run_path / "tickets.manifest.json").exists():
        return False, "missing: tickets.manifest.json not found"
    if not approval_path.exists():
        return False, "missing: approval file not found"

    try:
        with open(approval_path, 'r') as f:
            approval = json.load(f)
    except (json.JSONDecodeError, IOError, ValueError):
        return False, "invalid: cannot parse approval file"
    if not isinstance(approval, dict) or "sha256" not in approval:
        return False, "invalid: sha256 missing from approval file"
    for key in ("prd_sha256", "ux_sha256"):
        if key not in approval:
            return False, f"invalid: {key} missing from approval file"

    try:
        current_tickets = _tickets_hash(run_dir)
    except (ValueError, OSError) as e:
        return False, f"invalid: {str(e)}"
    if approval.get("sha256") != current_tickets:
        return False, "stale: tickets have changed since approval"

    ux_ok, ux_message = _ux_status(run_dir)
    if not ux_ok:
        return False, f"{ux_message.split(':')[0]}: UX approval is not valid ({ux_message})"
    try:
        current_ux = _ux_hash(run_dir)
        current_prd = hash_file(str(run_path / "prd.md"))
    except (ValueError, OSError) as e:
        return False, f"invalid: {str(e)}"
    if approval.get("ux_sha256") != current_ux:
        return False, "stale: ux has changed since the tickets were approved"
    if approval.get("prd_sha256") != current_prd:
        return False, "stale: prd.md has changed since the tickets were approved"

    return True, "approved"


def check_approval(run_dir: str, artifact: str) -> None:
    """
    Check if an artifact approval is valid.

    Exits with code 0 and prints 'approved' if approval exists and hash matches.
    Exits with code 1 and prints 'missing', 'stale', or 'invalid' otherwise.
    """
    ok, message = approval_status(run_dir, artifact)
    print(message)
    sys.exit(0 if ok else 1)


def main():
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: python scripts/check_approval.py <run_dir> prd|ux|tickets", file=sys.stderr)
        sys.exit(1)

    run_dir = sys.argv[1]
    artifact = sys.argv[2]

    try:
        check_approval(run_dir, artifact)
    except Exception:
        print("invalid: unexpected error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
