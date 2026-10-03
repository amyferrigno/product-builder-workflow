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

- Never type a number into a card or a claim yourself. Numbers come from provider output through `scripts/enrich.py`.
- Cards from ad-hoc SQL are `confidence: low` and their query is saved as `unreviewed`. Say so when you list them.
- Read-only: a hook blocks mutating SQL, and the provider and script refuse it too.
- Never run `scripts/approve.py` and never write under `approvals/`.

## Errors

Return error and stop if:
- No enabled data provider (message: "no data provider configured")
- `02-problem.md` is missing
- Evidence validation still fails after the one retry
