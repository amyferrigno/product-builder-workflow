---
name: pm-status
description: Show where a run stands (stage, verdicts, approvals, cost) and the next command. Changes nothing
---

## Trigger

`/pm-status [run-id]`

With no run id, it uses the active run (the last one created by intake).

## Execution

1. Run:
```bash
.venv/bin/python scripts/status.py runs/<run-id>
```
With no run id, run `.venv/bin/python scripts/active_run.py get` first to get the run folder, then pass that folder. If there is no active run, tell the human to give a run id.

2. Show the output as is. Do not summarise or reword it.

3. Name the next command in one line, taken from the "next" line of the output.

## Rules

- Read only. It changes no file and writes nothing under `approvals/`.
- Never run `scripts/approve.py`. Approval is `/pm-approve`, human only.
