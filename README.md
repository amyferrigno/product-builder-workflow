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

- **M0** (current): Scaffold—repo layout, config, schemas, validator, tests.
- **M1**: Extraction + problem framing.
- **M2**: PRD writer + auditor.
- **M3**: Data enrichment.
- **M4**: Customer anecdotes.
- **M5**: UX design.
- **M6**: Jira dry-run.
- **M7**: Jira publish.
- **M8**: Cost + polish.

## Key Files

- `CLAUDE.md`: Principles and repo layout.
- `decisions.md`: Aligned decisions with reasons.
- `memory.md`: Shared team context.
- `PLAN.md`: Current milestone steps.
- `pm.config.yaml`: Configuration (placeholders for real values).
- `connectors/registry.yaml`: Provider registry.
- `schemas/`: JSON Schema validators for handoff formats.
- `scripts/validate_schema.py`: Validator CLI tool.

## Architecture

The workflow operates in 3 stages:

1. **Stage 1** (Extraction): Meeting notes → structured problem statement.
2. **Stage 2** (PRD + UX): Problem → audited PRD and UX screens.
3. **Stage 3** (Jira): Screens → Jira tickets (dry-run or publish).

Each stage has a budget, gates, and approval checkpoints. See `PLAN.md` for the current milestone.
