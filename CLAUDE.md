# Agentic PM Workflow Principles

This file documents how we build and maintain this agentic PM tool.

## 11 Core Principles

1. **User Value & Business Value**: Create value for users, capture value for the business. Test both before shipping.
2. **Start with Problems**: Document the problem first. Solution-only notes become UNVALIDATED problem hypotheses.
3. **Roadmaps are Problems**: Frame roadmaps by the problems they solve, not the features they add.
4. **Strategy Says No**: Write explicit non-goals. Strategy is the authority to reject scope.
5. **Define Success First**: One primary metric, guardrails, target with timeframe. Before building.
6. **5-Gate AI Framework**: Every AI proposal must pass five gates (probabilistic, pattern match, data ready, error tolerance, positive ROI). Red flags block: known finite rules, insufficient data, catastrophic errors, explainability needed, UX problem in disguise, commodity tool rebuild.
7. **AI-First PRD**: State what good looks like (examples), constraints (never do this), data/context needs, architecture (prompt vs RAG vs agent), test set (good/bad/edge cases), and observability (metrics, thresholds).
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

- `.claude/agents/`: Agent specs (notes-extractor, prd-writer, etc.)
- `.claude/skills/`: Orchestration skills (e.g., `/pm-prd` for intake → extraction → problem framing)
- `connectors/`: Registry, queries, integrations (M3+)
- `schemas/`: JSON Schema for handoff formats (extraction, problem, PRD, etc.)
- `scripts/`: intake.py, ai_gates.py, validators
- `templates/`: problem.md, ai-gates.md, PRD template (M2+)
- `fixtures/`: Synthetic meeting notes with golden outputs for testing
- `tests/`, `runs/`: Test suite and active run workspaces

## Running Tests

```bash
make setup    # Create .venv and install dependencies (Python 3.9+)
make test     # Run pytest
```

All tests must pass before shipping a milestone. Schema validation is automatic.
