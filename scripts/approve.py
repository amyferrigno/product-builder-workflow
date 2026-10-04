#!/usr/bin/env python3
"""
Approve a PRD artifact after audit.
Usage: python scripts/approve.py <run_dir> prd|ux|tickets [--override "reason"] [--decisions-file decisions.md]
"""

import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_verdict import verdict_for_run
from check_approval import approval_status
from traceability import write_traceability
from tickets_hash import tickets_hash
from ux_hash import ux_hash
from ux_verdict import ux_verdict_for_run
from validate_tickets import validate_tickets

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
        raise ValueError("Invalid JSON in state.json")


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

    if artifact == "ux":
        approve_ux(run_dir, override_reason=override_reason, decisions_file=decisions_file)
        return

    if artifact == "tickets":
        approve_tickets(run_dir, override_reason=override_reason, decisions_file=decisions_file)
        return

    if artifact != "prd":
        raise ValueError(f"unknown artifact '{artifact}': use prd, ux or tickets")

    run_path = Path(run_dir)

    # Check that prd.md exists
    prd_path = run_path / "prd.md"
    if not prd_path.exists():
        raise ValueError("prd.md not found")

    # Load state
    state = load_state(run_dir)

    # An approval always needs an audit, even with --override
    if not (state.get("artifact_hashes") or {}).get("prd"):
        raise ValueError("PRD has not been audited; run the audit first")

    # Compute current hash of prd.md
    current_hash = hash_file(str(prd_path))

    # PRD changed since it was audited: refused even with an override
    if state["artifact_hashes"]["prd"] != current_hash:
        raise ValueError("PRD changed since it was audited; run the audit again")

    # Recompute the verdict from the audit file; state.json verdicts are not trusted
    repo_root = find_repo_root(run_dir)
    verdict, _reasons = verdict_for_run(run_path, repo_root)

    if verdict not in ("PASS", "PASS_WITH_RISK"):
        if override_reason is None or not override_reason.strip():
            raise ValueError(f"PRD verdict is {verdict}; use --override with a reason to approve")

    # Create approval object
    approval = {
        "artifact": artifact,
        "sha256": current_hash,
        "verdict": verdict,
        "override_reason": override_reason,
        "approved_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    }

    # Build and validate the updated state first
    try:
        state["approval_hashes"]["prd"] = current_hash
    except (KeyError, TypeError):
        raise ValueError("state.json is malformed: missing approval_hashes")
    state["status"] = "approved"
    state["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

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
        f"## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} - PRD Approval",
        "",
        "**Decided by**: Product Owner",
        "",
        f"**Run**: {run_id}",
        "",
        f"**Verdict**: {verdict}",
    ]

    if override_reason:
        if verdict == "PASS_WITH_RISK":
            entry_lines.append(f"**Decision**: Risk accepted with override: {override_reason}")
        else:
            entry_lines.append(f"**Override reason**: {override_reason}")
    elif verdict == "PASS_WITH_RISK":
        entry_lines.append("**Decision**: Risk accepted.")

    entry_lines.append("")

    entry_text = "\n".join(entry_lines)

    # Append to decisions file
    try:
        with open(decisions_path, 'a') as f:
            f.write(entry_text)
    except IOError:
        raise ValueError("Cannot write decisions file")


def approve_ux(
    run_dir: str,
    override_reason: str = None,
    decisions_file: str = None
) -> None:
    """
    Approve the UX artifact (Gate B). prd.md is never modified.

    Raises ValueError if approval is not possible.
    """
    run_path = Path(run_dir)

    prd_ok, prd_message = approval_status(run_dir, "prd")
    if not prd_ok:
        raise ValueError(f"PRD approval is not valid ({prd_message}); approve the PRD first")

    state = load_state(run_dir)

    try:
        current_hash = ux_hash(run_dir)
    except (ValueError, OSError) as e:
        raise ValueError(str(e))

    audited_hash = (state.get("artifact_hashes") or {}).get("ux")
    if not audited_hash:
        raise ValueError("UX has not been audited; run the audit first")

    if audited_hash != current_hash:
        raise ValueError("UX changed since it was audited; run the audit again")

    # Recompute the verdict from the audit file; state.json verdicts are not trusted
    verdict, _reasons = ux_verdict_for_run(run_path)
    if verdict not in ("PASS", "PASS_WITH_RISK"):
        if override_reason is None or not override_reason.strip():
            raise ValueError(f"UX verdict is {verdict}; use --override with a reason to approve")

    repo_root = find_repo_root(run_dir)
    prd_hash = hash_file(str(run_path / "prd.md"))

    approval = {
        "artifact": "ux",
        "sha256": current_hash,
        "prd_sha256": prd_hash,
        "verdict": verdict,
        "override_reason": override_reason,
        "approved_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    }

    try:
        state["approval_hashes"]["ux"] = current_hash
    except (KeyError, TypeError):
        raise ValueError("state.json is malformed: missing approval_hashes")
    state["status"] = "approved"
    state["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

    schema = load_schema("state", repo_root)
    if list(Draft202012Validator(schema).iter_errors(state)):
        raise ValueError("State validation failed: state.json would be invalid after update")

    # Traceability goes to its own file; prd.md is left alone
    try:
        write_traceability(run_dir)
    except (OSError, UnicodeDecodeError):
        raise ValueError("Cannot write traceability.md")

    # Write state, then the approval file last
    try:
        with open(run_path / "state.json", 'w') as f:
            json.dump(state, f, indent=2)
    except IOError:
        raise ValueError("Cannot write state.json")

    approvals_dir = run_path / "approvals"
    try:
        approvals_dir.mkdir(parents=True, exist_ok=True)
        with open(approvals_dir / "ux.approved", 'w') as f:
            json.dump(approval, f, indent=2)
    except IOError:
        raise ValueError("Cannot write approval file")

    decisions_path = repo_root / "decisions.md" if decisions_file is None else Path(decisions_file)
    entry_lines = [
        "",
        f"## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} - UX Approval",
        "",
        "**Decided by**: Product Owner",
        "",
        f"**Run**: {state.get('run_id', 'unknown')}",
        "",
        f"**Verdict**: {verdict}",
    ]
    if override_reason:
        if verdict == "PASS_WITH_RISK":
            entry_lines.append(f"**Decision**: Risk accepted with override: {override_reason}")
        else:
            entry_lines.append(f"**Override reason**: {override_reason}")
    elif verdict == "PASS_WITH_RISK":
        entry_lines.append("**Decision**: Risk accepted.")
    entry_lines.append("")

    try:
        with open(decisions_path, 'a') as f:
            f.write("\n".join(entry_lines))
    except IOError:
        raise ValueError("Cannot write decisions file")


def approve_tickets(
    run_dir: str,
    override_reason: str = None,
    decisions_file: str = None
) -> None:
    """
    Approve the ticket manifest (Gate C). prd.md and ux/ are never modified.
    There is no override: the Definition of Ready is checked here by script.

    Raises ValueError if approval is not possible.
    """
    if override_reason is not None:
        raise ValueError("--override is not allowed for tickets; fix the manifest so it passes the Definition of Ready")

    run_path = Path(run_dir)

    ux_ok, ux_message = approval_status(run_dir, "ux")
    if not ux_ok:
        raise ValueError(f"UX approval is not valid ({ux_message}); approve the UX first")

    repo_root = find_repo_root(run_dir)
    try:
        errors = validate_tickets(run_dir, repo_root)
    except (ValueError, OSError) as e:
        raise ValueError(f"Cannot validate tickets: {e}")
    if errors:
        shown = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(f"Tickets fail the Definition of Ready ({len(errors)} errors):\n{shown}")

    state = load_state(run_dir)

    try:
        current_hash = tickets_hash(run_dir)
        manifest = json.loads((run_path / "tickets.manifest.json").read_text(encoding="utf-8"))
        ux_current = ux_hash(run_dir)
        prd_hash = hash_file(str(run_path / "prd.md"))
    except (ValueError, OSError) as e:
        raise ValueError(str(e))
    ticket_count = sum(1 + len(e.get("children", [])) for e in manifest.get("epics", []))

    approval = {
        "artifact": "tickets",
        "sha256": current_hash,
        "prd_sha256": prd_hash,
        "ux_sha256": ux_current,
        "ticket_count": ticket_count,
        "approved_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    }

    try:
        state["approval_hashes"]["tickets"] = current_hash
    except (KeyError, TypeError):
        raise ValueError("state.json is malformed: missing approval_hashes")
    state["stage"] = "stage3"
    state["status"] = "approved"
    state["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

    schema = load_schema("state", repo_root)
    if list(Draft202012Validator(schema).iter_errors(state)):
        raise ValueError("State validation failed: state.json would be invalid after update")

    # Traceability goes to its own file; prd.md and ux/ are left alone
    try:
        write_traceability(run_dir)
    except (OSError, UnicodeDecodeError):
        raise ValueError("Cannot write traceability.md")

    # Write state, then the approval file last
    try:
        with open(run_path / "state.json", 'w') as f:
            json.dump(state, f, indent=2)
    except IOError:
        raise ValueError("Cannot write state.json")

    approvals_dir = run_path / "approvals"
    try:
        approvals_dir.mkdir(parents=True, exist_ok=True)
        with open(approvals_dir / "tickets.approved", 'w') as f:
            json.dump(approval, f, indent=2)
    except IOError:
        raise ValueError("Cannot write approval file")

    decisions_path = repo_root / "decisions.md" if decisions_file is None else Path(decisions_file)
    entry_lines = [
        "",
        f"## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} - Tickets Approval",
        "",
        "**Decided by**: Product Owner",
        "",
        f"**Run**: {state.get('run_id', 'unknown')}",
        "",
        f"**Tickets**: {ticket_count}",
        "",
    ]
    try:
        with open(decisions_path, 'a') as f:
            f.write("\n".join(entry_lines))
    except IOError:
        raise ValueError("Cannot write decisions file")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Approve a PRD artifact after audit."
    )
    parser.add_argument("run_dir", help="Run directory")
    parser.add_argument("artifact", help="Artifact name ('prd', 'ux' or 'tickets')")
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
