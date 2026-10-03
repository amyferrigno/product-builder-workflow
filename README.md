# Agentic PM Workflow

An AI-driven workflow to turn meeting notes into audited PRDs, UX mocks, and Jira tickets. Multi-stage pipeline with human approval gates.

## Setup

```bash
make setup    # Create .venv, install dependencies (Python 3.9+)
```

## Run Tests

```bash
make test     # Run pytest
```

All tests must pass before merging. Schema validation is automatic.

## Milestones

See [planning.md](planning.md) for the full roadmap and status.

- **M0** (done): Scaffold—repo layout, config, schemas, validator, tests.
- **M1** (done): Extraction + problem framing.
- **M2** (done): PRD writer + auditor.
- **M3 + M4** (current, merged): Data enrichment and customer anecdotes.
- **M5**: UX design.
- **M6**: Jira dry-run.
- **M7**: Jira publish.
- **M8**: Cost + polish.

## Running the Workflow (M1: Extraction + Problem Framing)

### Intake: Convert notes to numbered, citable source

```bash
# From a file
.venv/bin/python scripts/intake.py path/to/notes.md [--slug name] [--date YYYY-MM-DD]

# From stdin
echo "notes here" | .venv/bin/python scripts/intake.py - --slug mymeeting

# Output: run ID and path to numbered notes
```

Supports `.md`, `.txt`, `.docx`, and stdin. Creates `runs/<date>-<slug>/` with numbered notes and `state.json`.

### Validators

```bash
# Check extraction.json
.venv/bin/python scripts/validate_extraction.py runs/2026-01-15-demo/

# Check problem.md
.venv/bin/python scripts/validate_problem.py runs/2026-01-15-demo/
```

Both exit 1 on errors, print one error per line. Extraction validator enforces that all cited lines are non-blank. Problem validator also checks AI verdict logic.

## Running the Workflow (M2: PRD, audit, approval)

Commands (skills in `.claude/skills/`):

- `/pm-prd <path-or-paste>`: intake, extraction, problem framing, PRD draft, validation, audit, revision loop (up to `audit.max_revision_loops`), then stops at Human Gate A with a summary.
- `/pm-audit prd <run_dir>`: audit an existing or hand-written PRD in a run folder.
- `/pm-approve prd <run-id> [override reason]`: human only. Approves the PRD, tied to its hash.

Scripts:

```bash
.venv/bin/python scripts/validate_prd.py runs/<run-id>/       # structure, IDs, citations, number tracing
.venv/bin/python scripts/render_audit.py runs/<run-id>/       # prd.audit.json -> verdict, prd.audit.md, state.json
.venv/bin/python scripts/audit_verdict.py runs/<run-id>/      # verdict only
.venv/bin/python scripts/gate_summary.py runs/<run-id>/ prd   # one-screen Gate A summary
.venv/bin/python scripts/approve.py runs/<run-id>/ prd [--override "reason"]
.venv/bin/python scripts/check_approval.py runs/<run-id>/ prd # exit 0 only if approval matches current prd.md
```

Hooks (`.claude/settings.json`):

- `guard_approvals.py` (before Write/Edit): blocks any write under `runs/*/approvals/`.
- `validate_artifact.py` (after Write/Edit): runs `validate_prd.py` when `runs/*/prd.md` is edited and reports errors.

Agents: `prd-writer` (problem framing, PRD draft, PRD revision) and `prd-auditor` (read-only, returns audit JSON). The verdict is computed by script, not by the auditor.

## Evidence plug-ins (M3 + M4: data and anecdotes)

Numbers and quotes come from scripts, never from a model. Evidence cards (`runs/<id>/03-evidence/EV-###.json`) are written only by `scripts/enrich.py` from provider output. Anecdotes are copied unchanged from scrubbed candidates.

Commands (skills in `.claude/skills/`):

- `/pm-enrich <run-id> [--registry path] [--config path]`: agent `data-enricher` asks 2 to 5 data questions per problem, picks library queries and runs `enrich.py`; then `validate_evidence.py` checks the cards. Stops with "no data provider configured" if none is enabled.
- `/pm-anecdotes <run-id> [--keywords "a,b"]`: `anecdotes.py pull` writes `04-anecdotes.candidates.json`, agent `anecdote-curator` keeps 3 to 5 (with a counter-anecdote when one exists), `validate_anecdotes.py` checks them.
- `/pm-prd` runs both in parallel when the registry has enabled providers.

The `--claim` is a template, not a sentence with numbers. The script fills `{value}` (the provider value), `{value_pct}` (value x 100, written as `{value_pct}%` or `{value_pct} percent`, only for fractions 0 to 1) and `{n}` from the provider output, and refuses a template with its own digits, unknown placeholders or a magnitude word (k, m, mn, mm, bn, x, hundred, thousand, million, billion, times) after a number. `validate_evidence.py` re-checks every number in a claim with the same rules, and checks that `query_hash` is the sha256 of the library `.sql` file text and that `source` is the query's provider. Parameter names, formats, allowed values and a working `example` for each library query are in `connectors/queries/index.yaml`.

Offline demo (no real connections): the real `connectors/registry.yaml` stays all-disabled. A separate mock registry enables a fake warehouse and a fake anecdote source:

```bash
.venv/bin/python scripts/enrich.py run runs/<run-id> --provider mock_warehouse --query-id median_minutes_to_confirm \
  --params '{"segment": "smb"}' --question "How long does confirming take for smb?" \
  --claim "Median time to confirm is {value} minutes (n={n})" --supports PB-1 --segment smb \
  --registry fixtures/registry.mock.yaml --config fixtures/pm.config.mock.yaml
.venv/bin/python scripts/anecdotes.py pull runs/<run-id> --provider mock_anecdotes --problem PB-1 --keywords "scheduling,confirm" \
  --registry fixtures/registry.mock.yaml --config fixtures/pm.config.mock.yaml
```

Read-only guard: `scripts/sql_guard.py` allows only a single `SELECT` / `WITH ... SELECT`, rejects INSERT, UPDATE, DELETE, MERGE, DROP, ALTER, CREATE, GRANT, TRUNCATE, REPLACE, ATTACH and PRAGMA, `SELECT *` on `data.pii_tables`, non-aggregate queries (when `data.aggregate_only` is true: at least one aggregate call is needed, `GROUP BY` alone does not count; window functions, `group_concat` and `string_agg` are rejected), `[bracket]` identifiers, and any `LIMIT` that is not `LIMIT <integer>` or `LIMIT <integer> OFFSET <integer>` with the integer at most `data.max_rows_returned`. A query that touches a PII table may only select `COUNT(...)` expressions or literals and may not use `GROUP BY`, `MIN`, `MAX`, `SUM`, `AVG`, `group_concat` or `string_agg`; reviewed library queries that need to group by something must avoid the PII table. The same checks run in three places as an early warning: the guard function, the provider (before it executes) and the hook `guard_readonly_query.py` (before Bash and `mcp__*` calls). They are not the control; see the next paragraph.

What enforces read-only and PII rules: the provider does. The mock warehouse installs a sqlite authorizer that allows only reads, refuses every column of a table listed in `data.pii_tables` and refuses the schema tables and any function not on its allowlist. For a real warehouse, use a read-only database role and PII-free views, and list the PII tables in `data.pii_tables`. The text guard and the hook are early warnings only: they catch honest mistakes but cannot understand every spelling of SQL. Known limits: a row count of a PII table (`COUNT(*)`) is allowed; and a hand-written evidence card with a copied query hash would still validate, so that guarantee rests on the agents' tool limits (the enricher has no Write tool). The cache key includes the sha256 of the query text, so an edited library query is never served a stale result, and outputs whose value is not a number are never cached.

PII scan: `scripts/pii.py` scrubs and scans for emails, phone numbers, URLs with user info and the names listed under `anecdotes.pii_terms` in the config. `anecdotes.py pull` drops records without consent and fails if PII remains. The hook `pii_scan.py` (after Write/Edit) scans `04-anecdotes.json`, `04-anecdotes.candidates.json` and `prd.md`. Manual check: `.venv/bin/python scripts/pii.py scan <file>`.

PRD rule: any quoted passage of 4 or more words in section 6b must appear in an anecdote record or an extraction item.

## Add a data provider in under 10 minutes

1. Write a script that reads the request JSON on stdin and prints the output JSON on stdout (shapes from `schemas/provider-io.schema.json`).

   Request:
   ```json
   {"question": "How long does confirming take?", "query_id": "median_minutes_to_confirm", "params": {"segment": "smb"}}
   ```
   Output (`ok`, `rows`, `n`, `run_at`, `query_hash`, `caveats` are required; `error` is required when `ok` is false):
   ```json
   {"ok": true, "rows": [{"median_minutes": 62.0, "n_meetings": 94}], "n": 1, "run_at": "2026-10-03T11:00:00+00:00", "query_hash": "<sha256>", "caveats": ["what to keep in mind"]}
   ```
   Skeleton (`connectors/providers/my_source.py`). It hashes the SQL text of the library query (the same text `validate_evidence.py` hashes), and `run_query` here is a tiny demo you replace with your read-only code:
   ```python
   import os, sys, json, hashlib, sqlite3
   from datetime import datetime, timezone

   import yaml

   def load_sql(query_id):
       queries_dir = os.environ.get("PM_QUERIES_DIR", "connectors/queries")  # set by enrich.py
       with open(os.path.join(queries_dir, "index.yaml")) as f:
           for q in yaml.safe_load(f)["queries"]:
               if q["id"] == query_id:
                   with open(os.path.join(queries_dir, q["file"])) as g:
                       return g.read()
       raise ValueError(f"unknown query_id '{query_id}'")

   def run_query(sql, params):  # demo only: replace with your read-only, aggregate-only code
       db = sqlite3.connect(":memory:")
       db.execute("CREATE TABLE demo (value INTEGER)")
       db.executemany("INSERT INTO demo VALUES (?)", [(i,) for i in range(1, 11)])
       cur = db.execute(sql, params)
       names = [d[0] for d in cur.description]
       return [dict(zip(names, row)) for row in cur.fetchall()]

   def main():
       req = json.load(sys.stdin)
       out = {"ok": False, "rows": [], "n": 0, "query_hash": ""}
       try:
           sql = load_sql(req["query_id"])
           out["query_hash"] = hashlib.sha256(sql.encode("utf-8")).hexdigest()
           rows = run_query(sql, req["params"])
           if not rows or next(iter(rows[0].values())) is None:
               out["error"] = "query returned no rows for these params"
           else:
               out.update(ok=True, rows=rows, n=len(rows))
       except Exception as e:  # refuse, never crash
           out["error"] = str(e)
       out.update(run_at=datetime.now(timezone.utc).isoformat(), caveats=[])
       print(json.dumps(out))

   if __name__ == "__main__":
       main()
   ```
2. Register it in `connectors/registry.yaml` (set `enabled: true` only when it is real and approved):
   ```yaml
   - id: my_source
     kind: script
     enabled: true
     command: "python connectors/providers/my_source.py"
     capabilities:
       - sql_readonly
   ```
3. Add a query to `connectors/queries/index.yaml` (use a new id), with its `.sql` file next to it (here `connectors/queries/demo_rows_above.sql`: `SELECT COUNT(*) AS n_rows FROM demo WHERE value > :min_value`). Each param is an object with `name`, `description` and either `format` or `allowed_values`; add an `example` request that returns rows. Set `status: reviewed` only after a person has checked the metric definition:
   ```yaml
   - id: demo_rows_above
     provider: my_source
     file: demo_rows_above.sql
     description: Number of demo rows above a threshold
     metric: demo_rows_above
     metric_definition: Count of demo rows whose value is greater than min_value
     params:
       - name: min_value
         description: Rows with a value above this are counted
         format: integer from 1 to 10
     example:
       question: How many demo rows are above 3?
       params: {min_value: 3}
     value_field: n_rows
     n_field: n_rows
     status: reviewed
   ```
4. Test it. Pipe a request into the script:
   ```bash
   echo '{"question": "q", "query_id": "demo_rows_above", "params": {"min_value": 3}}' | .venv/bin/python connectors/providers/my_source.py
   ```
   Then run `enrich.py` against a run (it needs `02-problem.md`) and validate:
   ```bash
   .venv/bin/python scripts/enrich.py run runs/<run-id> --provider my_source --query-id demo_rows_above \
     --params '{"min_value": 3}' --question "How many demo rows are above 3?" \
     --claim "{value} demo rows are above the threshold" --supports PB-1
   .venv/bin/python scripts/validate_evidence.py runs/<run-id>
   ```

## Key Files

- `CLAUDE.md`: Principles and repo layout.
- `decisions.md`: Aligned decisions with reasons.
- `memory.md`: Learnings and patterns from runs.
- `PLAN.md`: Current milestone steps.
- `pm.config.yaml`: Configuration and model tier mapping.
- `connectors/registry.yaml`: Registry of data sources.
- `schemas/`: JSON Schema validators.
- `scripts/`: Intake, AI gates logic, validators.
- `fixtures/`: Synthetic meeting notes with golden outputs.

## Architecture

The workflow operates in 3 stages:

1. **Stage 1** (Extraction): Meeting notes → structured problem statement.
2. **Stage 2** (PRD + UX): Problem → audited PRD and UX screens.
3. **Stage 3** (Jira): Screens → Jira tickets (dry-run or publish).

Each stage has a budget, gates, and approval checkpoints. See `PLAN.md` for the current milestone.
