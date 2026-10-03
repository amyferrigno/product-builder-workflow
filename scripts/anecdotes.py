#!/usr/bin/env python3
"""
Pull customer anecdotes from a provider and write de-identified candidates.

Usage:
  python scripts/anecdotes.py pull <run_dir> --provider P --problem PB-1 --keywords "a,b"
      [--segment S] [--limit N] [--registry R] [--config C] [--cache-dir D]

Rows without consent are dropped, PII is scrubbed (pii.scrub with the config's terms),
quotes are cut to 40 words on a word boundary (an ellipsis is appended when cut), and ids
AN-001... are assigned. Every text field is scanned again afterwards; any finding means exit 1
and nothing is written (fail closed). Output: <run_dir>/04-anecdotes.candidates.json.
If it exists, new records are appended with continuing ids; a source_ref already present is skipped.
Prints a JSON summary; errors go to stderr, one per line, exit 1.
"""

import re
import sys
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from providers import run_provider, ProviderError, resolve_path, REPO_ROOT
from validate_evidence import problem_ids
from pii import scan, scrub, load_pii_config

MAX_QUOTE_WORDS = 40
ELLIPSIS = "…"
CANDIDATES_FILE = "04-anecdotes.candidates.json"
QUERY_ID = "anecdotes_by_keyword"
TEXT_FIELDS = ("source", "source_ref", "date", "segment", "persona", "pain", "quote")
ROW_FIELDS = TEXT_FIELDS + ("sentiment", "consent_ok")


class AnecdoteError(Exception):
    """A user-facing failure; the message may hold several lines."""


def word_count(quote: str) -> int:
    """Words in a quote; a trailing ellipsis is not a word."""
    return len(quote.rstrip(ELLIPSIS).split())


def truncate_quote(quote: str) -> Tuple[str, bool]:
    words = quote.split()
    if len(words) <= MAX_QUOTE_WORDS:
        return quote, False
    return " ".join(words[:MAX_QUOTE_WORDS]) + ELLIPSIS, True


def load_anecdote_schema() -> Dict[str, Any]:
    path = REPO_ROOT / "schemas" / "anecdote.schema.json"
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise AnecdoteError(f"Cannot load schema {path}: {e}")


def load_terms(config_path: str) -> Tuple[Dict[str, List[str]], bool]:
    try:
        return load_pii_config(resolve_path(config_path))
    except FileNotFoundError:
        raise AnecdoteError(f"Config not found: {config_path}")
    except Exception as e:
        raise AnecdoteError(f"Cannot read config {config_path}: {e}")


def read_candidates(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise AnecdoteError(f"Cannot read {path}: {e}")
    if not isinstance(data, list):
        raise AnecdoteError(f"{path} must be a JSON array")
    return data


def next_number(existing: List[Dict[str, Any]]) -> int:
    highest = 0
    for rec in existing:
        m = re.fullmatch(r"AN-(\d+)", str(rec.get("id", "")))
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def pull(args) -> Dict[str, Any]:
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise AnecdoteError(f"Run directory not found: {args.run_dir}")
    try:
        problems = problem_ids(run_dir)
    except ValueError as e:
        raise AnecdoteError(str(e))
    if args.problem not in problems:
        raise AnecdoteError(f"unknown problem '{args.problem}' (not in 02-problem.md)")

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if not keywords:
        raise AnecdoteError("--keywords must contain at least one keyword")
    if args.limit is not None and args.limit < 1:
        raise AnecdoteError("--limit must be a positive integer")

    pii_terms, allow_companies = load_terms(args.config)

    params: Dict[str, Any] = {"keywords": keywords}
    if args.segment:
        params["segment"] = args.segment
    if args.limit is not None:
        params["limit"] = args.limit
    request = {
        "question": f"Customer anecdotes about {', '.join(keywords)} for {args.problem}",
        "query_id": QUERY_ID,
        "params": params,
    }
    try:
        output = run_provider(
            args.provider, request,
            registry_path=args.registry, config_path=args.config, cache_dir=args.cache_dir,
        )
    except ProviderError as e:
        raise AnecdoteError(str(e))

    candidates_path = run_dir / CANDIDATES_FILE
    existing = read_candidates(candidates_path)
    seen_refs = {rec.get("source_ref") for rec in existing}
    number = next_number(existing)

    dropped = truncated = duplicates = 0
    new_records: List[Dict[str, Any]] = []
    for row in output["rows"]:
        if not isinstance(row, dict):
            raise AnecdoteError("provider returned a row that is not an object")
        missing = [k for k in ROW_FIELDS if k not in row]
        if missing:
            raise AnecdoteError(f"provider row is missing fields: {', '.join(missing)}")
        if row["consent_ok"] is not True:
            dropped += 1
            continue
        record: Dict[str, Any] = {"id": f"AN-{number:03d}"}
        for field in TEXT_FIELDS:
            value = row[field]
            if not isinstance(value, str):
                raise AnecdoteError(f"provider row field '{field}' is not text")
            record[field] = scrub(value, pii_terms, allow_companies)
        if record["source_ref"] in seen_refs:
            duplicates += 1
            continue
        record["quote"], was_cut = truncate_quote(record["quote"])
        truncated += was_cut
        record["sentiment"] = row["sentiment"]
        record["linked_problem"] = args.problem
        record["frequency_hint"] = None
        record["consent_ok"] = True
        seen_refs.add(record["source_ref"])
        new_records.append(record)
        number += 1

    schema_validator = Draft202012Validator(load_anecdote_schema())
    for rec in new_records:
        errors = list(schema_validator.iter_errors(rec))
        if errors:
            field = ".".join(str(p) for p in errors[0].path) or "record"
            raise AnecdoteError(f"{rec['id']}: field '{field}': {errors[0].message}")

    findings = []
    for rec in new_records:
        for field in TEXT_FIELDS:
            for f in scan(rec[field], pii_terms, allow_companies):
                findings.append(f"{rec['id']}: field '{field}': {f['type']}: {f['match']}")
    if findings:
        raise AnecdoteError("PII still present after scrubbing, nothing written:\n" + "\n".join(findings))

    try:
        with open(candidates_path, "w") as f:
            json.dump(existing + new_records, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        raise AnecdoteError(f"Cannot write {candidates_path}: {e}")
    return {
        "candidates": len(new_records),
        "total": len(existing) + len(new_records),
        "dropped_consent": dropped,
        "truncated": truncated,
        "duplicates_skipped": duplicates,
        "path": str(candidates_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Pull de-identified customer anecdotes.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pull", help="Write 04-anecdotes.candidates.json")
    p.add_argument("run_dir", help="Run directory (needs 02-problem.md)")
    p.add_argument("--provider", required=True)
    p.add_argument("--problem", required=True, help="Problem id, e.g. PB-1")
    p.add_argument("--keywords", required=True, help="Comma-separated keywords")
    p.add_argument("--segment", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--registry", default="connectors/registry.yaml")
    p.add_argument("--config", default="pm.config.yaml")
    p.add_argument("--cache-dir", default=".cache/providers")
    args = parser.parse_args()
    try:
        result = pull(args)
    except AnecdoteError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
