## 1. Header

- Title: Automated parsing of free-form meeting requests
- Owner: Product Manager
- Status: Draft for Human Gate A
- Version: 0.1
- Run ID: 2026-01-15-ai-clear-fit
- Problem framing: 02-problem.md (primary problem PB-1, AI verdict AI_JUSTIFIED)

## 2. TL;DR

Meeting requests arrive as free-form emailed text and the team manually parses each one into the system, taking 2 hours per request, which the VP Product puts at 1000 hours per month for 500 requests (P-1, M-2, M-3). The proposed direction is an LLM-based parser that drafts structured scheduling constraints, with every parsed request still reviewed by a human (S-1, S-2, R-1). The proposed primary success metric is the share of parsing automated, for which the notes name a target of 80% (M-6).

## 3. Problem statement

One of the largest customers, a legal firm with complex scheduling rules, sent 500 meeting requests last month (U-1, M-1). The requests come as emails with free-form text. The team manually parses each one into the system, taking 2 hours per request, which is 1000 hours per month of manual work for 500 requests (P-1, M-2, M-3). Customers wait 24-48 hours for confirmation (P-2, M-7). Validation status: VALIDATED in the problem framing (PB-1), on the figures reported in the notes.

## 4. Why now and strategic fit

- The scale is large: 500 requests last month from one customer (M-1).
- The VP Product expects savings in operational cost and faster request fulfilment for customers (S-2).
- The notes state no deadline or trigger, and no wider strategy statement.

## 5. Target users and segments

For: the internal team that parses requests by hand (U-3), customers who send free-form requests such as the legal firm (U-1), and other customers whose requests are also in the logs (U-2).

Not for: customers with no free-form request flow; the notes do not describe any.

## 6. Evidence

### 6a. Data insights

No data provider configured. The figures below were reported in the meeting and are not verified by a data provider.

- One large customer sent 500 meeting requests last month (M-1).
- The team spends 2 hours per request on manual parsing, which the VP Product puts at 1000 hours per month for 500 requests (M-2, M-3).
- Logs of those 500 requests plus another 800 from other customers give 1300 labeled examples of free-form request to structured output (M-4).
- About 30 distinct constraint types (M-5).
- Customers currently wait 24-48 hours for confirmation (M-7).

### 6b. Customer anecdotes

No anecdote provider configured. No anecdote records exist for this run.

- Requests arrive as free-form emailed text (P-1). No verbatim customer request is captured as an anecdote record, and the frequency of any one request pattern is unknown.
- No counter-anecdote was raised in the notes.

### 6c. Evidence gaps

- No data provider: the volume, time and wait figures (M-1, M-2, M-3, M-7) come from a verbal report. How to close: pull the request logs and time records through a data connector and attach evidence cards.
- The 2 hours per request (M-2) has no stated measurement method. How to close: sample timed parsing sessions.
- Per-type example counts across the 30 constraint types (M-5) were not discussed. How to close: count examples per type in the logs.
- Data quality of the 1300 labeled examples (M-4) and production access were not discussed. How to close: audit a sample of labels and confirm access with the Data Analyst.
- Customer reaction to faster confirmation is not evidenced. How to close: capture customer feedback as anecdote records once an anecdote provider is configured.

## 7. Goals and non-goals

Goals:

- Cut the manual parsing effort per request (P-1, M-2).
- Automate 80% of the parsing, as named in the meeting (M-6).
- Shorten the customer wait for confirmation (P-2, M-7).
- Keep a human reviewing every parsed request (R-1).

Non-goals:

- Removing human review of parsed requests (R-1).
- Replacing the scheduling system itself.
- Handling anything other than free-form request parsing in v1.

## 8. Success metrics

- **MET-001** Primary metric: share of meeting-request parsing automated.
  - Target: 80% automated parsing, named in the meeting (M-6). The timeframe and the exact definition are proposals.
  - Timeframe: proposed: measured on the golden set before launch and monthly after launch.
  - Baseline: no automated parsing today; the team parses every request by hand at 2 hours per request (M-2).
  - Instrumentation: compare parser output to reviewer-corrected output for every request.
- **MET-002** Guardrail: parser accuracy on the holdout set (R-2).
  - Target: proposed: must meet the A8 must-pass thresholds before launch and not drift below them.
  - Timeframe: proposed: before launch, then continuous.
  - Baseline: unknown, to be measured before launch.
- **MET-003** Guardrail: customer confirmation wait time (M-7).
  - Target: proposed: must be shorter than the current wait.
  - Timeframe: proposed: reviewed monthly after launch.
  - Baseline: 24-48 hours today (M-7).
- **MET-004** Guardrail: misparsed constraints that reach a scheduled meeting (P-3).
  - Target: proposed: none reach a scheduled meeting unreviewed.
  - Timeframe: proposed: continuous after launch.
  - Baseline: unknown, to be measured before launch.

Vanity check: share automated is meaningless if reviewers must rewrite most drafts, so MET-002 and MET-004 guard quality.

## 9. Value tests

### User Value / Trust Test

Customers get faster confirmation (M-7) and the team gets time back for complex cases. Trust depends on the AI being a draft that a human reviews (R-1), with low-confidence parses flagged (S-3) and the reviewer able to see and correct every constraint (A7). Verdict: passes, subject to the gaps in 6c.

### Business Value Test

The cost today is 1000 hours per month of manual work for 500 requests (M-3). The hidden costs named in the meeting are drift monitoring, ongoing evals and retraining (R-3, R-4, S-3). No build cost was stated (A10). Verdict: passes on the stated savings, with the full cost unknown.

## 10. Solution overview

Direction: an LLM-based parser that turns free-form request text into structured scheduling constraints, as a draft for human review (S-1, S-2, R-1). The Engineer Lead proposed a fine-tuned model on the request data, a confidence threshold so low-confidence parses get human review, and monthly retraining on new labeled data (S-3). The architecture is to be specified (A-1). The Data Analyst says an MVP could be running in 4 weeks (M-8).

## 11. User flow

1. A customer emails a free-form request. The system receives it.
2. The system parses the text into structured constraints and a confidence value. The reviewer receives the draft, with low-confidence parses flagged.
3. The reviewer checks the draft, corrects it if needed and approves it (R-1).
4. The system schedules from the approved constraints and the customer receives the confirmation.

## 12. Requirements

| REQ-ID | Description | Priority | Acceptance criteria |
|--------|-------------|----------|---------------------|
| REQ-001 | Parse a free-form request into structured scheduling constraints (S-1, P-1) | Must | Given a free-form emailed request, When the parser runs, Then it outputs structured constraints covering the constraint types in the request |
| REQ-002 | Attach a confidence value and flag low-confidence parses for review (S-3) | Must | Given a parsed request below the confidence threshold, When it is queued, Then it is flagged as low confidence for the reviewer |
| REQ-003 | Require human review of every parsed request before scheduling (R-1) | Must | Given a parsed request, When no reviewer has approved it, Then the system does not schedule the meeting |
| REQ-004 | Let the reviewer see and correct every parsed constraint (P-3, R-1) | Must | Given a draft with a wrong constraint, When the reviewer edits it, Then the corrected constraint is used and the correction is recorded |
| REQ-005 | Measure parser accuracy on a holdout set before launch (R-2) | Must | Given a holdout set split from the labeled data, When the eval runs, Then accuracy is reported per dimension against the A8 thresholds |
| REQ-006 | Monitor drift as request patterns evolve (R-3) | Should | Given live requests after launch, When a monitoring period ends, Then drift and correction rates are reported |
| REQ-007 | Retrain on new labeled data on a schedule (S-3, R-4) | Should | Given new reviewer-corrected examples, When the monthly retraining runs, Then the new model is evaluated against the golden set before it replaces the old one |
| REQ-008 | Fall back to full manual parsing when the parser fails or is unavailable (P-3) | Must | Given a parser outage or an unparseable request, When the request arrives, Then it goes to the manual queue and the customer is not blocked |

## 13. MVP scope

### In v1

- Parser for free-form requests with a confidence threshold (S-2, S-3).
- Human review of every parsed request (R-1).
- Holdout evaluation and a golden set (R-2).
- Drift monitoring (R-3).

### Out of v1

- Automatic scheduling without human review (R-1).
- Anything beyond request parsing.
- Retraining automation beyond the monthly cycle (S-3).

## 14. Dependencies and assumptions

- Access to the request logs and the 1300 labeled examples (M-4).
- Assumption: the labels are good enough for a train/test split, which the Data Analyst says there is enough data for (R-2).
- The Engineer Lead specifies the architecture (A-1).
- Assumption: the 4 week MVP estimate holds (M-8).

## 15. Risks and mitigations

- The AI misparses a constraint and the meeting is scheduled wrong (P-3). Mitigation: human review of every parse (R-1) and the confidence threshold (S-3).
- Drift as request patterns change (R-3). Mitigation: monitoring and monthly retraining (R-4, S-3).
- Sparse examples for rare constraint types (M-5). Mitigation: count examples per type and add golden set cases for rare types.
- Reviewers rubber-stamp drafts. Mitigation: sample audits of approved drafts (A9).
- The evidence is notes-only and unverified until provider data exists: the volume, time, wait and label figures were only reported in the meeting, with no evidence cards or anecdote records (M-1, M-2, M-3, M-4, M-7). Mitigation: close the gaps in 6c, with provider data and anecdote records, before launch.

## 16. Launch and rollout

The notes give no rollout plan. Proposed: ship behind a feature flag to the internal team first, with every parse reviewed, expand only when the A8 thresholds are met on the golden set, and keep the manual queue available at all times. Communication plan to be agreed with Customer Success.

## 17. Open questions

- What is the build and run cost of the model? Owner: Engineer Lead.
- How many examples exist per constraint type (M-5)? Owner: Data Analyst.
- Is production access to the request data confirmed? Owner: Data Analyst.
- What confidence threshold balances review load and risk (S-3)? Owner: Engineer Lead.
- How was the 2 hours per request measured (M-2)? Owner: Customer Success Manager.

## 18. Alignment

- Eng: Engineer Lead signs off on architecture and feasibility (A-1).
- Design: reviewer experience to be confirmed before Stage 2.
- Data: Data Analyst signs off on the labeled data and holdout set (M-4).
- GTM: Customer Success Manager signs off on customer impact (M-7).
- Leadership: VP Product signs off on the business case (M-3).

## 19. Decision log

Meeting decisions: the extraction records no decision items. The following are proposals and agreements discussed in the meeting, not formal decisions:

- Every parsed request still goes to a human for review (R-1).
- The Engineer Lead proposed to spec the architecture (A-1, S-3).

Workflow decisions:

- PB-1 is the primary problem because it is the only problem in the framing, and no problems are parked.
- The AI verdict is AI_JUSTIFIED because all five gates pass with no red flags, per the problem framing.
- Section 8 targets other than the 80% named in the meeting (M-6) are proposals.

## 20. Traceability

| REQ | Screens | Jira |
|-----|---------|------|
| REQ-001 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-002 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-003 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-004 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-005 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-006 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-007 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-008 | not yet created (Stage 2) | not yet created (Stage 3) |

## A1. 5-Gate verdict and red flag check

Verdict from the problem framing: AI_JUSTIFIED. All five gates pass and no red flag applies.

- Gate 1 (genuinely probabilistic): pass. Free-form text with about 30 distinct constraint types (P-1, M-5, S-1).
- Gate 2 (matches an AI pattern): pass. NLU, parsing free-form text into structured constraints (S-1, S-2).
- Gate 3 (data ready): pass. 1300 labeled examples and enough for a train/test split (M-4, R-2). Per-type counts, data quality and production access were not discussed (M-5).
- Gate 4 (error tolerance): pass. A misparse would schedule a meeting wrong (P-3), but every parsed request goes to a human for review and low-confidence parses are flagged (R-1, S-3).
- Gate 5 (ROI after hidden costs): pass. Drift monitoring, ongoing evals and retraining were named (R-3, R-4, S-3) against 1000 hours per month of manual work (M-3). No build cost was stated.

Red flags found: none.

## A2. AI pattern and architecture choice

Pattern: NLU/NLG. The Engineer Lead's proposed architecture is a fine-tuned model on the request data, a confidence threshold, and monthly retraining (S-3). Rationale: the task is a narrow, repeated extraction from text with a large set of labeled examples (M-4), which favours a fine-tuned or prompted model over an agent, and no retrieval over documents is described, so retrieval is not proposed. The PRD keeps the choice between a fine-tuned model and a prompted LLM-based parser open for the architecture spec (S-2, A-1), and compares both on the golden set.

## A3. Context engineering

- System prompt intent: turn one free-form request into structured constraints of the known types, about 30 in all (M-5), and say when a request is ambiguous.
- Data sources: the labeled request logs only (M-4). No customer row-level data goes into logs or prompts beyond what the request needs.
- Few-shot examples: chosen from the labeled examples, covering each constraint type.

## A4. What good looks like

- Good (illustrative): for a request that combines a date range, a time-of-day preference, a day exclusion and a location preference with a fallback, the parser outputs one structured constraint for each part.
- Bad (illustrative): dropping the day exclusion, or treating the fallback as the main preference.
- Edge: a request with conflicting constraints, or a constraint type outside the known types. The parser flags it instead of guessing.

## A5. Constraints

- Never schedule a meeting from an unreviewed parse (R-1).
- Never invent a constraint that the request text does not contain.
- Decline and route to manual parsing when the request is unparseable or out of the known types.
- Never put row-level customer data or personal data into prompts or logs beyond what is needed.

## A6. Error tolerance and fallback

- Low tolerance: a misparse schedules a meeting wrong (P-3), so every parse is reviewed (R-1).
- A confidence threshold sends low-confidence parses to flagged review (S-3). The threshold value is an open question (section 17).
- Fallback: the manual parsing queue stays available and takes over on failure or outage (REQ-008).
- Escalation: repeated corrections of the same constraint type are reported to the Engineer Lead.

## A7. Trust, control, recovery

- Trust: the reviewer sees the original text next to the parsed constraints, with confidence shown and low-confidence parses flagged (S-3).
- Control: the reviewer can edit any constraint, reject the draft, or send it to manual parsing (R-1, REQ-004).
- Recovery: if a wrong meeting is scheduled, the reviewer can correct the constraints and reschedule; the correction is recorded for retraining (R-4).
- The AI output is always a draft, never final (R-1).

## A8. Eval plan

Scale: 1 to 4 per dimension. 1 = wrong or missing, 2 = weak, 3 = meets the minimum, 4 = excellent.

| Dimension | Weight | Must-pass threshold |
|-----------|--------|---------------------|
| Constraint extraction accuracy (all types) | 40% | Average 3 or above, no type below 2 |
| No invented constraints | 25% | 4 on every golden case |
| Ambiguity and conflict handling | 20% | Average 3 or above |
| Confidence calibration (low confidence flags real errors) | 15% | Average 3 or above |

These weights and thresholds are proposals for the Engineer Lead and Data Analyst to confirm. Evals block launch (R-2): any must-pass threshold missed means no ship.

Golden set: a target of 50 or more cases before launch, drawn from the labeled data (M-4) and covering:

- Good cases: clear requests of each constraint type.
- Bad cases: requests the parser must not misread, such as negations.
- Edge cases: conflicting constraints, unknown constraint types, very long requests.
- Failure cases: empty, garbled or non-request text, which must go to manual parsing.

The holdout set from the train/test split measures accuracy (R-2).

## A9. Observability

- Sampling: review a sample of live parses daily after launch, then weekly, never zero.
- Explicit feedback: reviewer corrections and rejections (R-1).
- Implicit feedback: how long reviewers spend per draft, and how often low-confidence flags were right.
- Drift: track the correction rate and the mix of constraint types over time (R-3).
- Thresholds for alerts are proposals to be set with the Engineer Lead.

## A10. Full cost estimate

No amounts were stated in the notes, so none are given here. Cost components to be estimated:

- Model API or hosting costs for parsing and for retraining (S-3).
- Data work: cleaning and auditing the labeled examples (M-4).
- Eval design: building and maintaining the golden set and the holdout set (R-2).
- Monitoring: drift and quality sampling (R-3).
- Review time that remains, since every parse is reviewed (R-1).
- Rebuild risk: the parser may need rework as request patterns evolve (R-4).
