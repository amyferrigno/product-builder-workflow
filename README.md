# Agentic PM Workflow

An AI-driven workflow to turn meeting notes into audited PRDs, UX mocks, and Jira tickets. Multi-stage pipeline with human approval gates.

## Setup

```bash
make setup    # Create .venv, install dependencies (Python 3.9+)
```

## Run Tests

```bash
make test     # Run pytest
```

All tests must pass before merging. Schema validation is automatic.

## Milestones

See [planning.md](planning.md) for the full roadmap and status.

- **M0** (done): Scaffold—repo layout, config, schemas, validator, tests.
- **M1** (done): Extraction + problem framing.
- **M2** (current): PRD writer + auditor.
- **M3**: Data enrichment.
- **M4**: Customer anecdotes.
- **M5**: UX design.
- **M6**: Jira dry-run.
- **M7**: Jira publish.
- **M8**: Cost + polish.

## Running the Workflow (M1: Extraction + Problem Framing)

### Intake: Convert notes to numbered, citable source

```bash
# From a file
.venv/bin/python scripts/intake.py path/to/notes.md [--slug name] [--date YYYY-MM-DD]

# From stdin
echo "notes here" | .venv/bin/python scripts/intake.py - --slug mymeeting

# Output: run ID and path to numbered notes
```

Supports `.md`, `.txt`, `.docx`, and stdin. Creates `runs/<date>-<slug>/` with numbered notes and `state.json`.

### Validators

```bash
# Check extraction.json
.venv/bin/python scripts/validate_extraction.py runs/2026-01-15-demo/

# Check problem.md
.venv/bin/python scripts/validate_problem.py runs/2026-01-15-demo/
```

Both exit 1 on errors, print one error per line. Extraction validator enforces that all cited lines are non-blank. Problem validator also checks AI verdict logic.

## Running the Workflow (M2: PRD, audit, approval)

Commands (skills in `.claude/skills/`):

- `/pm-prd <path-or-paste>`: intake, extraction, problem framing, PRD draft, validation, audit, revision loop (up to `audit.max_revision_loops`), then stops at Human Gate A with a summary.
- `/pm-audit prd <run_dir>`: audit an existing or hand-written PRD in a run folder.
- `/pm-approve prd <run-id> [override reason]`: human only. Approves the PRD, tied to its hash.

Scripts:

```bash
.venv/bin/python scripts/validate_prd.py runs/<run-id>/       # structure, IDs, citations, number tracing
.venv/bin/python scripts/render_audit.py runs/<run-id>/       # prd.audit.json -> verdict, prd.audit.md, state.json
.venv/bin/python scripts/audit_verdict.py runs/<run-id>/      # verdict only
.venv/bin/python scripts/gate_summary.py runs/<run-id>/ prd   # one-screen Gate A summary
.venv/bin/python scripts/approve.py runs/<run-id>/ prd [--override "reason"]
.venv/bin/python scripts/check_approval.py runs/<run-id>/ prd # exit 0 only if approval matches current prd.md
```

Hooks (`.claude/settings.json`):

- `guard_approvals.py` (before Write/Edit): blocks any write under `runs/*/approvals/`.
- `validate_artifact.py` (after Write/Edit): runs `validate_prd.py` when `runs/*/prd.md` is edited and reports errors.

Agents: `prd-writer` (problem framing, PRD draft, PRD revision) and `prd-auditor` (read-only, returns audit JSON). The verdict is computed by script, not by the auditor.

## Key Files

- `CLAUDE.md`: Principles and repo layout.
- `decisions.md`: Aligned decisions with reasons.
- `memory.md`: Learnings and patterns from runs.
- `PLAN.md`: Current milestone steps.
- `pm.config.yaml`: Configuration and model tier mapping.
- `connectors/registry.yaml`: Registry of data sources.
- `schemas/`: JSON Schema validators.
- `scripts/`: Intake, AI gates logic, validators.
- `fixtures/`: Synthetic meeting notes with golden outputs.

## Architecture

The workflow operates in 3 stages:

1. **Stage 1** (Extraction): Meeting notes → structured problem statement.
2. **Stage 2** (PRD + UX): Problem → audited PRD and UX screens.
3. **Stage 3** (Jira): Screens → Jira tickets (dry-run or publish).

Each stage has a budget, gates, and approval checkpoints. See `PLAN.md` for the current milestone.
