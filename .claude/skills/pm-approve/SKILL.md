---
name: pm-approve
description: Human approval of the PRD at Gate A, the UX at Gate B and the tickets at Gate C, tied to the file hashes
disable-model-invocation: true
---

## Trigger

`/pm-approve prd <run-id> [override reason]`
`/pm-approve ux <run-id> [override reason]`
`/pm-approve tickets <run-id>`

Only a human may trigger this skill. The model must never invoke it on its own, and must never run `scripts/approve.py` outside it.

Claude Code will show a confirmation prompt for the approval command. The human must accept it for the approval to run.

## Execution

1. Approve (from the repo root), with the artifact the human named (`prd`, `ux` or `tickets`):
```bash
.venv/bin/python scripts/approve.py runs/<run-id> <prd|ux|tickets>
```
Add `--override "<reason>"` only for `prd` or `ux`, and only if the human typed an override reason. Never invent a reason. Without an override, the script refuses unless the audit verdict is PASS or PASS_WITH_RISK. For `ux` it also refuses when the PRD approval is not valid or the UX was not audited in its current form.

2. Check the approval:
```bash
.venv/bin/python scripts/check_approval.py runs/<run-id> <prd|ux|tickets>
```
Exit 0 and "approved" means the approval matches the current files. Exit 1 prints "missing", "stale" or "invalid".

3. Report the result in plain words: approved or refused, the script's message, the check result and, if an override was used, that it was recorded in `decisions.md`.

## Gate B (ux)

- Approving `ux` writes `runs/<run-id>/traceability.md` (which screens cover which requirement). It leaves `prd.md` untouched.

## Gate C (tickets)

- `/pm-approve tickets <run-id>` takes no override reason. No override exists for tickets: the Definition of Ready (`scripts/validate_tickets.py`) must pass, and the script refuses otherwise. It also refuses when the UX approval is not valid. Never pass `--override` for tickets.
- Approving `tickets` refreshes `runs/<run-id>/traceability.md` and leaves `prd.md` and `ux/` untouched.
- Changing `tickets.manifest.json`, the UX or the PRD makes the tickets approval stale. Writing Jira keys into the manifest later does not.

## Rules

- Do not write under `runs/<run-id>/approvals/` by hand. A hook blocks it. Only `scripts/approve.py` writes approvals.
- Editing `prd.md` after approval makes the PRD approval stale. The PRD then needs approving again.
- Changing the PRD or any UX file (`flows.md`, `spec.md`, `index.html`, any screen) after UX approval makes the UX approval stale. The UX then needs approving again.
- Changing the manifest, the PRD or any UX file after tickets approval makes the tickets approval stale. Changing only a `jira_key` value does not.
