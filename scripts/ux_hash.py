#!/usr/bin/env python3
"""
Hash the UX folder of a run.
Usage: python scripts/ux_hash.py <run_dir>

The hash covers flows.md, spec.md, index.html and every screens/*.html
(sorted by relative path), so any byte change in those files changes it.
Standard library only (a hook imports this file).
"""

import hashlib
import sys
from pathlib import Path
from typing import List

UX_FILES = ("flows.md", "spec.md", "index.html")


def ux_files(ux_dir: Path) -> List[Path]:
    """The files that make up the UX artifact, sorted by relative posix path."""
    files = [ux_dir / name for name in UX_FILES if (ux_dir / name).is_file()]
    screens = ux_dir / "screens"
    if screens.is_dir():
        files.extend(p for p in screens.glob("*.html") if p.is_file())
    return sorted(files, key=lambda p: p.relative_to(ux_dir).as_posix())


def ux_hash(run_dir) -> str:
    """sha256 over '<relative path>\\t<file sha256>\\n' lines. ValueError when ux/ is missing."""
    ux_dir = Path(run_dir) / "ux"
    if not ux_dir.is_dir():
        raise ValueError(f"ux folder not found: {ux_dir}")
    digest = hashlib.sha256()
    for path in ux_files(ux_dir):
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        line = f"{path.relative_to(ux_dir).as_posix()}\t{file_hash}\n"
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/ux_hash.py <run_dir>")
        sys.exit(1)
    try:
        print(ux_hash(sys.argv[1]))
    except (ValueError, OSError) as e:
        print(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
