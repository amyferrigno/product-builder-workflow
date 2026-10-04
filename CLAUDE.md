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

- `.claude/agents/`: notes-extractor, prd-writer (4 modes: problem framing, PRD draft, PRD revision, no-PRD memo), prd-auditor (read-only), data-enricher (Read, Bash; runs enrich.py), anecdote-curator (Read, Write), ux-designer (Read, Write, Edit, Bash; design and revision), ux-auditor (read-only), ticket-architect (Read, Write, Bash; design and revision), jira-publisher (Read, Bash; runs jira_publish.py)
- `.claude/skills/`: `/pm-prd` (meeting-to-prd), `/pm-audit` (prd-audit), `/pm-approve` (human only), `/pm-enrich` (data-enrichment), `/pm-anecdotes` (customer-anecdotes), `/pm-ux` (prd-to-ux), `/pm-audit ux` (ux-audit), `/pm-tickets` (prd-to-tickets), `/pm-publish` (jira-publish, human only), `/pm-run` (pm-run, drives the whole flow and stops at each gate), `/pm-status` (pm-status, read only); `/pm-approve ux` is Gate B, `/pm-approve tickets` is Gate C
- `.claude/hooks/`: guard_approvals (blocks writes under approvals/), validate_artifact (runs the PRD validator), guard_readonly_query (blocks mutating or non-aggregate SQL), pii_scan (scans anecdotes and PRD), guard_stage_gate (no ux/ writes before PRD approval, no tickets before UX approval), guard_jira_write (blocks Jira writes outside `jira_publish.py`, which enforces the same rules), cost_meter_hook (SubagentStop, logs cost), load_context (SessionStart), checkpoint (PreCompact), close_out (Stop)
- `connectors/`: `registry.yaml` (all disabled), `queries/` (reviewed query library), `providers/` (mock warehouse and anecdotes). Offline demo: `fixtures/registry.mock.yaml` + `fixtures/pm.config.mock.yaml`
- `schemas/`: JSON Schema for handoff formats (extraction, problem, PRD audit, state, etc.)
- `scripts/`: intake, validators (extraction, problem, PRD, evidence, anecdotes), render_audit/audit_verdict, approve/check_approval, gate_summary, enrich, anecdotes, providers, sql_guard, pii, ux_hash, validate_ux, ux_verdict, render_ux_audit, traceability, tickets_hash, validate_tickets, preview_tickets, jira_client (REST, standard library), jira_publish (dry run, or live with `--publish`), active_run, cost_meter (log, summary, check), prd_decision (PRD or memo), validate_memo, status (`--next`), eval_fixtures (`make eval`)
- `templates/`: problem.md, ai-gates.md, prd.md, prd-ai-addendum.md, audit-prd.rubric.yaml, ux-tokens.css, ux-screen.html, ux-spec.md, audit-ux.rubric.yaml, jira-epic.md, jira-story.md, jira-task.md, no-prd-memo.md
- `fixtures/`: Synthetic meeting notes with golden outputs (golden outputs per fixture, including a no-PRD memo; `bad-prd/` must fail)
- `tests/`, `runs/`: Test suite and active run workspaces

Evidence cards come only from `enrich.py`; anecdote quotes are copied unchanged from scrubbed candidates.

Only a human runs `/pm-approve`. The verdict comes from `scripts/render_audit.py` (PRD) or `scripts/render_ux_audit.py` (UX), never from a model.

## Running Tests

```bash
make setup    # Create .venv and install dependencies (Python 3.9+)
make test     # Run pytest
make eval     # Check every fixture against its expected result
```

All tests must pass before shipping. Schema validation is automatic.
