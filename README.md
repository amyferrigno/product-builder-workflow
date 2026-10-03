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
- **M1** (current): Extraction + problem framing.
- **M2**: PRD writer + auditor.
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
