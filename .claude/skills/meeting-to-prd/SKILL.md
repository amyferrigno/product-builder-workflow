---
name: meeting-to-prd
description: Turn meeting notes into an audited PRD (Stage 1), stopping at Human Gate A for approval
---

## Trigger

`/pm-prd <path-or-paste> [--slug name]`

## Setup

1. Invoke with a file path (`.md`, `.txt`, `.docx`) or `-` to paste text
2. Provide `--slug <name>` for paste input (optional for files, overrides auto-derived slug)

## Execution

### Step 1: Intake

Run:
```bash
.venv/bin/python scripts/intake.py <path-or-paste> [--slug name] [--date YYYY-MM-DD] [--runs-dir runs]
```

Output: `runs/<date>-<slug>/` with:
- `00-notes/<original-filename>` (raw input as-is, bytes unchanged)
- `00-notes/notes.numbered.md` (every line prefixed with number)
- `state.json` (validates against `schemas/state.schema.json`)
- `approvals/` folder (empty until a human approves)

Exit 1 with error message if:
- Content is empty or whitespace-only
- File not found
- Unsupported extension (not `.md`, `.txt`, `.docx`)
- Slug format invalid (must match `^[a-z0-9]+(-[a-z0-9]+)*$`: lowercase letters and digits separated by single hyphens)
- Run folder already exists

### Step 2: Notes Extraction

Before each subagent launch, run `.venv/bin/python scripts/cost_meter.py check <run_dir>`. Exit 1 (`STOP:`) means do not launch: tell the human the stage budget is exceeded (they can raise `budgets` in `pm.config.yaml`). A `WARN:` line is relayed to the human.

Call agent `notes-extractor` with the run directory path only:
- Agent reads `00-notes/notes.numbered.md`
- Writes `01-extraction.json`

### Step 3: Validate Extraction

Run:
```bash
.venv/bin/python scripts/validate_extraction.py <run_dir>
```

Exit 1 with errors listed if validation fails. If it exits 1, send the validator's error lines to the same agent once and ask it to fix the file, then run the validator again. If it still fails, set `status` to `"failed"` in `state.json`, show the errors and stop. Never retry a second time.

Checks:
- Schema match
- All `source_lines` values exist in `notes.numbered.md`
- No cited lines are blank
- All IDs are unique
- `run_id` matches folder name

### Step 4: Problem Framing

Call agent `prd-writer` with paths only (task line: "problem framing"):
- Reads `01-extraction.json` from run directory
- Reads `templates/problem.md`
- Reads `templates/ai-gates.md`
- Reads `pm.config.yaml` (product section only)
- Writes `02-problem.md` to run directory
- Uses only the extraction; never reads `00-notes/`

### Step 5: Validate Problem

Run:
```bash
.venv/bin/python scripts/validate_problem.py <run_dir>
```

Exit 1 with errors listed if validation fails. If it exits 1, send the validator's error lines to the same agent once and ask it to fix the file, then run the validator again. If it still fails, set `status` to `"failed"` in `state.json`, show the errors and stop. Never retry a second time.

Checks:
- YAML front matter validates against `schemas/problem.schema.json`
- `run_id` matches folder name
- All required headings present
- All `source_items` IDs exist in extraction
- `primary_problem` and `parked_problems` exist in problems list
- Problem IDs are unique
- UNVALIDATED problems list missing evidence
- reframed_from_solution=true implies UNVALIDATED
- AI verdict matches computed verdict
- No TODO/TBD in front matter or body
- If disagreements in extraction, "Open questions" heading present

### Step 6: Record Stage 1 hashes

Update `<run_dir>/state.json`: set `artifact_hashes.extraction` and `artifact_hashes.problem` (sha256 hex of `01-extraction.json` and `02-problem.md`, use `shasum -a 256 <file>`), `audit_loops.prd` to `0`, `updated_at` to the current time (ISO-8601). Leave `stage` as "stage1" and `status` as "in_progress". Then run:
```bash
.venv/bin/python scripts/validate_schema.py schemas/state.schema.json <run_dir>/state.json
```
Stop if it exits 1.

### Step 7: Evidence

Read the registry (`connectors/registry.yaml`, or the path the human gave). If it has no enabled providers, do not create `03-evidence/` or `04-anecdotes.json`. The PRD must say so: "No data provider configured" in section 6a and "No anecdote provider configured" in section 6b.

If it has enabled providers, run both steps in parallel (two agent calls in one turn):
- Data: follow skill `data-enrichment` (`/pm-enrich <run-id>`, needs a `sql_readonly` provider). It calls agent `data-enricher` and writes `03-evidence/`.
- Anecdotes: follow skill `customer-anecdotes` (`/pm-anecdotes <run-id>`, needs an `anecdotes` provider). It calls agent `anecdote-curator` and writes `04-anecdotes.json`.

Validate both (`scripts/validate_evidence.py <run_dir>` and `scripts/validate_anecdotes.py <run_dir>`) with the one-retry rule those skills define, then continue to the draft. If only one kind of provider is enabled, run only that one and the PRD states the other is not configured. For the offline demo use `--registry fixtures/registry.mock.yaml --config fixtures/pm.config.mock.yaml`.

### Step 7b: Decision: PRD or no-PRD memo

Run:
```bash
.venv/bin/python scripts/prd_decision.py <run_dir>
```

It prints `PRD` or `MEMO`, then the reasons.

- `MEMO`: call agent `prd-writer` in memo mode (task line: "no-PRD memo") with the run directory path. It writes `no-prd-memo.md`. Run `.venv/bin/python scripts/validate_memo.py <run_dir>`; on errors send them to the same agent once and validate again. If it still fails, set `status` to `"failed"` in `state.json`, show the errors and stop. Then show the memo path and its decision line and stop: no PRD draft, no audit, no gate. If the human gives a reason to write the PRD anyway, they rerun with `.venv/bin/python scripts/prd_decision.py <run_dir> --force-prd "<reason>"`; never force it without the human's reason.
- `PRD`: continue as below.

### Step 8: PRD draft

Call agent `prd-writer` with paths only (task line: "PRD draft"), passing the run directory path. It reads `02-problem.md`, `01-extraction.json`, `03-evidence/` and `04-anecdotes.json` if they exist, `templates/prd.md`, `templates/prd-ai-addendum.md` and the `product` section of `pm.config.yaml`. It writes `<run_dir>/prd.md`. It never reads `00-notes/`.

### Step 9: Validate PRD

Run:
```bash
.venv/bin/python scripts/validate_prd.py <run_dir>
```

Exit 1 prints one error per line. Send those lines to the same agent once (task line: "PRD draft", fix these errors) and run the validator again. If it still fails, set `status` to `"failed"` in `state.json`, show the errors and stop. Never retry a second time.

### Step 10: Audit

1. Compute the PRD hash and keep it:
```bash
shasum -a 256 <run_dir>/prd.md
```
Use the first field (64 hex characters).
2. Call agent `prd-auditor` with three things only: the run directory path, the rubric path `templates/audit-prd.rubric.yaml` and that hash as `prd_hash`. Do not pass the writer's reasoning or `02-problem.md`.
3. Save the auditor's final message, verbatim, to `<run_dir>/prd.audit.json`. Do not edit it. If it is not valid JSON, ask the auditor once to return the JSON only.
4. Render and compute the verdict (the script decides, never you):
```bash
.venv/bin/python scripts/render_audit.py <run_dir>
```
It prints PASS, PASS_WITH_RISK or FAIL (exit 1 on FAIL), writes `prd.audit.md` and updates `state.json`. If it exits 2, the audit JSON is invalid: show the error and stop.

### Step 11: Revision loop (only on FAIL)

Read `audit.max_revision_loops` from `pm.config.yaml` (currently 2). While the verdict is FAIL and `state.json` `audit_loops.prd` is below that maximum:
1. Add 1 to `audit_loops.prd` in `state.json`.
2. Call agent `prd-writer` (task line: "PRD revision") with the run directory path. It edits only the flagged sections of `prd.md`.
3. Re-run Step 9, then Step 10 (new hash, fresh auditor call, new `prd.audit.json`).

Never exceed the maximum. If the verdict is still FAIL after the last allowed loop, set `status` to `"escalated"` in `state.json`, show `prd.audit.md` (reasons, fixes, hallucination findings) to the human, and stop.

### Step 12: Human Gate A

On PASS or PASS_WITH_RISK (`status` is now "awaiting_approval"), run:
```bash
.venv/bin/python scripts/gate_summary.py <run_dir> prd
```
Show the output to the human and STOP. Do not continue to Stage 2.

The human approves with `/pm-approve prd <run-id>`. The orchestrator must never run `scripts/approve.py` itself and must never write anything under `approvals/`. A hook blocks such writes. Editing `prd.md` after approval makes the approval stale.

## Errors

Return error and stop if:
- Intake fails: file issue (not found, corrupt, unsupported type, slug invalid)
- Content empty before creating run folder
- Extraction, problem or PRD validation still fails after the one retry (one error message per line)
- Run folder already exists (don't overwrite)
- `render_audit.py` exits 2 (invalid audit JSON)

## Success

Stage 1 ends at one of: `no-prd-memo.md` written and validated (no gate), `awaiting_approval` (Gate A summary shown), `escalated` (open audit issues shown) or `failed` (validator errors shown). Every state value used is allowed by `schemas/state.schema.json`.
