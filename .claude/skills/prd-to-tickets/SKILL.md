---
name: prd-to-tickets
description: Turn an approved PRD and UX into a Jira ticket manifest, stop at Human Gate C, then write the dry-run payloads (Stage 3, nothing is sent to Jira)
---

## Trigger

`/pm-tickets <run-id>`

Needs a run folder `runs/<run-id>/` whose PRD is approved at Gate A and whose UX is approved at Gate B.

## Execution

### Step 1: Check the UX approval

Run:
```bash
.venv/bin/python scripts/check_approval.py runs/<run-id> ux
```

It must print "approved" (exit 0). If not, stop and tell the human which approval to run first: `/pm-approve ux <run-id>` (and `/pm-approve prd <run-id>` if the PRD is not approved). Do not plan any tickets.

### Step 2: Check for an existing tickets approval

Run:
```bash
.venv/bin/python scripts/check_approval.py runs/<run-id> tickets
```

If it prints "approved", the tickets are already approved and unchanged. Skip to Step 6. Otherwise continue.

### Step 3: Plan the tickets

Call agent `ticket-architect` in design mode (task line: "design"), passing the run directory path only. It reads `prd.md`, `02-problem.md`, `ux/spec.md`, `ux/flows.md`, `traceability.md`, the Jira templates and `pm.config.yaml`, and writes `runs/<run-id>/tickets.manifest.json`. It never touches `prd.md`, `ux/` or `approvals/`, and never calls Jira. It returns paths only.

### Step 4: Validate (Definition of Ready)

Run:
```bash
.venv/bin/python scripts/validate_tickets.py runs/<run-id>
```

Exit 1 prints one error per line, each starting with a ticket id. Read `audit.max_revision_loops` from `pm.config.yaml` (currently 2). While there are errors and fewer revision loops than that maximum have run:
1. Send only the error lines to agent `ticket-architect` in revision mode (task line: "revision") with the run directory path. It changes only the tickets named and re-validates.
2. Run the validator again.

Never exceed the maximum. If errors remain after the last allowed loop, set `status` to `"escalated"` in `state.json`, show the remaining errors to the human and stop.

Checks include: schema, ids and labels, summary format and length, no placeholder text, at least 3 Given/When/Then criteria per Story, REQ and screen links that exist, analytics events from the spec, AI quality criteria when the PRD has an AI addendum, one instrumentation Task per feature Epic, one Measure and Quality Epic, every Must requirement covered, no `blocks` cycle, and every `jira_key` null.

### Step 5: Preview and Human Gate C

Run:
```bash
.venv/bin/python scripts/preview_tickets.py runs/<run-id>
.venv/bin/python scripts/gate_summary.py runs/<run-id> tickets
```

Show the summary to the human and STOP. Tell the human to read `runs/<run-id>/tickets.preview.md` (totals, ticket tree, Must coverage) and then run `/pm-approve tickets <run-id>`.

The model never approves: it must never run `scripts/approve.py` and must never write anything under `approvals/`. A hook blocks such writes. There is no override for tickets: the Definition of Ready must pass.

### Step 6: Dry-run payloads (only after approval)

Run this only when `check_approval.py runs/<run-id> tickets` printed "approved":
```bash
.venv/bin/python scripts/jira_publish.py runs/<run-id>
```

In this version it is a dry run. It writes `runs/<run-id>/tickets.dryrun.json` (the exact Jira payloads, epics first) and prints one line per ticket. Nothing is sent to Jira. Report the summary lines to the human in plain words. The model never calls a Jira tool.

To publish for real after the dry run, the human runs `/pm-publish <run-id>` (skill `jira-publish`). This skill never publishes.

## Errors

Return error and stop if:
- The UX is not approved (Step 1)
- Validation still fails after the last allowed revision loop (Step 4)
- `jira_publish.py` exits 1 (approval missing or stale, or a mode other than dry run): show its message and stop

## Success

Stage 3 ends at one of: `awaiting_approval` (Gate C summary shown), `escalated` (open validator errors shown) or the dry run written after approval. Every state value used is allowed by `schemas/state.schema.json`. Changing the manifest, the UX or the PRD after approval makes the tickets approval stale and it needs approving again.
