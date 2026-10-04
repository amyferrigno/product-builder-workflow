#!/usr/bin/env python3
"""
Hash the ticket manifest of a run.
Usage: python scripts/tickets_hash.py <run_dir>

The hash is the sha256 of runs/<id>/tickets.manifest.json re-serialised as JSON
with sorted keys and compact separators, after every jira_key (epic and child)
is set to null. Writing Jira keys back therefore does not change the hash.
Standard library only (a hook imports this file).
"""

import hashlib
import json
import sys
from pathlib import Path

MANIFEST_NAME = "tickets.manifest.json"


def tickets_hash(run_dir) -> str:
    """sha256 of the manifest with all jira_key values nulled. ValueError when missing or not JSON."""
    path = Path(run_dir) / MANIFEST_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"manifest not found: {path}")
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"cannot read manifest {path}: {e}")
    except json.JSONDecodeError as e:
        raise ValueError(f"manifest is not valid JSON ({path}): {e}")
    if isinstance(data, dict) and isinstance(data.get("epics"), list):
        for epic in data["epics"]:
            if not isinstance(epic, dict):
                continue
            epic["jira_key"] = None
            children = epic.get("children")
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        child["jira_key"] = None
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/tickets_hash.py <run_dir>")
        sys.exit(1)
    try:
        print(tickets_hash(sys.argv[1]))
    except ValueError as e:
        print(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
