# Agentic PM Workflow Principles

This file documents how we build and maintain this agentic PM tool.

## 11 Core Principles

1. **User Value & Business Value**: Create value for users, capture value for the business. Test both before shipping.
2. **Start with Problems**: Document the problem first. Solution-only notes become UNVALIDATED problem hypotheses.
3. **Roadmaps are Problems**: Frame roadmaps by the problems they solve, not the features they add.
4. **Strategy Says No**: Write explicit non-goals. Strategy is the authority to reject scope.
5. **Define Success First**: One primary metric, guardrails, target with timeframe. Before building.
6. **Does This Need AI?**: Apply the 5-gate framework. Watch for red flags: complexity theatre, "because AI", no baseline.
7. **AI-First PRD**: AI features need dedicated PRDs covering training data, failure modes, eval thresholds.
8. **Design for Wrong**: Plan for when the AI fails. Build trust, control and recovery into the UX.
9. **Evals are a Gate**: 1-to-4 scale, weighted, thresholds. Evals block ship. No handwaving.
10. **Alignment Needs Records**: All decisions go in `decisions.md` with reasons, not chat. Write to `decisions.md` when alignment happens.
11. **Anecdotes + Data**: Anecdotes illustrate. Data quantifies. Never invent quotes or numbers.

## Never Do

- Write to Jira without a matching human-signed approval file whose hash matches.
- Invent customer numbers or quotes; cite sources.
- Put row-level customer data or PII in prompts or logs.
- Run mutating (INSERT, UPDATE, DELETE, DROP) queries against the warehouse.
- Set story points on tickets; engineers estimate (the manifest schema rejects the field).
- Edit files under `runs/*/approvals/` after creation.

## Repo Layout

- `.claude/`: Agent/skill/hook code (empty scaffold in M0).
- `connectors/`: Registry, scripts, query builders, provider integrations.
- `schemas/`: JSON Schema validators for all handoff formats.
- `scripts/`: Utilities (validator, etc.).
- `templates/`: PRD, UX, ticket templates (empty in M0).
- `fixtures/`: Test meeting notes and expected outputs.
- `tests/`: Test suite. Run with `make test`.
- `runs/`: Workspace for active runs (gitignored except `.gitkeep`).
- `pm.config.yaml`: Configuration (placeholders for real values).
- `connectors/registry.yaml`: Provider registry (all disabled in M0).
- `decisions.md`: Aligned decisions with reasons (dated, no chat).
- `memory.md`: Shared memory for the workflow.

## Running Tests

```bash
make setup    # Create .venv and install dependencies (Python 3.9+)
make test     # Run pytest
```

All tests must pass before shipping a milestone. Schema validation is automatic.
