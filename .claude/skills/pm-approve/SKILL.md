---
name: pm-approve
description: Human approval of the PRD at Gate A, tied to the PRD hash
disable-model-invocation: true
---

## Trigger

`/pm-approve prd <run-id> [override reason]`

Only a human may trigger this skill. The model must never invoke it on its own, and must never run `scripts/approve.py` outside it.

## Execution

1. Approve (from the repo root):
```bash
.venv/bin/python scripts/approve.py runs/<run-id> prd
```
Add `--override "<reason>"` only if the human typed an override reason. Never invent a reason. Without an override, the script refuses unless the audit verdict is PASS or PASS_WITH_RISK.

2. Check the approval:
```bash
.venv/bin/python scripts/check_approval.py runs/<run-id> prd
```
Exit 0 and "approved" means the approval matches the current `prd.md`. Exit 1 prints "missing", "stale" or "invalid".

3. Report the result in plain words: approved or refused, the script's message, the check result and, if an override was used, that it was recorded in `decisions.md`.

## Rules

- Do not write under `runs/<run-id>/approvals/` by hand. A hook blocks it. Only `scripts/approve.py` writes approvals.
- Editing `prd.md` after approval makes the approval stale. The PRD then needs approving again.
