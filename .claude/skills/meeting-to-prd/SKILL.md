---
name: meeting-to-prd
description: Turn meeting notes into a problem statement with an AI decision
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
- `approvals/` folder (empty, for M2)

Exit 1 with error message if:
- Content is empty or whitespace-only
- File not found
- Unsupported extension (not `.md`, `.txt`, `.docx`)
- Slug format invalid (must match `^[a-z0-9]+(-[a-z0-9]+)*$`: lowercase letters and digits separated by single hyphens)
- Run folder already exists

### Step 2: Notes Extraction

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

Call agent `prd-writer` with paths only:
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

### Step 6: Update state.json

Update `<run_dir>/state.json`:
- `stage`: leave as "stage1"
- `status`: leave as "in_progress" (Stage 1 is not finished until the PRD is drafted and audited in M2)
- `verdicts.prd`: leave as null (it holds the M2 audit verdict, not the AI verdict)
- `artifact_hashes.extraction`: sha256 hex of `01-extraction.json`
- `artifact_hashes.problem`: sha256 hex of `02-problem.md`
- `updated_at`: current time, ISO-8601

Then run:
```bash
.venv/bin/python scripts/validate_schema.py schemas/state.schema.json <run_dir>/state.json
```

Stop if it exits 1. The AI verdict is reported only in the Step 7 summary.

### Step 7: Summary

Print a short JSON summary:
```json
{
  "success": true,
  "run_id": "<date>-<slug>",
  "run_dir": "<path>",
  "extraction_items": <count>,
  "problems_found": <count>,
  "primary_problem": "PB-X",
  "ai_proposed": <true|false>,
  "ai_verdict": "<verdict or null>"
}
```

Add note: "Problem framing complete. PRD drafting arrives in M2."

## Errors

Return error and stop if:
- Intake fails: file issue (not found, corrupt, unsupported type, slug invalid)
- Content empty before creating run folder
- Extraction validation still fails after the one retry (one error message per line)
- Problem validation still fails after the one retry (one error message per line)
- Run folder already exists (don't overwrite)

## Success

All seven steps complete, both validators pass, state.json updated.
