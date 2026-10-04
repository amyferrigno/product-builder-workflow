#!/usr/bin/env python3
"""
Active run pointer: runs/.active holds the id of the run the session is working on.
Usage: python scripts/active_run.py set <run_dir> | get
Standard library only.
"""

import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
POINTER_NAME = ".active"


def is_repo_run(run_dir) -> bool:
    """True when run_dir sits directly under this repo's runs/ folder."""
    try:
        return Path(run_dir).resolve().parent == (REPO_ROOT / "runs").resolve()
    except OSError:
        return False


def set_active(run_dir) -> None:
    """Write the run id to runs/.active. Refuses a run dir not directly under the repo's runs/."""
    run_path = Path(run_dir)
    if not is_repo_run(run_path):
        raise ValueError(f"Run dir must be directly under {REPO_ROOT / 'runs'}: {run_dir}")
    pointer = REPO_ROOT / "runs" / POINTER_NAME
    pointer.write_text(run_path.resolve().name + "\n", encoding="utf-8")


def get_active(repo_root) -> Optional[Path]:
    """Return the active run dir, or None when the pointer or the run folder is missing."""
    runs = Path(repo_root) / "runs"
    try:
        run_id = (runs / POINTER_NAME).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not run_id or "/" in run_id or "\\" in run_id or run_id in (".", ".."):
        return None
    run_dir = runs / run_id
    return run_dir if run_dir.is_dir() else None


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "set":
        try:
            set_active(args[1])
        except (ValueError, OSError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return 0
    if len(args) == 1 and args[0] == "get":
        active = get_active(REPO_ROOT)
        if active is None:
            return 1
        print(active)
        return 0
    print("Usage: active_run.py set <run_dir> | get", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
