#!/usr/bin/env python3
"""
Evaluate every fixture: build a temp run from its notes and goldens, run every validator whose input
exists, compute the decision and the PRD / UX verdicts, and compare with expected.yaml.
Usage: python scripts/eval_fixtures.py [--json] [--fixtures-dir fixtures]
Prints one row per fixture and "EVAL: <n> fixtures, <m> failed". Exit 1 when any fixture fails.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_verdict
import prd_decision
import ux_verdict
import validate_anecdotes
import validate_evidence
import validate_extraction
import validate_memo
import validate_prd
import validate_problem
import validate_tickets
import validate_ux

RUN_DATE = "2026-01-15"
MAX_ERROR_LINES = 10
MOCK_CONFIG_NAME = "pm.config.mock.yaml"


def discover(fixtures_dir: Path) -> List[Path]:
    """Fixture folders that have both notes.md and expected.yaml, sorted by name."""
    if not fixtures_dir.is_dir():
        return []
    return sorted(
        p for p in fixtures_dir.iterdir()
        if p.is_dir() and (p / "notes.md").is_file() and (p / "expected.yaml").is_file()
    )


def mock_config(fixtures_dir: Path) -> str:
    """Mock config next to the fixtures; falls back to the repo's own fixtures folder."""
    candidate = fixtures_dir / MOCK_CONFIG_NAME
    if candidate.is_file():
        return str(candidate)
    return str(REPO_ROOT / "fixtures" / MOCK_CONFIG_NAME)


def build_run(fixture: Path, runs_dir: Path) -> Path:
    """Intake the notes into runs_dir and copy the golden files and folders into the run."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "intake.py"), str(fixture / "notes.md"),
         "--date", RUN_DATE, "--slug", fixture.name, "--runs-dir", str(runs_dir)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(f"intake failed: {result.stderr.strip() or result.stdout.strip()}")
    run_dir = Path(json.loads(result.stdout)["run_dir"])
    golden = fixture / "golden"
    if golden.is_dir():
        for item in sorted(golden.iterdir()):
            target = run_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy(item, target)
    return run_dir


def _checks(run_dir: Path, fixtures_dir: Path) -> List[Any]:
    """(label, callable returning a list of error strings) for every validator whose input exists."""
    config = mock_config(fixtures_dir)

    def pair(fn):
        return lambda: fn(str(run_dir))[1]

    checks: List[Any] = []
    if (run_dir / "01-extraction.json").exists():
        checks.append(("extraction", pair(validate_extraction.validate_extraction)))
    if (run_dir / "02-problem.md").exists():
        checks.append(("problem", pair(validate_problem.validate_problem)))
    if (run_dir / "prd.md").exists():
        checks.append(("prd", pair(validate_prd.validate_prd)))
    if (run_dir / "no-prd-memo.md").exists():
        checks.append(("memo", lambda: validate_memo.validate_memo(str(run_dir))))
    if (run_dir / "03-evidence").is_dir():
        checks.append(("evidence", lambda: validate_evidence.validate_evidence(str(run_dir))))
    if (run_dir / "04-anecdotes.json").exists() or (run_dir / "04-anecdotes.candidates.json").exists():
        checks.append(("anecdotes", lambda: validate_anecdotes.validate_anecdotes(str(run_dir), config)))
    if (run_dir / "ux").is_dir():
        checks.append(("ux", lambda: validate_ux.validate_ux(run_dir, REPO_ROOT)))
    if (run_dir / "tickets.manifest.json").exists():
        checks.append(("tickets", lambda: validate_tickets.validate_tickets(run_dir, REPO_ROOT)))
    return checks


def _count_tickets(run_dir: Path) -> Optional[int]:
    path = run_dir / "tickets.manifest.json"
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return sum(len(e.get("children", [])) for e in manifest.get("epics", []))
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def evaluate_fixture(fixture: Path, fixtures_dir: Path) -> Dict[str, Any]:
    """Evaluate one fixture. Never raises: a crash becomes an error on that fixture."""
    row: Dict[str, Any] = {
        "name": fixture.name, "decision": None, "validators_passed": 0, "validators_total": 0,
        "prd_verdict": None, "ux_verdict": None, "tickets": None, "ok": False, "errors": [],
    }
    errors: List[str] = row["errors"]
    try:
        expected = yaml.safe_load((fixture / "expected.yaml").read_text(encoding="utf-8"))
        if not isinstance(expected, dict):
            raise ValueError("expected.yaml is not a mapping")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = build_run(fixture, Path(tmp))
            for label, check in _checks(run_dir, fixtures_dir):
                row["validators_total"] += 1
                try:
                    found = check()
                except Exception as e:  # a crash in one validator is that validator's failure
                    found = [f"crashed: {type(e).__name__}: {e}"]
                if found:
                    errors.extend(f"{label}: {line}" for line in found)
                else:
                    row["validators_passed"] += 1

            try:
                row["decision"] = prd_decision.decide(run_dir)[0]
            except Exception as e:
                errors.append(f"decision: {e}")
            if (run_dir / "prd.audit.json").exists():
                try:
                    row["prd_verdict"] = audit_verdict.verdict_for_run(run_dir, REPO_ROOT)[0]
                except Exception as e:
                    errors.append(f"prd verdict: {e}")
            if (run_dir / "ux.audit.json").exists():
                try:
                    row["ux_verdict"] = ux_verdict.ux_verdict_for_run(run_dir, REPO_ROOT)[0]
                except Exception as e:
                    errors.append(f"ux verdict: {e}")
            row["tickets"] = _count_tickets(run_dir)

        _compare(expected, row, errors)
    except Exception as e:
        errors.append(f"crashed: {type(e).__name__}: {e}")
    row["ok"] = not errors
    return row


def _compare(expected: Dict[str, Any], row: Dict[str, Any], errors: List[str]) -> None:
    if "decision" not in expected:
        errors.append("expected.yaml has no decision")
    elif row["decision"] != expected["decision"]:
        errors.append(f"decision: expected {expected['decision']}, got {row['decision']}")
    for key, field in (("prd", "prd_verdict"), ("ux", "ux_verdict")):
        section = expected.get(key)
        if isinstance(section, dict) and "verdict" in section and row[field] != section["verdict"]:
            errors.append(f"{key} verdict: expected {section['verdict']}, got {row[field]}")


def evaluate(fixtures_dir) -> List[Dict[str, Any]]:
    fixtures_dir = Path(fixtures_dir)
    return [evaluate_fixture(f, fixtures_dir) for f in discover(fixtures_dir)]


def format_table(rows: List[Dict[str, Any]]) -> str:
    header = ["fixture", "decision", "validators", "prd", "ux", "tickets", "result"]
    body = []
    for r in rows:
        body.append([
            r["name"], r["decision"] or "-", f"{r['validators_passed']}/{r['validators_total']}",
            r["prd_verdict"] or "-", r["ux_verdict"] or "-",
            "-" if r["tickets"] is None else str(r["tickets"]), "OK" if r["ok"] else "FAIL",
        ])
    widths = [max(len(line[i]) for line in [header] + body) for i in range(len(header))]
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(header)).rstrip()]
    for r, line in zip(rows, body):
        lines.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(line)).rstrip())
        if not r["ok"]:
            shown = [e.replace("\n", " ") for e in r["errors"]]
            for err in shown[:MAX_ERROR_LINES]:
                lines.append(f"    - {err}")
            if len(shown) > MAX_ERROR_LINES:
                lines.append(f"    ... {len(shown) - MAX_ERROR_LINES} more")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate every fixture against its expected.yaml.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    parser.add_argument("--fixtures-dir", default=str(REPO_ROOT / "fixtures"))
    args = parser.parse_args(argv)

    rows = evaluate(args.fixtures_dir)
    failed = sum(1 for r in rows if not r["ok"])
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(format_table(rows))
        print(f"EVAL: {len(rows)} fixtures, {failed} failed")
    return 1 if failed or not rows else 0


if __name__ == "__main__":
    sys.exit(main())
