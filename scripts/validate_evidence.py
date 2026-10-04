#!/usr/bin/env python3
"""
Validate evidence cards in a run directory.
Usage: python scripts/validate_evidence.py <run_dir> [--queries-dir connectors/queries]

Checks every runs/<id>/03-evidence/EV-###.json: schema, file name matches id, unique ids,
supports_problem exists in 02-problem.md, query_id exists in the query library, confidence
matches the library status (reviewed = high, otherwise low), and every number in the claim
is exactly the provider value, the value as a percent, or n. For library queries it also checks
that query_hash is the sha256 of the library .sql file text and that source is the query's
provider. Exit 0 if valid, 1 with one error per line.

Claim number rules (the same ones scripts/enrich.py uses to render a claim template):
  {value}      integers as-is, other numbers rounded to at most 2 decimals, trailing zeros trimmed
  {value_pct}  value x 100 rounded to at most 1 decimal, trailing .0 trimmed; only when
               0 <= value <= 1, and only written directly before % or the word "percent"
  {n}          the n integer
No rounding slack and no magnitude words (k, m, mn, mm, bn, x, hundred, thousand, million, billion, times)
after a number.

Also holds the helpers scripts/enrich.py shares: load_library, problem_ids, claim_number_errors,
render_claim, query_hash_of, param_names.
"""

import re
import sys
import json
import hashlib
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
NUMBER_RE = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
MAGNITUDE_WORDS = r"(?:k|m|mn|mm|bn|x|hundred|thousand|million|billion|times)"
MAGNITUDE_AFTER_RE = re.compile(r"\s*" + MAGNITUDE_WORDS + r"\b", re.IGNORECASE)
PERCENT_AFTER_RE = re.compile(r"\s*%|\s+percent\b", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")


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


def _trim(text: str) -> str:
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_value(value: float) -> str:
    """Integers as-is; other numbers rounded to at most 2 decimals, trailing zeros trimmed."""
    if float(value).is_integer():
        return str(int(value))
    return _trim(f"{round(value, 2):.2f}")


def format_value_pct(value: float) -> str:
    """value x 100 rounded to at most 1 decimal, trailing .0 trimmed. Raises ValueError outside 0..1."""
    if not 0 <= value <= 1:
        raise ValueError("{value_pct} needs a provider value between 0 and 1")
    return _trim(f"{round(value * 100, 1):.1f}")


def param_names(query: Dict[str, Any]) -> List[str]:
    """Parameter names of a library query (entries are objects with a name, or plain strings)."""
    names = []
    for p in query.get("params") or []:
        names.append(p.get("name") if isinstance(p, dict) else p)
    return [n for n in names if isinstance(n, str)]


def query_hash_of(queries_dir: Path, query: Dict[str, Any]) -> str:
    """sha256 of the library .sql file text, read the way the provider reads it."""
    with open(queries_dir / query["file"], "r") as f:
        return hashlib.sha256(f.read().encode("utf-8")).hexdigest()


def render_claim(template: str, value: float, n: int) -> str:
    """Fill a claim template. Raises ValueError with a one-line message when it is not allowed."""
    names = PLACEHOLDER_RE.findall(template)
    for name in names:
        if name not in ("value", "value_pct", "n"):
            raise ValueError(f"unknown placeholder '{{{name}}}' in claim template")
    if "{value}" not in template and "{value_pct}" not in template:
        raise ValueError("claim template must contain {value} or {value_pct}")
    outside = PLACEHOLDER_RE.sub("", template)
    if "{" in outside or "}" in outside:
        raise ValueError("claim template has unbalanced braces")
    if re.search(r"\d", outside):
        raise ValueError("claim template must not contain literal numbers; use {value}, {value_pct} or {n}")
    for m in PLACEHOLDER_RE.finditer(template):
        rest = template[m.end():]
        if MAGNITUDE_AFTER_RE.match(rest):
            raise ValueError(
                "claim template must not put a magnitude word "
                "(k, m, mn, mm, bn, x, hundred, thousand, million, billion, times) after a number"
            )
        has_percent = PERCENT_AFTER_RE.match(rest) is not None
        if m.group(1) == "value_pct":
            if not has_percent:
                raise ValueError("{value_pct} must be followed directly by % or the word percent")
        elif re.match(r"\s*%", rest):
            raise ValueError("% may follow only {value_pct}")
    values = {"value": format_value(value), "n": str(n)}
    if "{value_pct}" in template:
        values["value_pct"] = format_value_pct(value)
    return PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def claim_number_errors(claim: str, value: float, n: int) -> List[str]:
    """Every number in the claim must be exactly {value}, {value_pct} (before % or percent) or {n}."""
    errors = []
    plain = {format_value(value), str(n)}
    pct = format_value_pct(value) if 0 <= value <= 1 else None
    for m in NUMBER_RE.finditer(claim):
        token = m.group(0)
        rest = claim[m.end():]
        if MAGNITUDE_AFTER_RE.match(rest):
            errors.append(f"claim number '{token}' must not be followed by a magnitude word")
        elif PERCENT_AFTER_RE.match(rest):
            if pct is None or token != pct:
                errors.append(f"claim number '{token}' does not match provider value")
        elif token not in plain:
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
                if card["source"] != query.get("provider"):
                    errors.append(f"{name}: source {card['source']} does not match the query provider")
                try:
                    expected_hash = query_hash_of(resolve_path(queries_dir), query)
                except (OSError, KeyError, TypeError) as e:
                    errors.append(f"{name}: cannot read the library query file: {e}")
                else:
                    if card["query_hash"] != expected_hash:
                        errors.append(f"{name}: query_hash does not match the library query")

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
