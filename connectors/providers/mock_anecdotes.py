#!/usr/bin/env python3
"""
Mock anecdote provider (script provider, see schemas/provider-io.schema.json).
Reads a request JSON on stdin, prints an output JSON on stdout. Always exits 0.

Request: {"question", "query_id": "anecdotes_by_keyword",
          "params": {"keywords": [..] or "a,b", "segment": optional, "limit": optional}}

Returns matching synthetic records RAW (not scrubbed): scrubbing and consent filtering are
the caller's job (scripts/anecdotes.py). A record matches when any keyword appears
(case-insensitive) in its keywords, pain or quote.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "mock_anecdotes" / "tickets.json"
QUERY_ID = "anecdotes_by_keyword"
CAVEATS = ["synthetic mock data"]


def _output(ok, rows, query_hash, error=None):
    out = {
        "ok": ok,
        "rows": rows,
        "n": len(rows),
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "query_hash": query_hash,
        "caveats": list(CAVEATS),
    }
    if error is not None:
        out["error"] = error
    return out


def _parse_keywords(value):
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = value
    else:
        return None
    keywords = [str(k).strip().lower() for k in items if str(k).strip()]
    return keywords or None


def run(request):
    qhash = hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    if not isinstance(request, dict):
        return _output(False, [], qhash, "request must be a JSON object")
    if request.get("query_id") != QUERY_ID:
        return _output(False, [], qhash, f"unknown query_id: {request.get('query_id')}")
    params = request.get("params")
    if not isinstance(params, dict):
        return _output(False, [], qhash, "params must be an object")
    keywords = _parse_keywords(params.get("keywords"))
    if keywords is None:
        return _output(False, [], qhash, "params.keywords must be a non-empty list or comma string")
    segment = params.get("segment")
    if segment is not None and not isinstance(segment, str):
        return _output(False, [], qhash, "params.segment must be a string")
    limit = params.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        return _output(False, [], qhash, "params.limit must be a positive integer")

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)
    except (OSError, ValueError) as e:
        return _output(False, [], qhash, f"cannot read mock data: {e}")

    matches = []
    for rec in records:
        if segment and str(rec.get("segment", "")).lower() != segment.lower():
            continue
        haystack = " ".join(
            [" ".join(rec.get("keywords", [])), str(rec.get("pain", "")), str(rec.get("quote", ""))]
        ).lower()
        if any(k in haystack for k in keywords):
            matches.append(rec)

    out = _output(True, matches[:limit] if limit else matches, qhash)
    out["n"] = len(matches)
    return out


def main():
    try:
        request = json.load(sys.stdin)
    except (ValueError, EOFError):
        print(json.dumps(_output(False, [], hashlib.sha256(b"").hexdigest(), "invalid JSON on stdin")))
        return 0
    print(json.dumps(run(request)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
