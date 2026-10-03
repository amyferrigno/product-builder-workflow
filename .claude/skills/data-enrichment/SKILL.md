---
name: data-enrichment
description: Pull numbers for a run from a data provider into validated evidence cards (03-evidence/)
---

## Trigger

`/pm-enrich <run-id> [--registry path] [--config path]`

Defaults: registry `connectors/registry.yaml`, config `pm.config.yaml`. The run folder is `runs/<run-id>/` and must already have `02-problem.md` (Stage 1 problem framing done).

Offline demo: use the mock registry and config, which enable a fake warehouse:
`/pm-enrich <run-id> --registry fixtures/registry.mock.yaml --config fixtures/pm.config.mock.yaml`

## Execution

### Step 1: Check a provider exists

Read the registry. Look for an entry with `enabled: true` and capability `sql_readonly`. If there is none, STOP and tell the human: "no data provider configured". Do not create `03-evidence/`. The PRD will state this.

### Step 2: Enrich

Call agent `data-enricher` with paths only: the run directory, the registry path and the config path. The agent runs `scripts/enrich.py`, which is the only thing that writes evidence cards (`03-evidence/EV-###.json`). Do not write or edit cards yourself.

How the agent calls it:
- `--claim` is a TEMPLATE. Placeholders: `{value}` (provider value), `{value_pct}` (value x 100, no percent sign, only for fractions 0 to 1, written as `{value_pct}%` or `{value_pct} percent`), `{n}`. No digit may be written in the template; the script fills the numbers and prints `value`, `n` and the rendered `claim`.
- Required options: `run_dir`, `--provider`, `--question`, `--claim`, `--supports`, and one of `--query-id` or `--sql`. Optional: `--params`, `--segment`, `--period`, `--metric`, `--registry`, `--config`, `--value-field`, `--n-field`.
- Parameter names, formats, allowed values and a working `example` are in `connectors/queries/index.yaml`. Never guess parameter values.
- `--period` and `--segment` are labels stored on the card; they should mirror the params used.
- Example, share of tickets:
  `.venv/bin/python scripts/enrich.py run <run_dir> --provider mock_warehouse --query-id ticket_share_by_category --params '{"category": "scheduling_conflict", "period_start": "2025-07", "period_end": "2025-12"}' --question "What share of tickets are scheduling conflicts?" --claim "{value_pct}% of {n} tickets are scheduling conflicts" --supports PB-1 --period 2025-07..2025-12 --registry <registry_path> --config <config_path>`
- Example, median for a segment:
  `.venv/bin/python scripts/enrich.py run <run_dir> --provider mock_warehouse --query-id median_minutes_to_confirm --params '{"segment": "enterprise"}' --question "How long to confirm?" --claim "Median is {value} minutes over {n} meetings" --supports PB-1 --segment enterprise --registry <registry_path> --config <config_path>`
- On `query returned no rows for these params`: check the allowed values once, retry once, then record an evidence gap.

### Step 3: Validate

Run:
```bash
.venv/bin/python scripts/validate_evidence.py <run_dir>
```

Exit 1 prints one error per line. Send those lines to the same agent once and ask it to fix them by running the script again. Run the validator again. If it still fails, set `status` to `"failed"` in `state.json`, show the errors and stop. Never retry a second time.

### Step 4: Record the hash

Define the evidence hash as the sha256 of the concatenation of the card files in sorted order:
```bash
cat $(ls <run_dir>/03-evidence/EV-*.json | sort) | shasum -a 256 | cut -d' ' -f1
```

Update `<run_dir>/state.json`: set `artifact_hashes.evidence` to that value and `updated_at` to the current time (ISO-8601). Then run:
```bash
.venv/bin/python scripts/validate_schema.py schemas/state.schema.json <run_dir>/state.json
```
Stop if it exits 1.

### Step 5: List the cards

Show the human a short table from the cards: `id`, `claim`, `value`, `n`, `confidence`. Also show the agent's list of questions it could not answer. They are evidence gaps for PRD section 6c.

## Rules

- Never type a number into a card or a claim yourself (claims are templates). Numbers come from provider output through `scripts/enrich.py`.
- Cards from ad-hoc SQL are `confidence: low` and their query is saved as `unreviewed`. Say so when you list them.
- Read-only: a hook blocks mutating SQL, and the provider and script refuse it too.
- Never run `scripts/approve.py` and never write under `approvals/`.

## Errors

Return error and stop if:
- No enabled data provider (message: "no data provider configured")
- `02-problem.md` is missing
- Evidence validation still fails after the one retry
