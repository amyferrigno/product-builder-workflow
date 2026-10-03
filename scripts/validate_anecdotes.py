#!/usr/bin/env python3
"""
Validate the curated anecdotes of a run against the candidates.

Usage:
  python scripts/validate_anecdotes.py <run_dir> [--config pm.config.yaml]

Reads 04-anecdotes.json (curated) and 04-anecdotes.candidates.json. Prints one error per
line and exits 1 on any error, 0 when valid.
"""

import re
import sys
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from providers import resolve_path, REPO_ROOT
from validate_evidence import problem_ids
from pii import scan, load_pii_config

CURATED_FILE = "04-anecdotes.json"
CANDIDATES_FILE = "04-anecdotes.candidates.json"
MIN_RECORDS = 3
MAX_RECORDS = 5
MAX_QUOTE_WORDS = 40
ELLIPSIS = "…"
TEXT_FIELDS = ("source", "source_ref", "date", "segment", "persona", "pain", "quote")


def load_array(path: Path) -> Any:
    """Return (list, error). Error is a one-line message or None."""
    if not path.is_file():
        return None, f"{path.name} not found: {path}"
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return None, f"{path.name} is not valid JSON: {e}"
    if not isinstance(data, list):
        return None, f"{path.name} must be a JSON array"
    return data, None


def load_terms(config: str):
    path = resolve_path(config)
    if not path.exists():
        if config == "pm.config.yaml":
            return {"people": [], "companies": []}, False
        raise ValueError(f"Config not found: {config}")
    try:
        return load_pii_config(path)
    except Exception as e:
        raise ValueError(f"Cannot read config {config}: {e}")


def record_label(rec: Any, index: int) -> str:
    if isinstance(rec, dict) and isinstance(rec.get("id"), str):
        return rec["id"]
    return f"record #{index + 1}"


def validate_anecdotes(run_dir: str, config: str = "pm.config.yaml") -> List[str]:
    run_path = Path(run_dir)
    if not run_path.is_dir():
        return [f"Run directory not found: {run_dir}"]

    curated, err1 = load_array(run_path / CURATED_FILE)
    candidates, err2 = load_array(run_path / CANDIDATES_FILE)
    errors = [e for e in (err1, err2) if e]
    if errors:
        return errors

    try:
        pii_terms, allow_companies = load_terms(config)
    except ValueError as e:
        return [str(e)]
    try:
        with open(REPO_ROOT / "schemas" / "anecdote.schema.json", "r") as f:
            schema_validator = Draft202012Validator(json.load(f))
    except (OSError, json.JSONDecodeError) as e:
        return [f"Cannot load anecdote schema: {e}"]
    try:
        problems = problem_ids(run_path)
    except ValueError as e:
        return [str(e)]

    # Schema, per record.
    schema_ok = True
    for i, rec in enumerate(curated):
        label = record_label(rec, i)
        for e in schema_validator.iter_errors(rec):
            field = ".".join(str(p) for p in e.path) or "record"
            errors.append(f"{label}: field '{field}': {e.message}")
            schema_ok = False
    for i, rec in enumerate(candidates):
        if not isinstance(rec, dict):
            errors.append(f"{CANDIDATES_FILE}: {record_label(rec, i)} is not an object")
            schema_ok = False
    if not schema_ok:
        return errors

    # Count.
    needed = min(MIN_RECORDS, len(candidates))
    if len(curated) > MAX_RECORDS:
        errors.append(f"too many anecdotes: {len(curated)} (maximum {MAX_RECORDS})")
    if len(curated) < needed:
        errors.append(
            f"too few anecdotes: {len(curated)} (need at least {needed}, "
            f"{len(candidates)} candidates exist)"
        )

    # Duplicate ids.
    seen = set()
    for rec in curated:
        if rec["id"] in seen:
            errors.append(f"duplicate id {rec['id']}")
        seen.add(rec["id"])

    by_id: Dict[str, Dict[str, Any]] = {c.get("id"): c for c in candidates}
    evidence_dir = run_path / "03-evidence"

    for rec in curated:
        rid = rec["id"]
        candidate: Optional[Dict[str, Any]] = by_id.get(rid)
        if candidate is None:
            errors.append(f"{rid}: not found in {CANDIDATES_FILE}")
        else:
            for key in sorted(set(rec) | set(candidate)):
                if key == "frequency_hint":
                    continue
                if rec.get(key) != candidate.get(key):
                    errors.append(f"{rid}: field '{key}' differs from the candidate")
        words = len(rec["quote"].rstrip(ELLIPSIS).split())
        if words > MAX_QUOTE_WORDS:
            errors.append(f"{rid}: quote has {words} words (maximum {MAX_QUOTE_WORDS})")
        for field in TEXT_FIELDS:
            for f in scan(rec[field], pii_terms, allow_companies):
                errors.append(f"{rid}: field '{field}': PII found ({f['type']}): {f['match']}")
        if rec["consent_ok"] is not True:
            errors.append(f"{rid}: consent_ok must be true")
        if rec["linked_problem"] not in problems:
            errors.append(f"{rid}: linked_problem '{rec['linked_problem']}' not in 02-problem.md")
        hint = rec["frequency_hint"]
        if hint is not None and not (
            re.fullmatch(r"EV-\d{3}", hint) and (evidence_dir / f"{hint}.json").is_file()
        ):
            errors.append(f"{rid}: frequency_hint '{hint}' is not an existing evidence card")

    candidates_have_positive = any(
        isinstance(c.get("sentiment"), int) and c["sentiment"] > 0 for c in candidates
    )
    if candidates_have_positive and not any(r["sentiment"] > 0 for r in curated):
        errors.append("counter-anecdote missing: select a record with positive sentiment")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate curated anecdotes in a run directory.")
    parser.add_argument("run_dir", help="Run directory")
    parser.add_argument("--config", default="pm.config.yaml", help="Config with anecdotes.pii_terms")
    args = parser.parse_args()
    errors = validate_anecdotes(args.run_dir, args.config)
    for error in errors:
        print(error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
