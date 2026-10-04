#!/usr/bin/env python3
"""
Run a data provider and write an evidence card. The card's numbers come from the
provider output, never from the caller.

Usage:
  python scripts/enrich.py run <run_dir> --provider P (--query-id Q | --sql "SELECT ...")
      --question "..." --claim "TEMPLATE" --supports PB-1 [--params '{...}'] [--segment S]
      [--period P] [--metric M] [--registry R] [--config C] [--queries-dir D] [--cache-dir D]
      [--value-field F] [--n-field F]

--claim is a TEMPLATE the script fills from the provider output, so the caller never types a number:
  {value}      the provider value (integers as-is, else at most 2 decimals, trailing zeros trimmed)
  {value_pct}  value x 100, at most 1 decimal, no percent sign; write it as {value_pct}% or
               {value_pct} percent; only valid when 0 <= value <= 1
  {n}          the n integer
The template needs {value} or {value_pct}, no digits of its own, no unknown placeholders, no
magnitude word (k, m, mn, mm, bn, x, hundred, thousand, million, billion, times) after a placeholder, and % only after
{value_pct}. The card stores the rendered claim and the template (claim_template).
The provider's query_hash must equal the sha256 of the query text computed here, else the run is
refused (stale or wrong query). The cache key includes that hash, and an output whose value cell
is not a number is never cached (run_provider cache_filter).
Library query: value comes from the query's value_field in the first row, n from n_field.
Confidence is high for a reviewed query, low otherwise.
Ad-hoc (--sql): guarded by sql_guard first, sent to the provider as query_id adhoc_<8 hex>
with the SQL text in params["__sql"], saved to the library as status unreviewed, confidence low.
--value-field / --n-field pick the columns for ad-hoc queries (default: first column, and the
provider's row count).
Prints {"id", "path", "value", "n", "claim", "confidence"} as JSON on success; errors go to stderr, one per line,
exit 1.
"""

import os
import re
import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from providers import run_provider, ProviderError, load_config, resolve_path
from sql_guard import check_sql
from validate_evidence import (
    load_library, problem_ids, claim_number_errors, confidence_for, load_evidence_schema,
    render_claim, param_names, query_hash_of,
)


class EnrichError(Exception):
    """A user-facing failure; the message is one line."""


def next_card_id(evidence_dir: Path) -> str:
    highest = 0
    if evidence_dir.is_dir():
        for f in evidence_dir.glob("EV-*.json"):
            m = re.fullmatch(r"EV-(\d+)\.json", f.name)
            if m:
                highest = max(highest, int(m.group(1)))
    return f"EV-{highest + 1:03d}"


def save_adhoc_query(queries_dir: Path, query_id: str, sql: str, entry: Dict[str, Any]) -> None:
    """Append an unreviewed ad-hoc query to the library and save its .sql file."""
    try:
        library = load_library(queries_dir)
    except ValueError as e:
        raise EnrichError(str(e))
    if any(q.get("id") == query_id for q in library):
        return
    library.append(entry)
    try:
        with open(queries_dir / entry["file"], "w") as f:
            f.write(sql)  # exactly the text the provider hashed
        with open(queries_dir / "index.yaml", "w") as f:
            yaml.safe_dump({"queries": library}, f, sort_keys=False)
    except OSError as e:
        raise EnrichError(f"Cannot write query library: {e}")


def to_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EnrichError(f"provider {label} is not a number")  # never echo the cell contents
    return float(value)


def run(args) -> Dict[str, Any]:
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise EnrichError(f"Run directory not found: {args.run_dir}")

    try:
        problems = problem_ids(run_dir)
    except ValueError as e:
        raise EnrichError(str(e))
    if args.supports not in problems:
        raise EnrichError(f"unknown problem '{args.supports}' (not in 02-problem.md)")

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError:
        raise EnrichError("--params must be valid JSON")
    if not isinstance(params, dict):
        raise EnrichError("--params must be a JSON object")

    try:
        render_claim(args.claim, 0.5, 0)  # refuse a bad template before calling the provider
    except ValueError as e:
        raise EnrichError(str(e))

    if bool(args.query_id) == bool(args.sql):
        raise EnrichError("give exactly one of --query-id or --sql")

    queries_dir = resolve_path(args.queries_dir).resolve()
    os.environ["PM_QUERIES_DIR"] = str(queries_dir)

    try:
        config = load_config(args.config)
    except ProviderError as e:
        raise EnrichError(str(e))

    request_params = dict(params)
    if args.sql:
        sql = args.sql
        try:
            pii_tables = list(config["data"].get("pii_tables", []))
            max_rows = config["data"]["max_rows_returned"]
            aggregate_only = bool(config["data"].get("aggregate_only", True))
        except (KeyError, TypeError):
            raise EnrichError(f"Config {args.config} is missing the data section")
        guard_errors = check_sql(sql, pii_tables, max_rows, aggregate_only)
        if guard_errors:
            raise EnrichError("\n".join(guard_errors))
        sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        expected_hash = sql_hash
        query_id = f"adhoc_{sql_hash[:8]}"
        request_params["__sql"] = sql
        status = "unreviewed"
        value_field: Optional[str] = args.value_field
        n_field: Optional[str] = args.n_field
        metric = args.metric or "ad_hoc_query"
    else:
        try:
            library = {q.get("id"): q for q in load_library(queries_dir)}
        except ValueError as e:
            raise EnrichError(str(e))
        query = library.get(args.query_id)
        if query is None:
            raise EnrichError(f"unknown query_id '{args.query_id}'")
        if query.get("provider") != args.provider:
            raise EnrichError(f"query '{args.query_id}' belongs to provider '{query.get('provider')}'")
        missing = [p for p in param_names(query) if p not in params]
        if missing:
            raise EnrichError(f"missing params for '{args.query_id}': {', '.join(missing)}")
        try:
            expected_hash = query_hash_of(queries_dir, query)
        except (OSError, KeyError):
            raise EnrichError(f"Cannot read the library file for query '{args.query_id}'")
        query_id = args.query_id
        status = query.get("status", "unreviewed")
        value_field = query.get("value_field")
        n_field = query.get("n_field")
        metric = args.metric or query.get("metric") or query_id

    request = {"question": args.question, "query_id": query_id, "params": request_params}

    def numeric_value_cell(out: Dict[str, Any]) -> bool:
        """Cache only outputs whose value cell is a number (never cache text a provider returned)."""
        rows = out.get("rows")
        if not rows or not isinstance(rows[0], dict) or not rows[0]:
            return False
        cell = rows[0].get(value_field) if value_field else next(iter(rows[0].values()))
        return isinstance(cell, (int, float)) and not isinstance(cell, bool)

    try:
        output = run_provider(
            args.provider, request,
            registry_path=args.registry, config_path=args.config, cache_dir=args.cache_dir,
            cache_salt=expected_hash, cache_filter=numeric_value_cell,
        )
    except ProviderError as e:
        raise EnrichError(str(e))

    if output["query_hash"] != expected_hash:
        raise EnrichError("provider query_hash does not match the library query (stale or wrong query)")

    if not output["rows"]:
        raise EnrichError("provider returned no rows")
    first = output["rows"][0]
    if value_field is None:
        value_field = next(iter(first))
    if value_field not in first:
        raise EnrichError(f"value_field '{value_field}' not in provider output")
    value = to_number(first[value_field], "value")
    if n_field:
        if n_field not in first:
            raise EnrichError(f"n_field '{n_field}' not in provider output")
        n = int(to_number(first[n_field], "n"))
    else:
        n = output["n"]

    try:
        claim = render_claim(args.claim, value, n)
    except ValueError as e:
        raise EnrichError(str(e))
    claim_errors = claim_number_errors(claim, value, n)
    if claim_errors:
        raise EnrichError("\n".join(claim_errors))

    card = {
        "id": next_card_id(run_dir / "03-evidence"),
        "claim": claim,
        "claim_template": args.claim,
        "metric": metric,
        "value": value,
        "segment": args.segment or str(params.get("segment", "all")),
        "period": args.period or "all",
        "n": n,
        "source": args.provider,
        "query_id": query_id,
        "query_hash": output["query_hash"],
        "run_at": output["run_at"],
        "confidence": confidence_for(status),
        "caveats": list(output["caveats"]),
        "supports_problem": args.supports,
    }
    try:
        schema_errors = list(Draft202012Validator(load_evidence_schema()).iter_errors(card))
    except ValueError as e:
        raise EnrichError(str(e))
    if schema_errors:
        raise EnrichError(f"evidence card is invalid: {schema_errors[0].message}")

    if args.sql:
        save_adhoc_query(queries_dir, query_id, sql, {
            "id": query_id,
            "provider": args.provider,
            "file": f"{query_id}.sql",
            "description": args.question,
            "metric": metric,
            "metric_definition": "ad-hoc query, not reviewed",
            "params": [{"name": k, "description": "ad-hoc parameter"} for k in sorted(params.keys())],
            "value_field": value_field,
            "n_field": n_field,
            "status": "unreviewed",
        })

    card_path = run_dir / "03-evidence" / f"{card['id']}.json"
    try:
        card_path.parent.mkdir(parents=True, exist_ok=True)
        with open(card_path, "w") as f:
            json.dump(card, f, indent=2)
            f.write("\n")
    except OSError as e:
        raise EnrichError(f"Cannot write {card_path}: {e}")
    return {
        "id": card["id"], "path": str(card_path), "value": value, "n": n,
        "claim": claim, "confidence": card["confidence"],
    }


def main():
    parser = argparse.ArgumentParser(description="Run a provider and write an evidence card.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="Run a provider query and write the next EV-### card")
    p.add_argument("run_dir", help="Run directory (needs 02-problem.md)")
    p.add_argument("--provider", required=True)
    p.add_argument("--query-id", default=None)
    p.add_argument("--sql", default=None, help="Ad-hoc SQL (saved as unreviewed, confidence low)")
    p.add_argument("--params", default="{}", help="JSON object of query parameters")
    p.add_argument("--question", required=True)
    p.add_argument("--claim", required=True,
                   help="Claim template with {value}, {value_pct} (before %% or percent) and {n}; no digits")
    p.add_argument("--supports", required=True, help="Problem id, e.g. PB-1")
    p.add_argument("--segment", default=None)
    p.add_argument("--period", default=None)
    p.add_argument("--metric", default=None)
    p.add_argument("--value-field", default=None, help="Ad-hoc only: column holding the value")
    p.add_argument("--n-field", default=None, help="Ad-hoc only: column holding n")
    p.add_argument("--registry", default="connectors/registry.yaml")
    p.add_argument("--config", default="pm.config.yaml")
    p.add_argument("--queries-dir", default="connectors/queries")
    p.add_argument("--cache-dir", default=".cache/providers")
    args = parser.parse_args()

    try:
        result = run(args)
    except EnrichError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
