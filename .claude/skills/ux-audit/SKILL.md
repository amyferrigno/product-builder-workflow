---
name: ux-audit
description: Audit an existing UX folder in a run folder (validator, auditor, verdict)
---

## Trigger

`/pm-audit ux <run-id>`

Use it to audit a UX folder that already sits in `runs/<run-id>/ux/`, for example after a hand edit, or to re-audit. It does not write or fix the UX.

## Execution

1. Validate:
```bash
.venv/bin/python scripts/validate_ux.py runs/<run-id>
```
If it exits 1, show the error lines to the human and stop. The validator must be clean before the audit.

2. Hash the UX files:
```bash
.venv/bin/python scripts/ux_hash.py runs/<run-id>
```

3. Call agent `ux-auditor` in a fresh context with the run directory path, the rubric path `templates/audit-ux.rubric.yaml`, the `run_id` (the folder name) and the hash as `ux_hash`. Nothing else.

4. Save the auditor's final message verbatim to `runs/<run-id>/ux.audit.json`. Do not edit it. If it is not valid JSON, ask the auditor once to return the JSON only.

5. Render:
```bash
.venv/bin/python scripts/render_ux_audit.py runs/<run-id>
```
It prints the verdict (PASS, PASS_WITH_RISK or FAIL), writes `ux.audit.md` and updates `state.json`. Exit 2 means the audit JSON is invalid: show the error and stop.

## Summary

Show `ux.audit.md` to the human: the verdict, the score for each dimension, the reasons, and the fixes with their screen ids.

## Rules

- The script computes the verdict, never the orchestrator.
- On FAIL, report the fixes. Do not edit the UX here. To loop with the designer, use `/pm-ux`.
- Never run `scripts/approve.py` and never write under `approvals/`. Approval is `/pm-approve`, human only.
