---
name: pm-run
description: Drive a run through the whole flow (PRD or memo, UX, tickets, dry run) by following the other skills, stopping at every human gate
---

## Trigger

`/pm-run <notes path or run-id>`

This skill only decides what comes next and follows the other skills. It never repeats their steps and never approves.

## Setup

1. If the argument is a file path (`.md`, `.txt`, `.docx`): run intake as `meeting-to-prd` Step 1 does:
```bash
.venv/bin/python scripts/intake.py <path> [--slug name]
```
Exit 1 means stop and show the error. Otherwise take the new run id from its output.
2. If the argument is a run id, use `runs/<run-id>/` as it stands. If the folder does not exist, stop and say so.

## The loop

Run:
```bash
.venv/bin/python scripts/status.py runs/<run-id> --next
```

It prints one word. Act on it, then run it again. The script decides the next step, never you.

| Word | Action |
|------|--------|
| `prd` | Follow skill `meeting-to-prd` from where the run stands. It ends at Gate A or with a no-PRD memo. |
| `ux` | Follow skill `prd-to-ux`. It ends at Gate B. |
| `tickets` | Follow skill `prd-to-tickets`. It ends at Gate C. |
| `publish_dry_run` | Follow the dry-run step of skill `prd-to-tickets` (Step 6). Nothing is sent to Jira. |
| `approve_prd` | STOP. Show the Gate A summary and give the command (see below). |
| `approve_ux` | STOP. Show the Gate B summary and give the command. |
| `approve_tickets` | STOP. Show the Gate C summary and give the command. |
| `memo_done` | Show the path `runs/<run-id>/no-prd-memo.md` and stop. |
| `done` | Run `.venv/bin/python scripts/status.py runs/<run-id>`, show it as is and stop. |

If a skill ends at `failed` or `escalated` (a validator or audit still failing after its retries), show what it reported and stop. Do not loop again.

## Human gates

For `approve_prd`, `approve_ux` and `approve_tickets`, run `.venv/bin/python scripts/gate_summary.py runs/<run-id> <prd|ux|tickets>` and show the output. Then tell the human the exact command to run themselves:

- `/pm-approve prd <run-id> [override reason]`
- `/pm-approve ux <run-id> [override reason]`
- `/pm-approve tickets <run-id>` (no override exists)

After the human approves, they run `/pm-run <run-id>` again and the loop continues.

## Cost check

Before each subagent launch (by any skill this one follows), run:
```bash
.venv/bin/python scripts/cost_meter.py check runs/<run-id>
```

- Exit 1 (a `STOP:` line): do not launch the agent. Tell the human the stage budget is exceeded. They can raise `budgets` in `pm.config.yaml` and run `/pm-run <run-id>` again.
- A `WARN:` line: relay it to the human and continue.

## Rules

- Live Jira publishing is never part of `/pm-run`. After the dry run, point the human to `/pm-publish <run-id>`.
- Never run the approval script and never write anything under `approvals/`. A hook blocks such writes.
- Show script output as is. Report honestly which agents ran and what the scripts said.
- `/pm-status <run-id>` shows where a run stands at any time.
