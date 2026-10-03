#!/usr/bin/env python3
"""
Validate evidence cards in a run directory.
Usage: python scripts/validate_evidence.py <run_dir> [--queries-dir connectors/queries]

Checks every runs/<id>/03-evidence/EV-###.json: schema, file name matches id, unique ids,
supports_problem exists in 02-problem.md, query_id exists in the query library, confidence
matches the library status (reviewed = high, otherwise low), and every number in the claim
traces to value or n. Exit 0 if valid, 1 with one error per line.

Also holds the helpers scripts/enrich.py shares: load_library, problem_ids, claim_number_errors.
"""

import re
import sys
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from validate_problem import parse_problem_md

REPO_ROOT = Path(__file__).resolve().parent.parent
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def resolve_path(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() or p.exists() else REPO_ROOT / p


def load_evidence_schema() -> dict:
    path = REPO_ROOT / "schemas" / "evidence.schema.json"
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Cannot load schema {path}: {e}")


def load_library(queries_dir: Path) -> List[Dict[str, Any]]:
    """Return the list of queries in <queries_dir>/index.yaml. Raises ValueError."""
    index_path = queries_dir / "index.yaml"
    try:
        with open(index_path, "r") as f:
            index = yaml.safe_load(f)
    except FileNotFoundError:
        raise ValueError(f"Query library not found: {index_path}")
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"Cannot read query library {index_path}: {e}")
    if not isinstance(index, dict) or not isinstance(index.get("queries"), list):
        raise ValueError(f"Query library {index_path} must have a 'queries' list")
    return index["queries"]


def problem_ids(run_dir: Path) -> List[str]:
    """Problem ids from the front matter of 02-problem.md. Raises ValueError."""
    try:
        front_matter, _ = parse_problem_md(run_dir / "02-problem.md")
    except (FileNotFoundError, IOError) as e:
        raise ValueError(str(e))
    problems = front_matter.get("problems")
    if not isinstance(problems, list):
        raise ValueError("02-problem.md has no problems list")
    return [p.get("id") for p in problems if isinstance(p, dict)]


def confidence_for(status: str) -> str:
    return "high" if status == "reviewed" else "low"


def claim_number_errors(claim: str, value: float, n: int) -> List[str]:
    """Every number in the claim must be the value (or a rounding), value as a percent, or n."""
    errors = []
    allowed = [float(n), float(value), float(round(value)), round(value, 1), round(value, 2)]
    if 0 < value < 1:
        allowed += [float(round(value * 100)), round(value * 100, 1)]
    for token in NUMBER_RE.findall(claim):
        try:
            number = float(token.replace(",", ""))
        except ValueError:
            errors.append(f"claim number '{token}' does not match provider value")
            continue
        if not any(abs(number - a) < 1e-9 for a in allowed):
            errors.append(f"claim number '{token}' does not match provider value")
    return errors


def validate_evidence(run_dir: str, queries_dir: str = "connectors/queries") -> List[str]:
    """Validate the evidence cards of a run. Returns a list of errors."""
    run_path = Path(run_dir)
    if not run_path.is_dir():
        return [f"Run directory not found: {run_dir}"]

    errors: List[str] = []
    try:
        problems = problem_ids(run_path)
    except ValueError as e:
        errors.append(str(e))
        problems = None

    library = None
    try:
        library = {q.get("id"): q for q in load_library(resolve_path(queries_dir))}
    except ValueError as e:
        errors.append(str(e))

    evidence_dir = run_path / "03-evidence"
    if not evidence_dir.is_dir():
        return errors + ["03-evidence directory not found"]
    card_files = sorted(evidence_dir.glob("EV-*.json"))
    if not card_files:
        return errors + ["no evidence cards found in 03-evidence"]

    try:
        validator = Draft202012Validator(load_evidence_schema())
    except ValueError as e:
        return errors + [str(e)]

    seen: Dict[str, str] = {}
    for card_file in card_files:
        name = card_file.name
        try:
            with open(card_file, "r") as f:
                card = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"{name}: invalid JSON: {e}")
            continue

        schema_errors = list(validator.iter_errors(card))
        if schema_errors:
            for err in schema_errors:
                where = ".".join(str(p) for p in err.absolute_path) or "card"
                errors.append(f"{name}: {where}: {err.message}")
            continue

        card_id = card["id"]
        if name != f"{card_id}.json":
            errors.append(f"{name}: file name does not match id {card_id}")
        if card_id in seen:
            errors.append(f"{name}: duplicate id {card_id} (also in {seen[card_id]})")
        else:
            seen[card_id] = name

        if problems is not None and card["supports_problem"] not in problems:
            errors.append(f"{name}: unknown problem {card['supports_problem']} (not in 02-problem.md)")

        if library is not None:
            query = library.get(card["query_id"])
            if query is None:
                errors.append(f"{name}: unknown query id {card['query_id']}")
            else:
                expected = confidence_for(query.get("status"))
                if card["confidence"] != expected:
                    errors.append(
                        f"{name}: confidence {card['confidence']} does not match query status "
                        f"{query.get('status')} (expected {expected})"
                    )

        for msg in claim_number_errors(card["claim"], card["value"], card["n"]):
            errors.append(f"{name}: {msg}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate evidence cards in a run directory.")
    parser.add_argument("run_dir", help="Run directory")
    parser.add_argument("--queries-dir", default="connectors/queries", help="Query library directory")
    args = parser.parse_args()

    errors = validate_evidence(args.run_dir, args.queries_dir)
    for error in errors:
        print(error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
