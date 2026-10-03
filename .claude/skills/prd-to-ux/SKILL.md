---
name: prd-to-ux
description: Turn an approved PRD into flows, HTML screen mocks and a spec (Stage 2), stopping at Human Gate B for approval
---

## Trigger

`/pm-ux <run-id>`

Needs a run folder `runs/<run-id>/` whose PRD is approved at Gate A.

## Execution

### Step 1: Check the PRD approval

Run:
```bash
.venv/bin/python scripts/check_approval.py runs/<run-id> prd
```

It must print "approved" (exit 0). If not, stop and tell the human to run `/pm-approve prd <run-id>` first. Do not design anything.

### Step 2: Design

Call agent `ux-designer` in design mode (task line: "design"), passing the run directory path only. It reads `prd.md`, `templates/ux-screen.html`, `templates/ux-spec.md` and the tokens file, and writes `runs/<run-id>/ux/` (`flows.md`, `screens/`, `index.html`, `spec.md`). It never touches `prd.md` or `approvals/`. It returns paths only.

### Step 3: Validate

Run:
```bash
.venv/bin/python scripts/validate_ux.py runs/<run-id>
```

Exit 1 prints one error per line. Send those lines to the same agent once (task line: "revision", fix these errors) and run the validator again. If it still fails, set `status` to `"failed"` in `state.json`, show the errors and stop. Never retry a second time.

Checks include: every required state on every screen (plus the five AI states when the PRD has an AI addendum), every Must requirement mapped to a screen, REQ ids that exist in the PRD, self-contained files, token use, labels and alt text, and screens matching the index and spec.

### Step 4: Audit

1. Compute the UX hash and keep it:
```bash
.venv/bin/python scripts/ux_hash.py runs/<run-id>
```
2. Call agent `ux-auditor` in a fresh context with four things only: the run directory path, the rubric path `templates/audit-ux.rubric.yaml`, the `run_id` (the folder name) and that hash as `ux_hash`. Do not pass the designer's reasoning.
3. Save the auditor's final message, verbatim, to `runs/<run-id>/ux.audit.json`. Do not edit it. If it is not valid JSON, ask the auditor once to return the JSON only.

### Step 5: Render the verdict

Run (the script decides, never you):
```bash
.venv/bin/python scripts/render_ux_audit.py runs/<run-id>
```

It prints PASS, PASS_WITH_RISK or FAIL (exit 1 on FAIL), writes `ux.audit.md` and updates `state.json`. A failing validator also gives FAIL, whatever the scores say. If it exits 2, the audit JSON is invalid: show the error and stop.

### Step 6: Revision loop (only on FAIL)

Read `audit.max_revision_loops` from `pm.config.yaml` (currently 2). While the verdict is FAIL and `state.json` `audit_loops.ux` is below that maximum:
1. Collect only the fixes and their screen ids from `ux.audit.json` (dimensions scored below 3) and from the validator or verdict reasons.
2. Call agent `ux-designer` in revision mode (task line: "revision") with the run directory path and that list. It changes only the named screens and their spec sections, then re-validates.
3. Re-run Step 3, then Step 4 (new hash, fresh auditor call, new `ux.audit.json`) and Step 5.

Never exceed the maximum. If the verdict is still FAIL after the last allowed loop, set `status` to `"escalated"` in `state.json`, show `ux.audit.md` (reasons and fixes) to the human, and stop. Report honestly which agents ran and what the scripts said.

### Step 7: Human Gate B

On PASS or PASS_WITH_RISK, run:
```bash
.venv/bin/python scripts/gate_summary.py runs/<run-id> ux
```

Show the output to the human and STOP. Do not continue to Stage 3 (tickets).

The human approves with `/pm-approve ux <run-id>`. The model never approves: it must never run `scripts/approve.py` and must never write anything under `approvals/`. A hook blocks such writes.

## Errors

Return error and stop if:
- The PRD is not approved (Step 1)
- UX validation still fails after the one retry
- `render_ux_audit.py` exits 2 (invalid audit JSON)

## Success

Stage 2 ends at one of: `awaiting_approval` (Gate B summary shown), `escalated` (open audit issues shown) or `failed` (validator errors shown). Every state value used is allowed by `schemas/state.schema.json`. Screenshots are not part of this stage: the auditor reads the HTML and scripts check the facts.
