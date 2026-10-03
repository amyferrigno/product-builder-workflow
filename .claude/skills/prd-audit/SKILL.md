---
name: prd-audit
description: Audit an existing PRD in a run folder (validator, auditor, verdict), including hand-written PRDs
---

## Trigger

`/pm-audit prd <run_dir>`

Use it to audit a PRD that already sits in a run folder, for example one a person wrote by hand, or to re-audit after an edit. It does not write or fix the PRD.

To audit UX screens instead, use `/pm-audit ux <run-id>` (skill `ux-audit`).

## Files the run folder needs

Next to `prd.md`:
- `01-extraction.json`: required. `validate_prd.py` fails without it. It may be minimal: a JSON object with the item lists as arrays of `{"id": "P-1", "text": "..."}` (keys: `problems`, `proposed_solutions`, `user_segments`, `requests`, `decisions`, `disagreements`, `open_questions`, `action_items`, `metrics_mentioned`). Every extraction ID the PRD cites, and every number in PRD sections 2, 3 and 6, must appear in it. `{}` works only for a PRD that cites no IDs and has no numbers there.
- `02-problem.md`: optional for the scripts. If present it needs YAML front matter. A minimal one is `run_id`, `problems` (each with `id`, so any `PB-#` in the PRD resolves), `primary_problem` and `ai: {proposed: false}`. Set `ai.proposed: true` only if the PRD has the A1 to A10 addendum. If it is missing, the validator assumes no AI and any `PB-#` citation is an error.
- `state.json`: required by `render_audit.py`. It must validate against `schemas/state.schema.json` (`run_id`, `stage`, `status`, `verdicts`, `artifact_hashes`, `approval_hashes`, `jira_keys`, `updated_at`). The easy way is `.venv/bin/python scripts/intake.py <any notes file> --slug <name> --runs-dir <dir>`, then put the other files in that folder.
- `03-evidence/` and `04-anecdotes.json`: only if the PRD cites `EV-###` or `AN-###`. Without them the PRD must say "No data provider configured" and "No anecdote provider configured".

Keep the run folder inside the repo, or run the commands from the repo root.

## Execution

1. Validate:
```bash
.venv/bin/python scripts/validate_prd.py <run_dir>
```
If it exits 1, show the error lines to the human and stop. The validator must be clean before the audit.

2. Hash the PRD:
```bash
shasum -a 256 <run_dir>/prd.md
```
Use the first field.

3. Call agent `prd-auditor` with the run directory path, the rubric path `templates/audit-prd.rubric.yaml` and the hash as `prd_hash`. Nothing else.

4. Save the auditor's final message verbatim to `<run_dir>/prd.audit.json`.

5. Render:
```bash
.venv/bin/python scripts/render_audit.py <run_dir>
```
It prints the verdict (PASS, PASS_WITH_RISK or FAIL), writes `prd.audit.md` and updates `state.json`. Show `prd.audit.md` to the human. Exit 2 means the audit JSON is invalid: show the error and stop.

## Rules

- The script computes the verdict, never the orchestrator.
- On FAIL, report the fixes. Do not edit the PRD here. To loop with a writer, use `/pm-prd`.
- Never run `scripts/approve.py` and never write under `approvals/`. Approval is `/pm-approve`, human only.
