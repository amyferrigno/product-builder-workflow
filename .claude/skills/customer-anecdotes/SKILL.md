---
name: customer-anecdotes
description: Pull customer quotes for a run from an anecdote provider and curate 3 to 5 into 04-anecdotes.json
---

## Trigger

`/pm-anecdotes <run-id> [--keywords "a,b"]`

The run folder is `runs/<run-id>/` and must already have `02-problem.md`. Registry `connectors/registry.yaml` and config `pm.config.yaml` are the defaults.

Offline demo: add `--registry fixtures/registry.mock.yaml --config fixtures/pm.config.mock.yaml` to the pull and validate commands below.

## Execution

### Step 1: Check a provider exists

Read the registry. Look for an entry with `enabled: true` and capability `anecdotes`. If there is none, STOP and tell the human: "no anecdote provider configured". Do not create `04-anecdotes.json`.

### Step 2: Pick keywords

If `--keywords` was given, use it. Otherwise read `02-problem.md` and derive 3 to 6 short keywords (lowercase, comma-separated) from the primary problem's title and description. Note the primary problem id (for example `PB-1`) and, if the problem names one, the segment.

### Step 3: Pull candidates

Run:
```bash
.venv/bin/python scripts/anecdotes.py pull <run_dir> --provider <provider_id> --problem PB-1 --keywords "a,b" [--segment S] [--limit N] [--registry connectors/registry.yaml] [--config pm.config.yaml]
```

It writes `<run_dir>/04-anecdotes.candidates.json`. The script drops records without consent, scrubs personal data, shortens quotes to 40 words and assigns ids. If it exits 1 (for example PII remains), show the error and stop. Never work around it.

### Step 4: Curate

Call agent `anecdote-curator` with paths only: the run directory. It reads the candidates, `02-problem.md` and `03-evidence/` if it exists, and writes `04-anecdotes.json`.

### Step 5: Validate

Run:
```bash
.venv/bin/python scripts/validate_anecdotes.py <run_dir> [--config pm.config.yaml]
```

Exit 1 prints one error per line. Send those lines to the same agent once and ask it to fix the file, then run the validator again. If it still fails, set `status` to `"failed"` in `state.json`, show the errors and stop. Never retry a second time.

### Step 6: Record the hash

Run:
```bash
shasum -a 256 <run_dir>/04-anecdotes.json
```

Update `<run_dir>/state.json`: set `artifact_hashes.anecdotes` to the first field and `updated_at` to the current time (ISO-8601). Then run:
```bash
.venv/bin/python scripts/validate_schema.py schemas/state.schema.json <run_dir>/state.json
```
Stop if it exits 1.

### Step 7: Show the result

List each record: `id`, `segment`, `sentiment`, `pain`, `frequency_hint`. Say which one is the counter-anecdote.

## Rules

- Quotes are copied from the candidates unchanged. Never reword or invent a quote.
- A `frequency_hint` of null means frequency unknown. Do not fill it by guessing.
- A hook scans `04-anecdotes.json` and `prd.md` for personal data after every write.
- Never run `scripts/approve.py` and never write under `approvals/`.

## Errors

Return error and stop if:
- No enabled anecdote provider (message: "no anecdote provider configured")
- `02-problem.md` is missing
- The pull exits 1
- Curation validation still fails after the one retry
